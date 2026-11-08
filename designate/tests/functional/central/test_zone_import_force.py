# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.
"""Tests for the force option of zone imports (PATCH-016)."""

from unittest import mock

from oslo_messaging.rpc import dispatcher as rpc_dispatcher
from oslo_utils import uuidutils

from designate import context as designate_context
from designate import exceptions
from designate import objects
import designate.tests.functional

ZONEFILE = """$ORIGIN example.com.
example.com. 600 IN SOA ns1.example.com. nsadmin.example.com. (
    2013091101 7200 3600 2419200 10800 )
example.com. 10800 IN NS ns1.example.com.
{body}
"""


class ZoneImportForceTest(designate.tests.functional.TestCase):

    def setUp(self):
        super().setUp()
        self.context = self.get_context(
            project_id=uuidutils.generate_uuid(), roles=['member', 'reader'])

    def _import(self, body, force=False, context=None, attributes=None):
        zone_import = self.central_service.create_zone_import(
            context or self.context, ZONEFILE.format(body=body),
            zone_attributes=attributes, force=force)
        return self.wait_for_import(zone_import.id, error_is_ok=True)

    def _zone(self, zone_id):
        return self.storage.get_zone(self.admin_context_all_tenants, zone_id)

    def _rrsets(self, zone_id):
        rrsets = self.storage.find_recordsets(
            self.admin_context_all_tenants, {'zone_id': zone_id})
        return {(r.name, r.type): r for r in rrsets}

    def test_changed_ttl_is_applied(self):
        first = self._import('www 300 IN A 192.0.2.1')
        result = self._import('www 3600 IN A 192.0.2.1', force=True)

        self.assertEqual('COMPLETE', result.status, result.message)
        rrset = self._rrsets(first.zone_id)[('www.example.com.', 'A')]
        self.assertEqual(3600, rrset.ttl)

    def test_unchanged_records_are_not_recreated(self):
        body = 'www 300 IN A 192.0.2.1\nwww 300 IN A 192.0.2.2'
        first = self._import(body)
        before = self._rrsets(first.zone_id)[('www.example.com.', 'A')]

        self._import(body, force=True)

        after = self._rrsets(first.zone_id)[('www.example.com.', 'A')]
        self.assertEqual(sorted(r.id for r in before.records),
                         sorted(r.id for r in after.records))

    def test_identical_zonefile_does_not_bump_serial(self):
        body = 'www 300 IN A 192.0.2.1'
        first = self._import(body)
        self.assertFalse(self._zone(first.zone_id).increment_serial)

        self._import(body, force=True)

        self.assertFalse(self._zone(first.zone_id).increment_serial)

    def test_failed_sync_leaves_zone_untouched(self):
        # SOA  NS  3 recordsets = 5
        first = self._import(
            'www 300 IN A 192.0.2.1\n'
            'a1 300 IN A 192.0.2.2\n'
            'a2 300 IN A 192.0.2.3')
        self.config(quota_zone_recordsets=5)

        result = self._import(
            'a1 300 IN A 192.0.2.2\n'
            'a2 300 IN A 192.0.2.3\n'
            'n1 300 IN A 192.0.2.4\n'
            'n2 300 IN A 192.0.2.5', force=True)

        self.assertEqual('ERROR', result.status)
        rrsets = self._rrsets(first.zone_id)
        self.assertIn(('www.example.com.', 'A'), rrsets,
                      'zone was half-synced: www already deleted')

    def test_zone_with_managed_records(self):
        first = self._import('www 300 IN A 192.0.2.1')
        sink_ctx = designate_context.DesignateContext().elevated()
        sink_ctx.all_tenants = True
        sink_ctx.edit_managed_records = True
        self.central_service.create_managed_records(
            sink_ctx, first.zone_id,
            records_values=[{
                'data': '192.0.2.10',
                'managed': True,
                'managed_plugin_name': 'plugin',
                'managed_plugin_type': 'plugin',
                'managed_resource_type': 'instance',
                'managed_resource_id': uuidutils.generate_uuid(),
            }],
            recordset_values={'zone_id': first.zone_id,
                              'name': 'vm.example.com.', 'type': 'A'},
        )

        result = self._import(
            'www 300 IN A 192.0.2.1\nvm 3600 IN A 192.0.2.10', force=True)

        self.assertEqual('COMPLETE', result.status, result.message)
        self.assertIn(('vm.example.com.', 'A'), self._rrsets(first.zone_id))

    def test_zone_being_deleted_keeps_delete_action(self):
        first = self._import('www 300 IN A 192.0.2.1')
        self.central_service.delete_zone(self.context, first.zone_id)
        self.assertEqual('DELETE', self._zone(first.zone_id).action)

        result = self._import('www 300 IN A 192.0.2.2', force=True)

        self.assertEqual('ERROR', result.status)
        self.assertEqual('DELETE', self._zone(first.zone_id).action)


    def test_secondary_zone_is_rejected(self):
        zone = self.create_zone(
            context=self.context, type='SECONDARY', name='example.com.',
            email='root@example.com',
            masters=[{'host': '192.0.2.53', 'port': 53}])

        result = self._import('www 300 IN A 192.0.2.1', force=True)

        self.assertEqual('ERROR', result.status)
        self.assertNotIn(('www.example.com.', 'A'), self._rrsets(zone.id))
        # The secondary's serial belongs to the primary - no local bump.
        self.assertFalse(self._zone(zone.id).increment_serial,
                         'serial bump on SECONDARY; import message: %s'
                         % result.message)

    def test_recordset_owned_by_shared_project(self):
        first = self._import('www 300 IN A 192.0.2.1')
        other = self.get_context(project_id=uuidutils.generate_uuid(),
                                 roles=['member', 'reader'])
        self.share_zone(context=self.context, zone_id=first.zone_id,
                        target_project_id=other.project_id)
        self.central_service.create_recordset(
            other, first.zone_id, objects.RecordSet(
                name='shared.example.com.', type='A',
                records=objects.RecordList(
                    objects=[objects.Record(data='192.0.2.9')])))

        result = self._import(
            'www 300 IN A 192.0.2.1\nshared 300 IN A 192.0.2.10', force=True)

        self.assertEqual('COMPLETE', result.status, result.message)

    def test_shared_project_cannot_force_import_owner_zone(self):
        first = self._import('www 300 IN A 192.0.2.1')
        other = self.get_context(project_id=uuidutils.generate_uuid(),
                                 roles=['member', 'reader'])
        self.share_zone(context=self.context, zone_id=first.zone_id,
                        target_project_id=other.project_id)
        flag_before = self._zone(first.zone_id).increment_serial

        result = self._import('evil 300 IN A 192.0.2.66', force=True,
                              context=other)

        self.assertEqual('ERROR', result.status, result.message)
        self.assertNotIn(('evil.example.com.', 'A'),
                         self._rrsets(first.zone_id))
        self.assertEqual(flag_before,
                         self._zone(first.zone_id).increment_serial)

    def test_requested_pool_differs_from_existing_zone_pool(self):
        first = self._import('www 300 IN A 192.0.2.1')
        pool = self.create_pool(tenant_id=self.context.project_id)
        self.policy({'zone_create_forced_pool': '@'})

        attributes = objects.ZoneAttributeList(objects=[
            objects.ZoneAttribute(key='pool_id', value=pool.id)])
        result = self._import('www 300 IN A 192.0.2.1', force=True,
                              attributes=attributes)

        zone = self._zone(first.zone_id)
        if result.status == 'COMPLETE':
            self.assertEqual(pool.id, zone.pool_id)

    @mock.patch('designate.central.service.Service._create_or_sync_zone')
    def test_long_error_message_does_not_leave_import_pending(
            self, mock_sync):
        for exc in (exceptions.BadRequest, exceptions.Forbidden):
            mock_sync.side_effect = exc('x' * 500)

            result = self._import('www 300 IN A 192.0.2.1', force=True)

            self.assertEqual('ERROR', result.status, exc)
            self.assertEqual('x' * 160, result.message)


    def test_force_requires_force_policy(self):
        self.policy({'create_force_zone_import': '!'})

        exc = self.assertRaises(
            rpc_dispatcher.ExpectedException,
            self.central_service.create_zone_import,
            self.context, ZONEFILE.format(body=''), force=True)
        self.assertEqual(exceptions.Forbidden, exc.exc_info[0])

    def test_import_without_force_ignores_force_policy(self):
        self.policy({'create_force_zone_import': '!'})

        result = self._import('www 300 IN A 192.0.2.1')

        self.assertEqual('COMPLETE', result.status, result.message)


OPS = 'role:dns_ops'
NO_A_UPDATES = {'update_recordset': '!', 'update_A_recordset': '!'}
OWNER_FORCE_ONLY_RULES = {
    'create_zone': OPS,
    'create_zone_import': OPS,
    'update_zone_import': OPS,
    'create_force_zone_import': (
        'role:dns_zonemaster and project_id:%(project_id)s'),
}


class ZoneImportForcePolicyTest(designate.tests.functional.TestCase):

    def setUp(self):
        super().setUp()
        project_id = uuidutils.generate_uuid()
        self.ops = self.get_context(project_id=project_id, roles=['dns_ops'])
        self.zonemaster = self.get_context(project_id=project_id,
                                           roles=['dns_zonemaster'])

    def _import(self, context, body, force=False):
        zone_import = self.central_service.create_zone_import(
            context, ZONEFILE.format(body=body), force=force)
        return self.wait_for_import(zone_import.id, error_is_ok=True)

    def _rrsets(self, zone_id):
        rrsets = self.storage.find_recordsets(
            self.admin_context_all_tenants, {'zone_id': zone_id})
        return {(r.name, r.type): r for r in rrsets}

    def test_zonemaster_can_force_import_own_zone(self):
        self.policy(dict(OWNER_FORCE_ONLY_RULES))
        first = self._import(self.ops, 'www 300 IN A 192.0.2.1')
        self.assertEqual('COMPLETE', first.status, first.message)

        result = self._import(
            self.zonemaster, 'www 300 IN A 192.0.2.2', force=True)

        self.assertEqual('COMPLETE', result.status, result.message)
        rrset = self._rrsets(first.zone_id)[('www.example.com.', 'A')]
        self.assertEqual(['192.0.2.2'], [r.data for r in rrset.records])

    def test_zonemaster_cannot_plain_import(self):
        self.policy(dict(OWNER_FORCE_ONLY_RULES))

        exc = self.assertRaises(
            rpc_dispatcher.ExpectedException,
            self.central_service.create_zone_import,
            self.zonemaster, ZONEFILE.format(body=''))
        self.assertEqual(exceptions.Forbidden, exc.exc_info[0])

    def test_zonemaster_cannot_create_zone_by_force_import(self):
        self.policy(dict(OWNER_FORCE_ONLY_RULES))

        result = self._import(
            self.zonemaster, 'www 300 IN A 192.0.2.1', force=True)

        self.assertEqual('ERROR', result.status)
        self.assertEqual('Failed to create zone - Forbidden', result.message)
        self.assertRaises(
            exceptions.ZoneNotFound, self.storage.find_zone,
            self.admin_context_all_tenants, {'name': 'example.com.'})

    def test_unchanged_recordsets_need_no_permission(self):
        body = 'www 300 IN A 192.0.2.1\nmail 300 IN A 192.0.2.25'
        rules = dict(OWNER_FORCE_ONLY_RULES)
        self.policy(dict(rules))
        first = self._import(self.ops, body)
        rules.update(NO_A_UPDATES)
        self.policy(dict(rules))
        result = self._import(
            self.zonemaster, body + '\nnew 300 IN A 192.0.2.3', force=True)

        self.assertEqual('COMPLETE', result.status, result.message)
        self.assertIn(('new.example.com.', 'A'), self._rrsets(first.zone_id))

    def test_forbidden_change_is_reported_and_rolled_back(self):
        rules = dict(OWNER_FORCE_ONLY_RULES)
        self.policy(dict(rules))
        first = self._import(
            self.ops, 'www 300 IN A 192.0.2.1\nold 300 IN A 192.0.2.9')

        rules.update(NO_A_UPDATES)
        self.policy(dict(rules))
        result = self._import(
            self.zonemaster, 'www 300 IN A 192.0.2.2', force=True)

        self.assertEqual('ERROR', result.status)
        self.assertEqual(
            'Not allowed to update the A recordset www.example.com.',
            result.message)
        rrsets = self._rrsets(first.zone_id)
        self.assertIn(('old.example.com.', 'A'), rrsets)
        self.assertEqual(['192.0.2.1'],
                         [r.data for r in
                          rrsets[('www.example.com.', 'A')].records])
