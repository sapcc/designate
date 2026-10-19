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
import designate.conf
from designate import exceptions
from designate import heartbeat_emitter
from designate.objects import zone as zone_module
from designate import policy
from designate import rpc

CONF = designate.conf.CONF

PARENT_ZONE_ID = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'
CHILD_ZONE_ID = 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb'
PROJECT_ID = 'cccccccc-cccc-cccc-cccc-cccccccccccc'


def _make_zone(name, zone_id, tenant_id=PROJECT_ID, zone_type='PRIMARY'):
    z = zone_module.Zone()
    z.id = zone_id
    z.name = name
    z.type = zone_type
    z.tenant_id = tenant_id
    return z


class NameIsWithinZoneTestCase(oslotest.base.BaseTestCase):
    """Unit tests for _is_recordset_name_within_zone.

    The method is a pure string check: returns True if name is the zone apex
    or falls within the zone namespace. Used by both _is_valid_recordset_name
    and _is_valid_recordset_placement_subzone to avoid duplicating the
    endswith logic and the inverted try/except pattern.
    """

    @mock.patch.object(heartbeat_emitter, 'get_heartbeat_emitter')
    @mock.patch.object(policy, 'init')
    @mock.patch.object(rpc, 'init')
    @mock.patch.object(rpc, 'initialized')
    @mock.patch.object(profiler, 'setup_profiler')
    def setUp(self, mock_setup_profiler, mock_rpc_initialized,
              mock_rpc_init, mock_policy_init, mock_heartbeat):
        super().setUp()
        mock_rpc_initialized.return_value = False
        self.svc = service.Service()
        self.svc.coordination = mock.Mock()

    def test_apex_name_is_within_zone(self):
        self.assertTrue(
            self.svc._is_recordset_name_within_zone(
                'example.com.', {'name': 'example.com.'})
        )

    def test_subdomain_is_within_zone(self):
        self.assertTrue(
            self.svc._is_recordset_name_within_zone(
                'ns.sub.example.com.', {'name': 'example.com.'})
        )

    def test_direct_child_is_within_zone(self):
        self.assertTrue(
            self.svc._is_recordset_name_within_zone(
                'sub.example.com.', {'name': 'example.com.'})
        )

    def test_sibling_zone_is_not_within_zone(self):
        # 'other.com.' shares no namespace with 'example.com.'
        self.assertFalse(
            self.svc._is_recordset_name_within_zone(
                'other.com.', {'name': 'example.com.'})
        )

    def test_partial_label_match_is_not_within_zone(self):
        # 'notexample.com.' must not match 'example.com.' via naive suffix check.
        self.assertFalse(
            self.svc._is_recordset_name_within_zone(
                'notexample.com.', {'name': 'example.com.'})
        )


class RecordSetPlacementSubzoneTestCase(oslotest.base.BaseTestCase):
    """Unit tests for _is_valid_recordset_placement_subzone.

    Normal behaviour: raises InvalidRecordSetLocation when a recordset name
    falls within an existing child zone.

    Extended behaviour: callers holding the 'create_delegation_recordset'
    policy may place NS/glue records in the parent zone even when the child
    zone exists. This is required for zero-downtime delegation handover where
    the child zone must remain in Designate while the parent is updated.
    """

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
        self.svc = service.Service()
        self.svc.coordination = mock.Mock()
        self.svc._storage = self.storage

        self.context = mock.Mock()
        self.context.elevated.return_value = self.context

        self.parent_zone = _make_zone('example.com.', PARENT_ZONE_ID)

        # storage.find_zones returns dicts; the method accesses ['name'].
        self.child_zone_dict = {
            'name': 'sub.example.com.',
            'id': CHILD_ZONE_ID,
        }

    def _storage_returns_child_zone(self):
        self.storage.find_zones.return_value = [self.child_zone_dict]

    def _storage_returns_no_child_zones(self):
        self.storage.find_zones.return_value = []

    def test_no_child_zones_does_not_raise(self):
        self._storage_returns_no_child_zones()

        self.svc._is_valid_recordset_placement_subzone(
            self.context, self.parent_zone, 'any.example.com.'
        )

    def test_recordset_name_equals_zone_name_does_not_raise(self):
        # Early-return path: apex name is always valid regardless of children.
        self._storage_returns_child_zone()

        self.svc._is_valid_recordset_placement_subzone(
            self.context, self.parent_zone, 'example.com.'
        )

    def test_raises_when_recordset_belongs_in_child_zone(self):
        # _is_recordset_name_within_zone returning True means the name falls inside the
        # child zone namespace, which is the condition that triggers the error.
        self._storage_returns_child_zone()

        with mock.patch.object(
            self.svc, '_is_recordset_name_within_zone', return_value=True
        ):
            with mock.patch(

                'designate.central.service.policy.check',
                return_value=False,
            ) as mock_policy_check:
                self.assertRaisesRegex(
                    exceptions.InvalidRecordSetLocation,
                    'RecordSet belongs in a child zone: sub.example.com.',
                    self.svc._is_valid_recordset_placement_subzone,
                    self.context, self.parent_zone, 'ns.sub.example.com.',
                )
                mock_policy_check.assert_called_once_with(
                    'create_delegation_recordset',
                    self.context,
                    do_raise=False,
                )

    def test_delegation_policy_allows_recordset_in_child_zone(self):
        # With 'create_delegation_recordset' granted, placing NS/glue in the
        # parent zone must succeed even when the child zone exists.
        self._storage_returns_child_zone()

        with mock.patch.object(
            self.svc, '_is_recordset_name_within_zone', return_value=True
        ):
            with mock.patch(
                'designate.central.service.policy.check',
                return_value=True,
            ) as mock_policy_check:
                self.svc._is_valid_recordset_placement_subzone(
                    self.context, self.parent_zone, 'ns.sub.example.com.',
                )

                mock_policy_check.assert_called_once_with(
                    'create_delegation_recordset',
                    self.context,
                    do_raise=False,
                )

    def test_delegation_policy_denied_still_raises(self):
        # Policy denied -> original restriction applies, exception expected.
        self._storage_returns_child_zone()

        with mock.patch.object(
            self.svc, '_is_recordset_name_within_zone', return_value=True
        ):
            with mock.patch(
                'designate.central.service.policy.check',
                return_value=False,
            ):
                self.assertRaises(
                    exceptions.InvalidRecordSetLocation,
                    self.svc._is_valid_recordset_placement_subzone,
                    self.context, self.parent_zone, 'ns.sub.example.com.',
                )

    def test_too_long_recordset_name_within_child_zone_is_still_blocked(self):
        self._storage_returns_child_zone()

        max_len = CONF['service:central'].max_recordset_name_len
        long_name = 'a' * \
            (max_len - len('.sub.example.com.') + 1) + '.sub.example.com.'

        with mock.patch.object(
            self.svc, '_is_recordset_name_within_zone', return_value=True
        ):
            with mock.patch(
                'designate.central.service.policy.check',
                return_value=False,
            ):
                self.assertRaises(
                    exceptions.InvalidRecordSetLocation,
                    self.svc._is_valid_recordset_placement_subzone,
                    self.context, self.parent_zone, long_name,
                )
