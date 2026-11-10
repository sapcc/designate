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

from unittest import mock

import oslotest.base

from designate.central import service
from designate.common import profiler
from designate import exceptions
from designate import heartbeat_emitter
from designate import objects
from designate import policy
from designate import rpc

ZONE_ID = '3b8ee6dc-35ee-4ce1-8c80-8cbf75bba0f2'
POOL_ID = '794ccc2c-d751-44fe-b57f-8894c9f5c842'
OTHER_POOL_ID = 'c9b6f4a3-2a5e-4f0e-9a4b-3c2d1e0f9a8b'


class SyncZoneTestCase(oslotest.base.BaseTestCase):
    @mock.patch.object(heartbeat_emitter, 'get_heartbeat_emitter')
    @mock.patch.object(policy, 'init')
    @mock.patch.object(rpc, 'init')
    @mock.patch.object(rpc, 'initialized')
    @mock.patch.object(profiler, 'setup_profiler')
    def setUp(self, mock_setup_profiler, mock_rpc_initialized,
              mock_rpc_init, mock_policy_init, mock_heartbeat):
        super().setUp()
        mock_rpc_initialized.return_value = False
        self.storage = mock.Mock()
        self.service = service.Service()
        # MagicMock, the zone lock is used as a context manager
        self.service.coordination = mock.MagicMock()
        self.service._storage = self.storage
        self.context = mock.Mock()
        self.context.project_id = 'test-project-id'

    def _make_zone(self, **values):
        values.setdefault('name', 'example.com.')
        values.setdefault('type', 'PRIMARY')
        zone = objects.Zone(serial=1, action='NONE', **values)
        zone.id = ZONE_ID
        zone.tenant_id = 'test-project-id'
        zone.pool_id = POOL_ID
        return zone

    def _make_rrset(self, name='www.example.com.', rrtype='A',
                    data=('192.0.2.1',), ttl=300, managed=False):
        rrset = objects.RecordSet(
            name=name, type=rrtype,
            records=objects.RecordList(objects=[
                objects.Record(data=value, managed=managed)
                for value in data]))
        # ttl=None stands for a zonefile TTL of 0, which is left unset
        if ttl:
            rrset.ttl = ttl
        return rrset


@mock.patch('designate.storage.sql.get_write_session')
class CreateOrSyncZoneTestCase(SyncZoneTestCase):

    def setUp(self):
        super().setUp()
        self.incoming_zone = self._make_zone()
        self.existing_zone = self._make_zone()

    @mock.patch.object(policy, 'check')
    def test_creates_zone_when_not_existing(self, mock_check,
                                            mock_get_write_session):
        self.storage.find_zone.side_effect = exceptions.ZoneNotFound

        with mock.patch.object(self.service, 'create_zone',
                               return_value=self.incoming_zone) as create:
            self.service._create_or_sync_zone(self.context,
                                              self.incoming_zone)

        mock_check.assert_called_once_with(
            'create_zone_import', self.context, mock.ANY)
        create.assert_called_once_with(self.context, self.incoming_zone)

    @mock.patch.object(policy, 'check')
    def test_creating_a_zone_needs_create_zone_import(
            self, mock_check, mock_get_write_session):
        # create_force_zone_import alone only allows to update zones
        self.storage.find_zone.side_effect = exceptions.ZoneNotFound
        mock_check.side_effect = exceptions.Forbidden

        with mock.patch.object(self.service, 'create_zone') as create:
            self.assertRaises(
                exceptions.Forbidden, self.service._create_or_sync_zone,
                self.context, self.incoming_zone)

        create.assert_not_called()

    def test_syncs_existing_zone(self, mock_get_write_session):
        self.storage.find_zone.return_value = self.existing_zone
        delta = mock.Mock()

        with mock.patch.object(self.service, 'create_zone') as create:
            with mock.patch.object(self.service, '_build_sync_zone_delta',
                                   return_value=delta) as build:
                with mock.patch.object(self.service, '_apply_sync_zone_delta',
                                       return_value=self.existing_zone
                                       ) as apply:
                    result = self.service._create_or_sync_zone(
                        self.context, self.incoming_zone)

        # The transaction passes on deep copies of the arguments, and their
        # equality depends on the set order of the changed fields
        build.assert_called_once()
        self.assertEqual(self.existing_zone.id, build.call_args.args[1].id)
        apply.assert_called_once_with(mock.ANY, mock.ANY, delta)
        create.assert_not_called()
        self.assertIs(self.existing_zone, result)

    def _assert_rejected(self, exception, message=None):
        self.storage.find_zone.return_value = self.existing_zone

        with mock.patch.object(self.service, '_sync_zone') as sync:
            exc = self.assertRaises(
                exception, self.service._create_or_sync_zone,
                self.context, self.incoming_zone)

        sync.assert_not_called()
        if message:
            self.assertEqual(message, str(exc))

    def test_shared_project_is_forbidden(self, mock_get_write_session):
        # find_zone finds shared zones too, only the owner may overwrite
        self.existing_zone.tenant_id = 'owner-project-id'
        self._assert_rejected(exceptions.Forbidden)

    def test_secondary_zone_is_rejected(self, mock_get_write_session):
        self.existing_zone.type = 'SECONDARY'
        self._assert_rejected(
            exceptions.ZoneImportError,
            'Cannot force import into a non-PRIMARY zone.')

    def test_zone_being_deleted_is_rejected(self, mock_get_write_session):
        self.existing_zone.action = 'DELETE'
        self._assert_rejected(
            exceptions.ZoneImportError,
            'Cannot force import into a zone that is being deleted.')

    def test_zone_in_another_pool_is_rejected(self, mock_get_write_session):
        self.incoming_zone.attributes = objects.ZoneAttributeList(objects=[
            objects.ZoneAttribute(key='pool_id', value=OTHER_POOL_ID)])
        self._assert_rejected(
            exceptions.ZoneImportError,
            'Zone already exists in a different pool. '
            'Use pool_move_zone to migrate.')

    def test_same_pool_is_accepted(self, mock_get_write_session):
        self.incoming_zone.attributes = objects.ZoneAttributeList(objects=[
            objects.ZoneAttribute(key='pool_id', value=POOL_ID)])
        self.storage.find_zone.return_value = self.existing_zone

        with mock.patch.object(self.service, '_sync_zone') as sync:
            self.service._create_or_sync_zone(self.context,
                                              self.incoming_zone)

        sync.assert_called_once_with(
            self.context, self.existing_zone, self.incoming_zone)


class BuildSyncZoneDeltaTestCase(SyncZoneTestCase):

    def _delta(self, existing, incoming):
        self.storage.find_recordsets.return_value = objects.RecordSetList(
            objects=existing)
        zone = self._make_zone()
        incoming_zone = self._make_zone()
        incoming_zone.recordsets = objects.RecordSetList(objects=incoming)
        return self.service._build_sync_zone_delta(
            self.context, zone, incoming_zone)

    def test_new_rrset_goes_to_create(self):
        rrset = self._make_rrset()

        delta = self._delta([], [rrset])

        self.assertEqual(
            {'to_create': [rrset], 'to_update': [], 'to_delete': []}, delta)

    def test_removed_rrset_goes_to_delete(self):
        rrset = self._make_rrset()

        delta = self._delta([rrset], [])

        self.assertEqual(
            {'to_create': [], 'to_update': [], 'to_delete': [rrset]}, delta)

    def test_changed_rrset_goes_to_update(self):
        existing = self._make_rrset(data=('192.0.2.1',))

        delta = self._delta([existing],
                            [self._make_rrset(data=('192.0.2.2',))])

        self.assertEqual(
            {'to_create': [], 'to_update': [existing], 'to_delete': []}, delta)
        self.assertEqual(['192.0.2.2'], [r.data for r in existing.records])

    def test_unchanged_rrset_is_left_alone(self):
        delta = self._delta([self._make_rrset()], [self._make_rrset()])

        self.assertEqual(
            {'to_create': [], 'to_update': [], 'to_delete': []}, delta)

    def test_updated_rrset_carries_only_the_changes(self):
        # Like the ones find_recordsets returns, all fields are marked as
        # changed. update_recordset refuses e.g. a changed tenant_id.
        existing = self._make_rrset(data=('192.0.2.1',))
        existing.tenant_id = 'test-project-id'
        existing.zone_id = ZONE_ID

        delta = self._delta([existing],
                            [self._make_rrset(data=('192.0.2.2',))])

        self.assertEqual([existing], delta['to_update'])
        self.assertEqual({'records'}, set(existing.obj_get_changes()))

    def test_protected_rrsets_are_never_touched(self):
        # SOA, apex NS and managed recordsets survive a force import
        delta = self._delta([
            self._make_rrset('example.com.', 'SOA'),
            self._make_rrset('example.com.', 'NS'),
            self._make_rrset('vm.example.com.', 'A', managed=True),
        ], [
            self._make_rrset('vm.example.com.', 'A', data=('192.0.2.2',)),
        ])

        self.assertEqual(
            {'to_create': [], 'to_update': [], 'to_delete': []}, delta)

    def test_delegation_ns_is_synced(self):
        # Only the apex NS recordset is protected
        rrset = self._make_rrset('sub.example.com.', 'NS',
                                 data=('ns1.example.org.',))

        delta = self._delta([rrset], [])

        self.assertEqual([rrset], delta['to_delete'])


class ApplyIncomingRecordsTestCase(SyncZoneTestCase):

    def _apply(self, rrset, incoming):
        return self.service._apply_incoming_records(rrset, incoming)

    def test_identical_records_are_no_change(self):
        rrset = self._make_rrset(data=('192.0.2.1',))

        self.assertFalse(
            self._apply(rrset, self._make_rrset(data=('192.0.2.1',))))

    def test_changed_record_value(self):
        rrset = self._make_rrset(data=('192.0.2.1',))

        self.assertTrue(
            self._apply(rrset, self._make_rrset(data=('192.0.2.2',))))
        self.assertEqual(['192.0.2.2'], [r.data for r in rrset.records])

    def test_added_record_is_appended(self):
        rrset = self._make_rrset(data=('192.0.2.1',))

        self.assertTrue(self._apply(
            rrset, self._make_rrset(data=('192.0.2.1', '192.0.2.2'))))
        self.assertEqual(['192.0.2.1', '192.0.2.2'],
                         [r.data for r in rrset.records])

    def test_removed_record_is_dropped(self):
        rrset = self._make_rrset(data=('192.0.2.1', '192.0.2.2'))

        self.assertTrue(
            self._apply(rrset, self._make_rrset(data=('192.0.2.1',))))
        self.assertEqual(['192.0.2.1'], [r.data for r in rrset.records])

    def test_changed_ttl_alone_is_a_change(self):
        rrset = self._make_rrset(ttl=300)

        self.assertTrue(self._apply(rrset, self._make_rrset(ttl=600)))
        self.assertEqual(600, rrset.ttl)

    def test_missing_ttl_means_the_zone_ttl(self):
        # Like for a new recordset: TTL 0 in the zonefile leaves the TTL unset
        rrset = self._make_rrset(ttl=300)

        self.assertTrue(self._apply(rrset, self._make_rrset(ttl=None)))
        self.assertIsNone(rrset.ttl)

    def test_unchanged_records_keep_their_objects(self):
        # So storage updates them instead of deleting and creating them
        rrset = self._make_rrset(data=('192.0.2.1',))
        record = rrset.records[0]

        self._apply(rrset, self._make_rrset(data=('192.0.2.1', '192.0.2.2')))

        self.assertIs(record, rrset.records[0])


class ApplySyncZoneDeltaTestCase(SyncZoneTestCase):

    def setUp(self):
        super().setUp()
        self.zone = self._make_zone()
        self.updated_zone = self._make_zone()
        self.methods = mock.Mock()
        self.methods._update_zone_in_storage.return_value = self.updated_zone
        for name in ('create_recordset', 'update_recordset',
                     'delete_recordset', '_update_zone_in_storage'):
            patcher = mock.patch.object(self.service, name,
                                        getattr(self.methods, name))
            patcher.start()
            self.addCleanup(patcher.stop)

    def _apply(self, to_create=(), to_update=(), to_delete=()):
        return self.service._apply_sync_zone_delta(
            self.context, self.zone,
            {'to_create': list(to_create), 'to_update': list(to_update),
             'to_delete': list(to_delete)})

    def test_empty_delta_changes_nothing(self):
        # Neither a serial increase nor a NOTIFY to the secondaries
        result = self._apply()

        self.assertEqual([], self.methods.mock_calls)
        self.assertIs(self.zone, result)

    def test_changes_go_through_the_public_methods(self):
        # So the recordset policies apply to the import as well
        new = self._make_rrset('new.example.com.')
        changed = self._make_rrset('changed.example.com.')
        old = self._make_rrset('old.example.com.')
        old.id = 'a6f8e3a9-07a0-4e4b-bf6e-5b5ae6b1a8a3'

        result = self._apply([new], [changed], [old])

        self.assertEqual([
            mock.call.delete_recordset(
                self.context, self.zone.id, old.id, increment_serial=False),
            mock.call.update_recordset(
                self.context, changed, increment_serial=False),
            mock.call.create_recordset(
                self.context, self.zone.id, new, increment_serial=False),
            # The serial is increased once, at the end
            mock.call._update_zone_in_storage(self.context, self.zone),
        ], self.methods.mock_calls)
        self.assertIs(self.updated_zone, result)

    def test_forbidden_change_names_action_and_type(self):
        self.methods.update_recordset.side_effect = exceptions.Forbidden

        exc = self.assertRaises(
            exceptions.ZoneImportError, self._apply,
            to_update=[self._make_rrset(rrtype='MX', data=('10 mx.',))])

        self.assertEqual('Not allowed to update a recordset of type MX.',
                         str(exc))
        self.methods._update_zone_in_storage.assert_not_called()
