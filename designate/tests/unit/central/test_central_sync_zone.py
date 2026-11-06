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
from designate.objects import zone
from designate import policy
from designate import rpc


@mock.patch('designate.storage.sql.get_write_session')
class CreateOrSyncZoneTestCase(oslotest.base.BaseTestCase):
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
        self.service.coordination = mock.Mock()
        self.service._storage = self.storage
        self.context = mock.Mock()
        self.context.project_id = 'test-project-id'

    def test_create_or_sync_zone_creates_when_not_existing(
            self, mock_get_write_session):
        # When the zone does not exist yet, create_zone must be called.
        incoming_zone = zone.Zone(name='example.com.', type='PRIMARY')
        self.storage.find_zone.side_effect = exceptions.ZoneNotFound

        with mock.patch.object(self.service, 'create_zone',
                               return_value=incoming_zone) as mock_create:
            self.service._create_or_sync_zone(self.context, incoming_zone)

        mock_create.assert_called_once_with(mock.ANY, incoming_zone)

    def test_create_or_sync_zone_syncs_when_existing(
            self, mock_get_write_session):
        # When the zone already exists, delta-build + delta-apply must be
        # called — not create_zone.
        incoming_zone = zone.Zone(name='example.com.', type='PRIMARY')
        existing_zone = zone.Zone(name='example.com.', type='PRIMARY')
        existing_zone.tenant_id = 'test-project-id'
        self.storage.find_zone.return_value = existing_zone
        fake_delta = mock.Mock()

        with mock.patch.object(self.service, 'create_zone') as mock_create, \
             mock.patch.object(self.service, '_build_sync_zone_delta',
                               return_value=fake_delta) as mock_build, \
             mock.patch.object(self.service, '_apply_sync_zone_delta',
                               return_value=existing_zone) as mock_apply:
            self.service._create_or_sync_zone(self.context, incoming_zone)

        mock_build.assert_called_once_with(
            mock.ANY, existing_zone, incoming_zone)
        mock_apply.assert_called_once_with(
            mock.ANY, existing_zone, fake_delta)
        mock_create.assert_not_called()

    def test_create_or_sync_zone_raises_forbidden_for_shared_project(
            self, mock_get_write_session):
        # A project that only has shared access must not be able to sync —
        # tenant_id mismatch between existing zone and context raises Forbidden.
        incoming_zone = zone.Zone(name='example.com.', type='PRIMARY')
        existing_zone = zone.Zone(name='example.com.', type='PRIMARY')
        existing_zone.tenant_id = 'owner-project-id'
        self.context.project_id = 'other-project-id'
        self.storage.find_zone.return_value = existing_zone

        self.assertRaises(
            exceptions.Forbidden,
            self.service._create_or_sync_zone,
            self.context, incoming_zone,
        )


class BuildSyncZoneDeltaTestCase(oslotest.base.BaseTestCase):
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
        self.service.coordination = mock.Mock()
        self.service._storage = self.storage
        self.context = mock.Mock()
        self.context.project_id = 'test-project-id'

    def _make_zone(self, action='NONE'):
        z = zone.Zone(name='example.com.', type='PRIMARY', serial=1)
        z.action = action
        z.tenant_id = 'test-project-id'
        return z

    def _make_rrset(self, name, rrtype, data='192.0.2.1',
                    managed=False, tenant_id='test-project-id'):
        rs = objects.RecordSet(
            name=name, type=rrtype,
            records=objects.RecordList(
                objects=[objects.Record(data=data)]))
        rs.tenant_id = tenant_id
        if managed:
            for r in rs.records:
                r.managed = True
        return rs

    def _storage_returns(self, rrsets):
        self.storage.find_recordsets.return_value = \
            objects.RecordSetList(objects=rrsets)

    def test_raises_bad_request_for_zone_being_deleted(self):
        # Force-importing into a zone with action=DELETE would corrupt state.
        existing_zone = self._make_zone(action='DELETE')
        incoming_zone = self._make_zone()
        self.assertRaises(
            exceptions.BadRequest,
            self.service._build_sync_zone_delta,
            self.context, existing_zone, incoming_zone,
        )

    def test_new_rrset_goes_to_create(self):
        existing_zone = self._make_zone()
        incoming_zone = self._make_zone()
        incoming_zone.recordsets = objects.RecordSetList(objects=[
            self._make_rrset('www.example.com.', 'A'),
        ])
        self._storage_returns([])

        delta = self.service._build_sync_zone_delta(
            self.context, existing_zone, incoming_zone)

        self.assertEqual(1, len(delta['to_create']))
        self.assertEqual(0, len(delta['to_update']))
        self.assertEqual(0, len(delta['to_delete']))

    def test_removed_rrset_goes_to_delete(self):
        existing_zone = self._make_zone()
        incoming_zone = self._make_zone()
        incoming_zone.recordsets = objects.RecordSetList(objects=[])
        self._storage_returns([
            self._make_rrset('www.example.com.', 'A'),
        ])

        delta = self.service._build_sync_zone_delta(
            self.context, existing_zone, incoming_zone)

        self.assertEqual(0, len(delta['to_create']))
        self.assertEqual(0, len(delta['to_update']))
        self.assertEqual(1, len(delta['to_delete']))

    def test_changed_rrset_goes_to_update(self):
        existing_zone = self._make_zone()
        incoming_zone = self._make_zone()
        incoming_zone.recordsets = objects.RecordSetList(objects=[
            self._make_rrset('www.example.com.', 'A', data='192.0.2.2'),
        ])
        self._storage_returns([
            self._make_rrset('www.example.com.', 'A', data='192.0.2.1'),
        ])

        delta = self.service._build_sync_zone_delta(
            self.context, existing_zone, incoming_zone)

        self.assertEqual(0, len(delta['to_create']))
        self.assertEqual(1, len(delta['to_update']))
        self.assertEqual(0, len(delta['to_delete']))

    def test_protected_rrsets_are_never_touched(self):
        # SOA, apex NS and managed records must survive a force-import unchanged.
        existing_zone = self._make_zone()
        incoming_zone = self._make_zone()
        incoming_zone.recordsets = objects.RecordSetList(objects=[])
        self._storage_returns([
            self._make_rrset('example.com.', 'SOA'),
            self._make_rrset('example.com.', 'NS'),
            self._make_rrset('vm.example.com.', 'A', managed=True),
        ])

        delta = self.service._build_sync_zone_delta(
            self.context, existing_zone, incoming_zone)

        self.assertEqual(0, len(delta['to_create']))
        self.assertEqual(0, len(delta['to_update']))
        self.assertEqual(0, len(delta['to_delete']))

    def test_soa_and_apex_ns_not_updated_even_if_incoming_differs(self):
        # Even when the incoming zone contains SOA/NS records, they must not
        # appear in to_update — _is_protected guards the existing side.
        existing_zone = self._make_zone()
        incoming_zone = self._make_zone()
        incoming_zone.recordsets = objects.RecordSetList(objects=[
            self._make_rrset('example.com.', 'SOA'),
            self._make_rrset('example.com.', 'NS'),
        ])
        self._storage_returns([
            self._make_rrset('example.com.', 'SOA'),
            self._make_rrset('example.com.', 'NS'),
        ])

        delta = self.service._build_sync_zone_delta(
            self.context, existing_zone, incoming_zone)

        self.assertEqual(0, len(delta['to_update']))
        self.assertEqual(0, len(delta['to_delete']))
        self.assertEqual(0, len(delta['to_create']))


class ApplyIncomingRecordsTestCase(oslotest.base.BaseTestCase):
    @mock.patch.object(heartbeat_emitter, 'get_heartbeat_emitter')
    @mock.patch.object(policy, 'init')
    @mock.patch.object(rpc, 'init')
    @mock.patch.object(rpc, 'initialized')
    @mock.patch.object(profiler, 'setup_profiler')
    def setUp(self, mock_setup_profiler, mock_rpc_initialized,
              mock_rpc_init, mock_policy_init, mock_heartbeat):
        super().setUp()
        mock_rpc_initialized.return_value = False
        self.service = service.Service()
        self.service.coordination = mock.Mock()

    def _make_rrset(self, *data_values, ttl: int | None = 300):
        # ttl=None is valid for incoming rrsets (means "keep existing TTL")
        rs = objects.RecordSet(
            name='www.example.com.', type='A',
            records=objects.RecordList(
                objects=[objects.Record(data=d) for d in data_values]))
        if ttl is not None:
            rs.ttl = ttl
        return rs

    def test_identical_records_returns_none(self):
        # No change means no update needed — caller skips the storage write.
        existing = self._make_rrset('192.0.2.1', ttl=300)
        incoming = self._make_rrset('192.0.2.1', ttl=300)

        result = self.service._apply_incoming_records(existing, incoming)

        self.assertIsNone(result)

    def test_incoming_ttl_none_still_returns_none_when_records_match(self):
        # ttl=None in incoming means "keep existing TTL" — not a change.
        existing = self._make_rrset('192.0.2.1', ttl=300)
        incoming = self._make_rrset('192.0.2.1', ttl=None)

        result = self.service._apply_incoming_records(existing, incoming)

        self.assertIsNone(result)

    def test_changed_record_value_triggers_update(self):
        # A different IP must cause the rrset to be returned for storage update.
        existing = self._make_rrset('192.0.2.1', ttl=300)
        incoming = self._make_rrset('192.0.2.2', ttl=300)

        result = self.service._apply_incoming_records(existing, incoming)

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual({'192.0.2.2'},
                         {r.data for r in result.records})

    def test_added_record_appended(self):
        # A new IP added to the rrset must appear alongside the existing one.
        existing = self._make_rrset('192.0.2.1', ttl=300)
        incoming = self._make_rrset('192.0.2.1', '192.0.2.2', ttl=300)

        result = self.service._apply_incoming_records(existing, incoming)

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual({'192.0.2.1', '192.0.2.2'},
                         {r.data for r in result.records})

    def test_removed_record_dropped(self):
        # A record absent from the incoming zone must be removed.
        existing = self._make_rrset('192.0.2.1', '192.0.2.2', ttl=300)
        incoming = self._make_rrset('192.0.2.1', ttl=300)

        result = self.service._apply_incoming_records(existing, incoming)

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual({'192.0.2.1'},
                         {r.data for r in result.records})

    def test_ttl_change_alone_triggers_update(self):
        # Changing only the TTL with identical records must still return the rrset.
        existing = self._make_rrset('192.0.2.1', ttl=300)
        incoming = self._make_rrset('192.0.2.1', ttl=600)

        result = self.service._apply_incoming_records(existing, incoming)

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(600, result.ttl)

    def test_incoming_ttl_none_does_not_overwrite_existing_ttl(self):
        # ttl=None signals "unchanged" — the existing TTL must be preserved.
        existing = self._make_rrset('192.0.2.1', ttl=300)
        incoming = self._make_rrset('192.0.2.2', ttl=None)

        result = self.service._apply_incoming_records(existing, incoming)

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(300, result.ttl)

    def test_unchanged_records_reuse_existing_objects(self):
        # Records kept across the sync must be the original objects — so storage
        # updates them in place rather than delete+recreate.
        existing = self._make_rrset('192.0.2.1', ttl=300)
        original_record = list(existing.records)[0]
        incoming = self._make_rrset('192.0.2.1', '192.0.2.2', ttl=300)

        result = self.service._apply_incoming_records(existing, incoming)

        assert result is not None
        kept = [r for r in result.records if r.data == '192.0.2.1']
        self.assertEqual(1, len(kept))
        self.assertIs(original_record, kept[0])


class ApplySyncZoneDeltaTestCase(oslotest.base.BaseTestCase):
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
        self.service.coordination = mock.Mock()
        self.service._storage = self.storage
        self.context = mock.Mock()
        self.elevated_ctx = mock.Mock()
        self.context.elevated.return_value = self.elevated_ctx

    def _make_zone(self):
        z = zone.Zone(name='example.com.', type='PRIMARY', serial=1)
        z.tenant_id = 'test-project-id'
        return z

    def _make_rrset(self, name='www.example.com.', rrtype='A'):
        rs = objects.RecordSet(name=name, type=rrtype,
                               records=objects.RecordList(objects=[
                                   objects.Record(data='192.0.2.1')]))
        return rs

    def _empty_delta(self, zone):
        return {'to_delete': [], 'to_update': [], 'to_create': [],
                'serial': zone.serial}

    def test_empty_delta_does_not_update_zone(self):
        # No changes means no serial bump — avoid a spurious DNS notify.
        existing_zone = self._make_zone()
        delta = self._empty_delta(existing_zone)

        with mock.patch.object(self.service, '_update_zone_in_storage') \
                as mock_update_zone, \
             mock.patch.object(self.service, '_delete_recordset_in_storage'), \
             mock.patch.object(self.service, '_update_recordset_in_storage'), \
             mock.patch.object(self.service, '_create_recordset_in_storage'):
            self.service._apply_sync_zone_delta(
                self.context, existing_zone, delta)

        mock_update_zone.assert_not_called()

    def test_delete_calls_storage_with_elevated_context(self):
        # Elevated context is required so tenant-criteria filters don't reject
        # cross-tenant or managed records during force-import.
        existing_zone = self._make_zone()
        rrset = self._make_rrset()
        delta = {'to_delete': [rrset], 'to_update': [], 'to_create': [],
                 'serial': existing_zone.serial}

        with mock.patch.object(self.service, '_delete_recordset_in_storage') \
                as mock_delete, \
             mock.patch.object(self.service, '_update_zone_in_storage'), \
             mock.patch.object(self.service, '_update_recordset_in_storage'), \
             mock.patch.object(self.service, '_create_recordset_in_storage'):
            self.service._apply_sync_zone_delta(
                self.context, existing_zone, delta)

        mock_delete.assert_called_once_with(
            self.elevated_ctx, existing_zone, rrset, increment_serial=False)

    def test_create_calls_storage_with_elevated_context(self):
        # Same elevated-context requirement as delete — storage must not
        # re-apply tenant criteria on write.
        existing_zone = self._make_zone()
        rrset = self._make_rrset()
        delta = {'to_delete': [], 'to_update': [], 'to_create': [rrset],
                 'serial': existing_zone.serial}

        with mock.patch.object(self.service, '_create_recordset_in_storage') \
                as mock_create, \
             mock.patch.object(self.service, '_update_zone_in_storage'), \
             mock.patch.object(self.service, '_delete_recordset_in_storage'), \
             mock.patch.object(self.service, '_update_recordset_in_storage'):
            self.service._apply_sync_zone_delta(
                self.context, existing_zone, delta)

        mock_create.assert_called_once_with(
            self.elevated_ctx, existing_zone, rrset, increment_serial=False)

    def test_update_calls_storage_with_elevated_context(self):
        # to_update contains already-merged rrsets from _build_sync_zone_delta;
        # _apply_sync_zone_delta must write each directly to storage.
        existing_zone = self._make_zone()
        existing_rrset = self._make_rrset()
        delta = {'to_delete': [], 'to_update': [existing_rrset],
                 'to_create': [], 'serial': existing_zone.serial}

        with mock.patch.object(self.service, '_update_recordset_in_storage') \
                as mock_update, \
             mock.patch.object(self.service, '_update_zone_in_storage'), \
             mock.patch.object(self.service, '_delete_recordset_in_storage'), \
             mock.patch.object(self.service, '_create_recordset_in_storage'):
            self.service._apply_sync_zone_delta(
                self.context, existing_zone, delta)

        mock_update.assert_called_once_with(
            self.elevated_ctx, existing_zone, existing_rrset,
            increment_serial=False)

    def test_serial_bumped_once_and_return_value_is_refreshed_zone(self):
        # Serial must increment exactly once at the end — not per-recordset —
        # and the return value must be the post-commit zone from storage.
        existing_zone = self._make_zone()
        rrset = self._make_rrset()
        refreshed_zone = self._make_zone()
        delta = {'to_delete': [rrset], 'to_update': [], 'to_create': [],
                 'serial': existing_zone.serial}
        self.storage.get_zone.return_value = refreshed_zone

        with mock.patch.object(self.service, '_update_zone_in_storage') \
                as mock_update_zone, \
             mock.patch.object(self.service, '_delete_recordset_in_storage'), \
             mock.patch.object(self.service, '_update_recordset_in_storage'), \
             mock.patch.object(self.service, '_create_recordset_in_storage'):
            result = self.service._apply_sync_zone_delta(
                self.context, existing_zone, delta)

        mock_update_zone.assert_called_once_with(
            self.elevated_ctx, existing_zone, increment_serial=True)
        self.storage.get_zone.assert_called_once_with(
            self.elevated_ctx, existing_zone.id)
        self.assertIs(refreshed_zone, result)
