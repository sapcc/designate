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


class ZoneImportForceTestBase(designate.tests.functional.TestCase):

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

    def _data(self, zone_id):
        return {key: sorted(record.data for record in rrset.records)
                for key, rrset in self._rrsets(zone_id).items()}


class ZoneImportForceTest(ZoneImportForceTestBase):

    def setUp(self):
        super().setUp()
        self.context = self.get_context(
            project_id=uuidutils.generate_uuid(), roles=['member', 'reader'])

    def test_new_zone_is_created(self):
        result = self._import('www 300 IN A 192.0.2.1', force=True)

        self.assertEqual(('COMPLETE', 'example.com. imported'),
                         (result.status, result.message))
        self.assertEqual(['192.0.2.1'],
                         self._data(result.zone_id)[('www.example.com.', 'A')])

    def test_existing_zone_needs_force(self):
        self._import('www 300 IN A 192.0.2.1')

        result = self._import('www 300 IN A 192.0.2.2')

        self.assertEqual(('ERROR', 'Duplicate zone.'),
                         (result.status, result.message))

    def test_zonefile_replaces_recordsets(self):
        first = self._import(
            'www 300 IN A 192.0.2.1\n'
            'www 300 IN A 192.0.2.2\n'
            'old 300 IN A 192.0.2.3\n'
            'txt 300 IN TXT "same"')
        self.assertFalse(self._zone(first.zone_id).increment_serial)

        result = self._import(
            'www 300 IN A 192.0.2.2\n'
            'www 300 IN A 192.0.2.4\n'
            'new 300 IN A 192.0.2.5\n'
            'txt 300 IN TXT "same"', force=True)

        self.assertEqual('COMPLETE', result.status, result.message)
        self.assertEqual(first.zone_id, result.zone_id)
        data = self._data(first.zone_id)
        self.assertEqual(['192.0.2.2', '192.0.2.4'],
                         data[('www.example.com.', 'A')])
        self.assertEqual(['192.0.2.5'], data[('new.example.com.', 'A')])
        self.assertNotIn(('old.example.com.', 'A'), data)
        zone = self._zone(first.zone_id)
        self.assertEqual(('UPDATE', 'PENDING'), (zone.action, zone.status))
        self.assertTrue(zone.increment_serial)

    def test_changed_ttl_is_applied(self):
        first = self._import('www 300 IN A 192.0.2.1')
        result = self._import('www 3600 IN A 192.0.2.1', force=True)

        self.assertEqual('COMPLETE', result.status, result.message)
        rrset = self._rrsets(first.zone_id)[('www.example.com.', 'A')]
        self.assertEqual(3600, rrset.ttl)

    def test_ttl_0_means_the_zone_ttl(self):
        # Like for a new recordset
        first = self._import('www 300 IN A 192.0.2.1')
        result = self._import('www 0 IN A 192.0.2.1', force=True)

        self.assertEqual('COMPLETE', result.status, result.message)
        rrset = self._rrsets(first.zone_id)[('www.example.com.', 'A')]
        self.assertIsNone(rrset.ttl)

    def test_unchanged_records_are_not_recreated(self):
        body = 'www 300 IN A 192.0.2.1\nwww 300 IN A 192.0.2.2'
        first = self._import(body)
        before = self._rrsets(first.zone_id)[('www.example.com.', 'A')]

        self._import(body.replace('192.0.2.2', '192.0.2.3'), force=True)

        after = self._rrsets(first.zone_id)[('www.example.com.', 'A')]
        kept = [r.id for r in before.records if r.data == '192.0.2.1']
        self.assertEqual(kept, [r.id for r in after.records
                                if r.data == '192.0.2.1'])

    def test_identical_zonefile_does_not_bump_serial(self):
        body = 'www 300 IN A 192.0.2.1'
        first = self._import(body)
        self.assertFalse(self._zone(first.zone_id).increment_serial)

        result = self._import(body, force=True)

        self.assertEqual('COMPLETE', result.status, result.message)
        self.assertFalse(self._zone(first.zone_id).increment_serial)

    def test_failed_sync_leaves_zone_untouched(self):
        # SOA + NS + 3 recordsets = 5
        first = self._import(
            'www 300 IN A 192.0.2.1\n'
            'a1 300 IN A 192.0.2.2\n'
            'a2 300 IN A 192.0.2.3')
        self.config(quota_zone_recordsets=5)

        # www is deleted, the second create exceeds the quota
        result = self._import(
            'a1 300 IN A 192.0.2.2\n'
            'a2 300 IN A 192.0.2.3\n'
            'n1 300 IN A 192.0.2.4\n'
            'n2 300 IN A 192.0.2.5', force=True)

        self.assertEqual(('ERROR', 'Quota exceeded during zone import.'),
                         (result.status, result.message))
        rrsets = self._rrsets(first.zone_id)
        self.assertIn(('www.example.com.', 'A'), rrsets,
                      'zone was half-synced: www already deleted')
        self.assertNotIn(('n1.example.com.', 'A'), rrsets)

    def test_force_import_update_exception_rolled_back(self):
        first = self._import('www 300 IN A 192.0.2.1\nold 300 IN A 192.0.2.9')

        original = self.central_service.storage.update_recordset
        call_count = 0

        def fail_on_second(context, rrset):
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                raise exceptions.BadRequest('Simulated failure')
            return original(context, rrset)

        with mock.patch.object(
                self.central_service.storage,
                'update_recordset',
                side_effect=fail_on_second):
            result = self._import(
                'www 300 IN A 192.0.2.2\nold 300 IN A 192.0.2.99',
                force=True)

        self.assertEqual('ERROR', result.status)
        # Both recordsets must be in their original state due to the
        # @transaction rollback on _sync_zone.
        data = self._data(first.zone_id)
        self.assertEqual(['192.0.2.1'], data[('www.example.com.', 'A')])
        self.assertEqual(['192.0.2.9'], data[('old.example.com.', 'A')])

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

        # An exported zonefile contains the managed recordset as well
        result = self._import(
            'www 300 IN A 192.0.2.1\nvm 3600 IN A 192.0.2.10', force=True)
        self.assertEqual('COMPLETE', result.status, result.message)
        # A zonefile without it does not delete it
        result = self._import('www 300 IN A 192.0.2.1', force=True)
        self.assertEqual('COMPLETE', result.status, result.message)

        self.assertEqual(['192.0.2.10'],
                         self._data(first.zone_id)[('vm.example.com.', 'A')])

    def test_zone_being_deleted_keeps_delete_action(self):
        first = self._import('www 300 IN A 192.0.2.1')
        self.central_service.delete_zone(self.context, first.zone_id)
        self.assertEqual('DELETE', self._zone(first.zone_id).action)

        result = self._import('www 300 IN A 192.0.2.2', force=True)

        self.assertEqual(
            ('ERROR', 'Cannot force import into a zone that is being '
                      'deleted.'),
            (result.status, result.message))
        self.assertEqual('DELETE', self._zone(first.zone_id).action)

    def test_secondary_zone_is_rejected(self):
        zone = self.create_zone(
            context=self.context, type='SECONDARY', name='example.com.',
            email='root@example.com',
            masters=[{'host': '192.0.2.53', 'port': 53}])

        result = self._import('www 300 IN A 192.0.2.1', force=True)

        self.assertEqual(
            ('ERROR', 'Cannot force import into a non-PRIMARY zone.'),
            (result.status, result.message))
        self.assertNotIn(('www.example.com.', 'A'), self._rrsets(zone.id))
        self.assertFalse(self._zone(zone.id).increment_serial)

    def test_recordset_owned_by_shared_project(self):
        first = self._import('www 300 IN A 192.0.2.1')
        other = self.get_context(project_id=uuidutils.generate_uuid(),
                                 roles=['member', 'reader'])
        self.share_zone(context=self.context, zone_id=first.zone_id,
                        target_project_id=other.project_id)
        for name in ('shared.example.com.', 'gone.example.com.'):
            self.central_service.create_recordset(
                other, first.zone_id, objects.RecordSet(
                    name=name, type='A', records=objects.RecordList(
                        objects=[objects.Record(data='192.0.2.9')])))

        # The owner imports a file with another address for "shared" and
        # without "gone"
        result = self._import(
            'www 300 IN A 192.0.2.1\nshared 300 IN A 192.0.2.10', force=True)

        self.assertEqual('COMPLETE', result.status, result.message)
        data = self._data(first.zone_id)
        self.assertEqual(['192.0.2.10'], data[('shared.example.com.', 'A')])
        self.assertNotIn(('gone.example.com.', 'A'), data)

    def test_shared_project_cannot_force_import_owner_zone(self):
        first = self._import('www 300 IN A 192.0.2.1')
        other = self.get_context(project_id=uuidutils.generate_uuid(),
                                 roles=['member', 'reader'])
        self.share_zone(context=self.context, zone_id=first.zone_id,
                        target_project_id=other.project_id)

        result = self._import('evil 300 IN A 192.0.2.66', force=True,
                              context=other)

        self.assertEqual(('ERROR', 'Not allowed to import the zone.'),
                         (result.status, result.message))
        self.assertNotIn(('evil.example.com.', 'A'),
                         self._rrsets(first.zone_id))
        self.assertFalse(self._zone(first.zone_id).increment_serial)

    def test_requested_pool_differs_from_existing_zone_pool(self):
        first = self._import('www 300 IN A 192.0.2.1')
        pool = self.create_pool(tenant_id=self.context.project_id)
        self.policy({'zone_create_forced_pool': '@'})

        attributes = objects.ZoneAttributeList(objects=[
            objects.ZoneAttribute(key='pool_id', value=pool.id)])
        result = self._import('www 300 IN A 192.0.2.2', force=True,
                              attributes=attributes)

        self.assertEqual(
            ('ERROR', 'Zone already exists in a different pool. '
                      'Use pool_move_zone to migrate.'),
            (result.status, result.message))
        self.assertNotEqual(pool.id, self._zone(first.zone_id).pool_id)
        self.assertEqual(['192.0.2.1'],
                         self._data(first.zone_id)[('www.example.com.', 'A')])

    @mock.patch('designate.central.service.Service._create_or_sync_zone')
    def test_long_error_message_does_not_leave_import_pending(
            self, mock_sync):
        # A message longer than 160 characters cannot be stored
        for exc, message in (
                (exceptions.BadRequest('x' * 500),
                 'An undefined error occurred. ' + 'x' * 130),
                (exceptions.Forbidden('x' * 500),
                 'Not allowed to import the zone.')):
            mock_sync.side_effect = exc

            result = self._import('www 300 IN A 192.0.2.1', force=True)

            self.assertEqual(('ERROR', message),
                             (result.status, result.message))

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


# Like in production: operators import (that is, create) zones, zone owners
# may only force import their zones. The operator rules do not accept
# role:admin, so context.elevated() does not satisfy them either.
OPS = 'role:dns_ops'
OWNER_FORCE_ONLY_RULES = {
    'create_zone': OPS,
    'create_zone_import': OPS,
    'update_zone_import': OPS,
    'create_force_zone_import': (
        'role:dns_zonemaster and project_id:%(project_id)s'),
}
# With the per-type recordset rules (PATCH-017) the A or MX rule applies
NO_A_UPDATES = {'update_recordset': '!', 'update_A_recordset': '!'}
NO_MX_DELETES = {'delete_recordset': '!', 'delete_MX_recordset': '!'}


class ZoneImportForcePolicyTest(ZoneImportForceTestBase):

    def setUp(self):
        super().setUp()
        project_id = uuidutils.generate_uuid()
        # Imports without a context are done by the operator
        self.context = self.get_context(project_id=project_id,
                                        roles=['dns_ops'])
        self.zonemaster = self.get_context(project_id=project_id,
                                           roles=['dns_zonemaster'])
        self.policy(dict(OWNER_FORCE_ONLY_RULES))

    def test_zonemaster_can_force_import_own_zone(self):
        first = self._import('www 300 IN A 192.0.2.1')
        self.assertEqual('COMPLETE', first.status, first.message)

        result = self._import('www 300 IN A 192.0.2.2', force=True,
                              context=self.zonemaster)

        self.assertEqual('COMPLETE', result.status, result.message)
        self.assertEqual(['192.0.2.2'],
                         self._data(first.zone_id)[('www.example.com.', 'A')])

    def test_zonemaster_cannot_plain_import(self):
        exc = self.assertRaises(
            rpc_dispatcher.ExpectedException,
            self.central_service.create_zone_import,
            self.zonemaster, ZONEFILE.format(body=''))
        self.assertEqual(exceptions.Forbidden, exc.exc_info[0])

    def test_zonemaster_cannot_create_zone_by_force_import(self):
        result = self._import('www 300 IN A 192.0.2.1', force=True,
                              context=self.zonemaster)

        self.assertEqual(('ERROR', 'Not allowed to import the zone.'),
                         (result.status, result.message))
        self.assertRaises(
            exceptions.ZoneNotFound, self.storage.find_zone,
            self.admin_context_all_tenants, {'name': 'example.com.'})

    def test_unchanged_recordsets_need_no_permission(self):
        body = 'www 300 IN A 192.0.2.1\nmail 300 IN A 192.0.2.25'
        first = self._import(body)
        self.policy(dict(OWNER_FORCE_ONLY_RULES, **NO_A_UPDATES))

        result = self._import(body + '\nnew 300 IN A 192.0.2.3',
                              force=True, context=self.zonemaster)

        self.assertEqual('COMPLETE', result.status, result.message)
        self.assertIn(('new.example.com.', 'A'), self._rrsets(first.zone_id))

    def test_forbidden_change_is_reported_and_rolled_back(self):
        first = self._import(
            'www 300 IN A 192.0.2.1\nold 300 IN A 192.0.2.9')
        self.policy(dict(OWNER_FORCE_ONLY_RULES, **NO_A_UPDATES))

        # Deletes "old" (allowed) and changes "www" (forbidden)
        result = self._import('www 300 IN A 192.0.2.2', force=True,
                              context=self.zonemaster)

        self.assertEqual(
            ('ERROR', 'Not allowed to update a recordset of type A.'),
            (result.status, result.message))
        data = self._data(first.zone_id)
        self.assertIn(('old.example.com.', 'A'), data)
        self.assertEqual(['192.0.2.1'], data[('www.example.com.', 'A')])

    def test_forbidden_delete_is_reported(self):
        first = self._import(
            'www 300 IN A 192.0.2.1\n'
            'example.com. 300 IN MX 10 mail.example.com.')
        self.policy(dict(OWNER_FORCE_ONLY_RULES, **NO_MX_DELETES))

        result = self._import('www 300 IN A 192.0.2.1', force=True,
                              context=self.zonemaster)

        self.assertEqual(
            ('ERROR', 'Not allowed to delete a recordset of type MX.'),
            (result.status, result.message))
        self.assertIn(('example.com.', 'MX'), self._rrsets(first.zone_id))
