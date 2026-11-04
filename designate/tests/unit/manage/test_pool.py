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

import fixtures
import oslotest.base

from designate.manage import pool
from designate import objects


class TestManagePool(oslotest.base.BaseTestCase):
    def setUp(self):
        super().setUp()
        self.pool_cmd = pool.PoolCommands()

    @mock.patch.object(pool.policy, 'init')
    def test_update_zones_keeps_zone_masters(self, mock_policy_init):
        primary_zone = objects.Zone.from_dict({
            'name': 'example.com.',
            'type': 'PRIMARY',
            'email': 'example@example.com',
        })
        secondary_zone = objects.Zone.from_dict({
            'name': 'example.org.',
            'type': 'SECONDARY',
            'masters': [{'host': '192.0.2.50', 'port': 53}],
        })
        primary_zone.obj_reset_changes(recursive=True)
        secondary_zone.obj_reset_changes(recursive=True)

        target_pool = objects.Pool.from_dict({
            'id': '794ccc2c-d751-44fe-b57f-8894c9f5c842',
            'targets': [{
                'masters': [{'host': '192.0.2.10', 'port': 5354}],
            }],
        })

        self.pool_cmd.context = mock.Mock()
        with mock.patch.object(
                self.pool_cmd, 'central_api') as mock_central_api:
            mock_central_api.find_zones.return_value = objects.ZoneList(
                objects=[primary_zone, secondary_zone]
            )

            self.pool_cmd._update_zones(target_pool)

        mock_central_api.find_zones.assert_called_once_with(
            self.pool_cmd.context, criterion={'pool_id': target_pool.id}
        )

        # The zones are updated, but their masters are not changed.
        mock_central_api.update_zone.assert_has_calls([
            mock.call(self.pool_cmd.context, primary_zone),
            mock.call(self.pool_cmd.context, secondary_zone),
        ])
        self.assertNotIn('masters', primary_zone.obj_what_changed())
        self.assertNotIn('masters', secondary_zone.obj_what_changed())
        self.assertEqual(
            [('192.0.2.50', 53)],
            [(master.host, master.port) for master in secondary_zone.masters]
        )

    @mock.patch('yaml.dump')
    @mock.patch('builtins.open')
    def test_write_config_to_file(self, mock_open, mock_yaml_dump):
        pool.PoolCommands._write_config_to_file('filename', 'data')

        mock_open.assert_called_with('filename', 'w')
        mock_yaml_dump.assert_called_with(
            'data', mock.ANY, default_flow_style=False
        )


class TestManagePoolZoneUpdates(oslotest.base.BaseTestCase):
    """designate-manage pool update only updates zones for new targets."""

    def setUp(self):
        super().setUp()
        self.pool_cmd = pool.PoolCommands()
        self.pool_cmd.dry_run = False
        self.pool_cmd.central_api = mock.Mock()
        self.pool_cmd.central_api.update_pool.side_effect = (
            lambda context, updated_pool: updated_pool
        )
        self.mock_update_zones = self.useFixture(fixtures.MockPatchObject(
            pool.PoolCommands, '_update_zones')).mock
        self.useFixture(fixtures.MockPatchObject(
            pool.PoolCommands, '_validate_pool'))

    @staticmethod
    def _target(rndc_host='192.0.2.3', masters=('192.0.2.1', '192.0.2.2')):
        return {
            'type': 'bind9',
            'masters': [{'host': host, 'port': 5354} for host in masters],
            'options': {'rndc_host': rndc_host, 'rndc_port': 953},
        }

    def _existing_pool(self, targets):
        return objects.Pool.from_dict({
            'id': '1',
            'name': 'test-pool',
            'description': 'Test pool',
            'ns_records': [{'hostname': 'ns1.example.com.', 'priority': 1}],
            'attributes': {'type': 'internal'},
            'targets': [
                {
                    'type': target['type'],
                    'masters': target['masters'],
                    'options': [
                        {'key': key, 'value': str(value)}
                        for key, value in target['options'].items()
                    ],
                }
                for target in targets
            ],
        })

    def _update_pool(self, existing_targets, targets, **pool_data):
        pool_data.setdefault('name', 'test-pool')
        pool_data.setdefault(
            'ns_records', [{'hostname': 'ns1.example.com.', 'priority': 1}]
        )
        pool_data['targets'] = targets
        self.pool_cmd._update_pool(
            pool_data, self._existing_pool(existing_targets)
        )

    def test_update_pool_without_target_changes(self):
        self._update_pool(
            [self._target()], [self._target()],
            name='renamed-pool',
            description='Renamed pool',
            attributes={'type': 'external'},
            also_notifies=[{'host': '192.0.2.4', 'port': 53}],
        )

        self.pool_cmd.central_api.update_pool.assert_called_once()
        updated_pool = self.pool_cmd.central_api.update_pool.call_args[0][1]
        self.assertEqual('renamed-pool', updated_pool.name)
        self.assertEqual('external', updated_pool.attributes[0].value)
        self.mock_update_zones.assert_not_called()

    def test_update_pool_with_reordered_targets(self):
        # Same targets, masters and options in another order.
        existing_targets = [
            self._target(rndc_host='192.0.2.3'),
            self._target(rndc_host='192.0.2.13'),
        ]
        targets = [
            self._target(rndc_host='192.0.2.13',
                         masters=('192.0.2.2', '192.0.2.1')),
            self._target(rndc_host='192.0.2.3',
                         masters=('192.0.2.2', '192.0.2.1')),
        ]

        self._update_pool(existing_targets, targets)

        self.mock_update_zones.assert_not_called()

    def test_update_pool_with_new_masters(self):
        self._update_pool(
            [self._target()],
            [self._target(masters=('192.0.2.1', '192.0.2.20'))],
        )

        self.mock_update_zones.assert_called_once()
        updated_pool = self.mock_update_zones.call_args[0][0]
        self.assertEqual(
            ['192.0.2.1', '192.0.2.20'],
            [master.host for master in updated_pool.targets[0].masters]
        )

    def test_update_pool_with_new_target(self):
        self._update_pool(
            [self._target()],
            [self._target(), self._target(rndc_host='192.0.2.13')],
        )

        self.mock_update_zones.assert_called_once()

    def test_update_pool_with_changed_target_options(self):
        self._update_pool(
            [self._target()], [self._target(rndc_host='192.0.2.13')],
        )

        self.mock_update_zones.assert_called_once()

    def test_update_pool_with_changed_target_type(self):
        target = self._target()
        target['type'] = 'pdns4'

        self._update_pool([self._target()], [target])

        self.mock_update_zones.assert_called_once()

    def test_update_pool_dry_run(self):
        self.pool_cmd.dry_run = True

        self._update_pool(
            [self._target()],
            [self._target(masters=('192.0.2.1', '192.0.2.20'))],
        )

        self.pool_cmd.central_api.update_pool.assert_not_called()
        self.mock_update_zones.assert_not_called()
