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


import copy
import os
from unittest import mock
import yaml

from oslo_log import log as logging
import oslo_messaging

from designate.central import service
import designate.conf
from designate import exceptions
from designate.manage import base
from designate.manage import pool
from designate.tests import base_fixtures
import designate.tests.functional
from designate.tests import resources

CONF = designate.conf.CONF
LOG = logging.getLogger(__name__)


def get_pools_path(name='pools.yaml'):
    return os.path.join(resources.path, 'pools_yaml', name)


def get_pools(name='pools.yaml'):
    with open(get_pools_path(name)) as pool_obj:
        return yaml.safe_load(pool_obj)


class ManagePoolTestCase(designate.tests.functional.TestCase):
    def setUp(self):
        super().setUp()
        self.stdlog = base_fixtures.StandardLogging()
        self.useFixture(self.stdlog)

        default_pool = self.central_service.find_pool(
            self.admin_context, {'name': 'default'}
        )
        self.central_service.delete_pool(self.admin_context, default_pool.id)

        self.command = pool.PoolCommands()

        self.print_result = mock.patch.object(
            base.Commands, '_print_result').start()

    def test_show_config(self):
        self.command._setup()
        self.command._create_pool(get_pools()[0])

        pool_id = self.central_service.find_pool(
            self.admin_context, {'name': 'default'}).id

        self.command.show_config(pool_id, all_pools=False)

        self.print_result.assert_called_once()
        self.assertIn('Pool Configuration', self.command.output_message[1])
        self.assertIn(
            'Default PowerDNS 4 Pool', ''.join(self.command.output_message)
        )

    def test_show_config_catalog_zone(self):
        self.command._setup()
        self.command._create_pool(get_pools('pools-catalog-zone.yaml')[0])

        pool_id = self.central_service.find_pool(
            self.admin_context, {'name': 'default'}).id

        self.command.show_config(pool_id, all_pools=False)

        self.print_result.assert_called_once()
        self.assertIn('Pool Configuration', self.command.output_message[1])
        self.assertIn(
            'Default PowerDNS 4 Pool', ''.join(self.command.output_message)
        )

    @mock.patch.object(service.Service, 'find_pool',
                       side_effect=oslo_messaging.MessagingTimeout())
    def test_show_config_rpc_timeout(self, mock_find_pool):
        self.assertRaises(
            SystemExit,
            self.command.show_config, '5421ca70-f1b7-4edc-9e01-b604011a262a',
            all_pools=False
        )

        mock_find_pool.assert_called_once()

    def test_show_config_pool_not_found(self):
        self.assertRaises(
            SystemExit,
            self.command.show_config, '5421ca70-f1b7-4edc-9e01-b604011a262a',
            all_pools=False
        )
        self.assertIn(
            'Pool not found', ''.join(self.command.output_message)
        )

    def test_show_config_invalid_uuid(self):
        self.assertRaises(
            SystemExit,
            self.command.show_config, 'None', all_pools=False
        )
        self.print_result.assert_called_once()
        self.assertIn(
            'Not a valid uuid: None', ''.join(self.command.output_message)
        )

    def test_show_config_empty(self):
        self.assertRaises(
            SystemExit,
            self.command.show_config, 'a36bb018-9584-420c-acc6-2b5cf89714ad',
            all_pools=False
        )
        self.print_result.assert_called_once()
        self.assertIn('Pool not found', ''.join(self.command.output_message))

    def test_show_config_multiple_pools(self):
        self.command._setup()
        self.command._create_pool(get_pools(name='multiple-pools.yaml')[0])
        self.command._create_pool(get_pools(name='multiple-pools.yaml')[1])

        # Calling show_config --all_pools without specifying pool_id
        self.command.show_config(None, all_pools=True)

        self.print_result.assert_called_once()

        pools = self.central_service.find_pools(self.admin_context, {})
        self.assertIn('Pool Configuration', self.command.output_message[1])
        for p in pools:
            self.assertIn(p.id, ''.join(self.command.output_message))
            self.assertIn(p.description,
                          ''.join(self.command.output_message))

        # Calling show_config --all_pools with pool_id
        # (should ignore the pool_id)
        self.command.show_config('a36bb018-9584-420c-acc6-2b5cf89714ad',
                                 all_pools=True)
        for p in pools:
            self.assertEqual(2, sum(
                p.id in s for s in self.command.output_message))
            self.assertEqual(2, sum(
                p.description in s for s in self.command.output_message))

    def test_update(self):
        self.command.update(
            get_pools_path('pools.yaml'), delete=False, dry_run=False
        )

        self.print_result.assert_called_once()
        self.assertIn(
            'Updating Pools Configuration****************************',
            ''.join(self.command.output_message)
        )

        pool = self.central_service.find_pool(self.admin_context, {
            'name': 'default'
        })

        self.assertEqual(1, len(pool.targets))
        self.assertEqual('pdns4', pool.targets[0].type)

    def test_update_bind9(self):
        self.command.update(
            get_pools_path('bind9_pools.yaml'), delete=False, dry_run=False
        )

        self.print_result.assert_called_once()
        self.assertIn(
            'Updating Pools Configuration****************************',
            ''.join(self.command.output_message)
        )

        pool = self.central_service.find_pool(self.admin_context, {
            'name': 'bind'
        })

        self.assertEqual(1, len(pool.targets))
        self.assertEqual('bind9', pool.targets[0].type)

    def test_update_multiple_pools(self):
        self.command.update(
            get_pools_path('multiple-pools.yaml'), delete=False, dry_run=False
        )

        self.print_result.assert_called_once()
        self.assertIn(
            'Updating Pools Configuration****************************',
            ''.join(self.command.output_message)
        )

        pools = self.central_service.find_pools(self.admin_context, {})
        self.assertEqual(2, len(pools))

    def test_update_multiple_pools_name(self):
        self.command.update(
            get_pools_path('pools.yaml'), delete=False, dry_run=False
        )

        pools = self.central_service.find_pools(self.admin_context, {})
        self.assertEqual(1, len(pools))

        # Updating an existing pool (same name) to a different id should fail
        self.assertRaises(
            exceptions.DuplicatePool,
            self.command.update,
            get_pools_path('sample_output.yaml'), delete=False, dry_run=False
        )

        pools = self.central_service.find_pools(self.admin_context, {})
        self.assertEqual(1, len(pools))

        # Updating Pools with different name will only add pools
        self.command.update(
            get_pools_path('multiple-pools.yaml'), delete=False, dry_run=False
        )

        pools = self.central_service.find_pools(self.admin_context, {})
        self.assertEqual(3, len(pools))

    @mock.patch.object(service.Service, 'find_pool',
                       side_effect=oslo_messaging.MessagingTimeout())
    def test_update_rpc_timeout(self, mock_find_pool):
        self.assertRaises(
            SystemExit,
            self.command.update,
            get_pools_path('pools.yaml'), delete=False, dry_run=False
        )

        mock_find_pool.assert_called_once()

    @mock.patch.object(pool.PoolCommands, '_load_config')
    def test_update_pool_with_invalid_uuid(self, mock_load_config):
        mock_load_config.return_value = [{
            'name': 'default',
            'id': 'invalid',
        }]

        self.assertRaises(
            SystemExit,
            self.command.update, 'test.yaml', delete=False, dry_run=False
        )
        self.assertIn(
            'Not a valid uuid: invalid',
            ''.join(self.command.output_message)
        )

    @mock.patch.object(pool.PoolCommands, '_load_config')
    def test_update_pool_invalid_ns_record(self, mock_load_config):
        mock_load_config.return_value = [{
            'name': 'default',
            'ns_records': [
                {'hostname': 'ns1-1.example.org.', 'priority': None},
            ],
            'targets': [
                {
                    'type': 'powerdns',
                }
            ],
        }]

        self.assertRaises(
            SystemExit,
            self.command.update, 'test.yaml', delete=False, dry_run=False
        )
        self.assertIn(
            "Provided object is not valid. Got a ValueError error with "
            "message Field `priority' cannot be None",
            ''.join(self.command.output_message)
        )

    @mock.patch.object(pool.PoolCommands, '_load_config')
    def test_update_new_backend(self, mock_load_config):
        self.command._setup()
        self.command._create_pool(get_pools()[0])

        self.create_zone(fixture=0)
        self.create_zone(fixture=1)

        pools = self.central_service.find_pools(self.admin_context, {})
        self.assertEqual(1, len(pools))
        self.assertEqual('pdns4', pools[0].targets[0].type)

        new_default = dict(get_pools()[0])
        new_default['targets'][0]['type'] = 'bind9'

        mock_load_config.return_value = [new_default]

        self.command.update('test.yaml', delete=False, dry_run=False)

        mock_load_config.assert_called_once_with('test.yaml')
        self.print_result.assert_called_once()
        self.assertIn(
            'Updating Pools Configuration****************************',
            ''.join(self.command.output_message)
        )

        pools = self.central_service.find_pools(self.admin_context, {})
        self.assertEqual(1, len(pools))
        self.assertEqual('bind9', pools[0].targets[0].type)

    @mock.patch.object(pool.PoolCommands, '_load_config')
    def test_update_pool_keeps_zone_masters(self, mock_load_config):
        self.command._setup()
        self.command._create_pool(get_pools()[0])

        default_pool = self.central_service.find_pool(
            self.admin_context, {'name': 'default'}
        )
        self.create_tsigkey(scope='POOL', resource_id=default_pool.id)

        primary_zone = self.create_zone(fixture=1)
        fixture = self.get_zone_fixture('SECONDARY', 0)
        fixture['email'] = CONF['service:central'].managed_resource_email
        fixture['masters'] = [{'host': '192.0.2.50', 'port': 53}]
        secondary_zone = self.create_zone(**fixture)

        pool_data = get_pools()[0]
        pool_data['targets'][0]['masters'] = [
            {'host': '192.0.2.10', 'port': 5354}
        ]
        mock_load_config.return_value = [pool_data]

        with mock.patch(
                'designate.worker.rpcapi.WorkerAPI.perform_zone_xfr'
        ) as mock_perform_zone_xfr:
            self.command.update('pools.yaml', delete=False, dry_run=False)

        # The zones are updated, so that the backends use the new masters
        # of the pool target.
        zones = self.central_service.find_zones(self.admin_context)
        self.assertEqual(2, len(zones))
        for zone in zones:
            self.assertEqual('UPDATE', zone.action)
            self.assertEqual('PENDING', zone.status)

        # The secondary zone keeps its primary server and is not transferred
        # from the masters of the pool target.
        secondary_zone = self.central_service.get_zone(
            self.admin_context, secondary_zone.id
        )
        self.assertEqual(
            [('192.0.2.50', 53)],
            [(master.host, master.port) for master in secondary_zone.masters]
        )
        mock_perform_zone_xfr.assert_not_called()

        # The primary zone still has no masters.
        self.assertEqual(0, len(self.storage._find_zone_masters(
            self.admin_context, {'zone_id': primary_zone.id}
        )))

    @mock.patch.object(pool.PoolCommands, '_load_config')
    def test_update_pool_unknown_backend(self, mock_load_config):
        mock_load_config.return_value = [{
            'name': 'default',
            'ns_records': [
                {'hostname': 'ns1-1.example.org.', 'priority': 1},
            ],
            'targets': [
                {
                    'type': 'powerdns',
                }
            ],
        }]

        self.assertRaises(
            SystemExit,
            self.command.update, 'test.yaml', delete=False, dry_run=False
        )
        self.assertIn(
            'Unable to find designate backend driver type: powerdns',
            ''.join(self.command.output_message)
        )

    @mock.patch.object(pool.PoolCommands, '_load_config')
    def test_update_pool_unknown_backend_dry_run(self, mock_load_config):
        mock_load_config.return_value = [{
            'name': 'default',
            'ns_records': [
            ],
            'targets': [
                {
                    'type': 'powerdns',
                }
            ],
        }]

        self.command.update(
            'test.yaml', delete=False, dry_run=True
        )

        self.assertIn(
            'Unable to find designate backend driver type: powerdns',
            ''.join(self.command.output_message)
        )

    @mock.patch.object(pool.PoolCommands, '_load_config')
    def test_update_pool_unknown_backend_skip_verify(self, mock_load_config):
        mock_load_config.return_value = [{
            'name': 'default',
            'ns_records': [
            ],
            'targets': [
                {
                    'type': 'powerdns',
                }
            ],
        }]

        self.command.update(
            'test.yaml', delete=False, dry_run=False, skip_verify_drivers=True
        )

        self.assertNotIn(
            'Unable to find designate backend driver type: powerdns',
            ''.join(self.command.output_message)
        )

    def test_update_with_delete(self):
        self.command.update(
            get_pools_path('multiple-pools.yaml'), delete=True, dry_run=False
        )

        pools = self.central_service.find_pools(self.admin_context, {})
        self.assertEqual(2, len(pools))

        self.command.update(
            get_pools_path('pools.yaml'), delete=True, dry_run=False
        )

        self.print_result.assert_called()

        pools = self.central_service.find_pools(self.admin_context, {})
        self.assertEqual(1, len(pools))

    @mock.patch.object(pool.PoolCommands, '_load_config')
    def test_update_with_delete_dry_run(self, mock_load_config):
        default_pool = dict(get_pools()[0])
        default_pool['id'] = 'a234253f-9fd8-4e1c-996e-5bcb152f43d5'
        additional_pool = {
            'name': 'second_pool',
            'ns_records': [
                {'hostname': 'ns1-1.example.org.', 'priority': 1},
            ],
            'targets': [
                {
                    'type': 'pdns4',
                }
            ],
        }

        mock_load_config.return_value = get_pools()

        self.command._setup()
        self.command._create_pool(default_pool)
        self.command._create_pool(additional_pool)

        self.command.update('test.yaml', delete=True, dry_run=True)

        mock_load_config.assert_called_once_with('test.yaml')
        self.print_result.assert_called_once()
        self.assertIn(
            "Update Pool: <Pool id:'a234253f-9fd8-4e1c-996e-5bcb152f43d5' "
            "name:'default'>",
            ' '.join(self.command.output_message)
        )
        self.assertIn(
            'Delete Pool: second_pool',
            ''.join(self.command.output_message)
        )

        pools = self.central_service.find_pools(self.admin_context, {})
        self.assertEqual(2, len(pools))

    @mock.patch.object(pool.PoolCommands, '_load_config')
    def test_update_dry_run(self, mock_load_config):
        mock_load_config.return_value = get_pools()

        self.command.update('test.yaml', delete=True, dry_run=True)

        mock_load_config.assert_called_once_with('test.yaml')
        self.print_result.assert_called_once()
        self.assertIn(
            "Create Pool: <Pool id:'None' name:'default'>",
            ''.join(self.command.output_message)
        )

    @mock.patch.object(pool.PoolCommands, '_write_config_to_file')
    def test_generate_file(self, mock_write_config_to_file):
        self.command._setup()
        self.command._create_pool(get_pools()[0])

        self.command.generate_file('test.yaml')

        mock_write_config_to_file.assert_called_once()

    @mock.patch.object(service.Service, 'find_pools',
                       side_effect=oslo_messaging.MessagingTimeout())
    def test_generate_file_rpc_timeout(self, mock_find_pools):
        self.assertRaises(
            SystemExit,
            self.command.generate_file, 'test.yaml'
        )

        mock_find_pools.assert_called_once()

    def test_create_new_pool(self):
        pools = self.central_service.find_pools(self.admin_context, {})
        self.assertEqual(0, len(pools))

        self.command._setup()
        self.command._create_pool(get_pools()[0])

        new_pool = self.central_service.find_pool(
            self.admin_context, {'name': 'default'}
        )

        self.assertEqual('default', new_pool.name)
        self.assertEqual('Default PowerDNS 4 Pool', new_pool.description)

        pools = self.central_service.find_pools(self.admin_context, {})
        self.assertEqual(1, len(pools))

    def test_get_pool_by_id(self):
        self.command._setup()
        self.command._create_pool(get_pools()[0])

        new_pool = self.central_service.find_pool(
            self.admin_context, {'name': 'default'}
        )

        self.assertEqual(
            'default',
            self.command._get_pool({'id': new_pool.id}).name
        )

    def _create_pool_with_zones(self):
        self.command._setup()
        self.command._create_pool(get_pools()[0])

        default_pool = self.central_service.find_pool(
            self.admin_context, {'name': 'default'}
        )
        self.create_tsigkey(scope='POOL', resource_id=default_pool.id)
        self.create_zone(fixture=0)
        self.create_zone(fixture=1)

        return default_pool

    def _update_and_count_zone_updates(self, pool_data):
        with mock.patch.object(
                pool.PoolCommands, '_load_config',
                return_value=[pool_data]):
            with mock.patch.object(
                    self.central_service, 'update_zone',
                    wraps=self.central_service.update_zone
            ) as mock_update_zone:
                self.command.update(
                    'pools.yaml', delete=False, dry_run=False
                )

        return mock_update_zone.call_count

    def test_update_pool_without_target_changes_does_not_update_zones(self):
        default_pool = self._create_pool_with_zones()

        pool_data = get_pools()[0]
        pool_data['id'] = default_pool.id
        pool_data['name'] = 'renamed'
        pool_data['description'] = 'Renamed pool'
        pool_data['attributes'] = {'type': 'external'}
        pool_data['also_notifies'] = [{'host': '192.0.2.5', 'port': 53}]

        self.assertEqual(0, self._update_and_count_zone_updates(pool_data))

        for zone in self.central_service.find_zones(self.admin_context):
            self.assertEqual('CREATE', zone.action)

        updated_pool = self.central_service.get_pool(
            self.admin_context, default_pool.id
        )
        self.assertEqual('renamed', updated_pool.name)
        self.assertEqual('Renamed pool', updated_pool.description)
        self.assertEqual('external', updated_pool.attributes[0].value)
        self.assertEqual('192.0.2.5', updated_pool.also_notifies[0].host)

    def test_update_pool_masters_updates_zones(self):
        self._create_pool_with_zones()

        pool_data = get_pools()[0]
        pool_data['targets'][0]['masters'] = [
            {'host': '192.0.2.10', 'port': 5354}
        ]

        self.assertEqual(2, self._update_and_count_zone_updates(pool_data))

        for zone in self.central_service.find_zones(self.admin_context):
            self.assertEqual('UPDATE', zone.action)
            self.assertEqual('PENDING', zone.status)

        # Nothing changed this time, so the zones are not updated again.
        self.assertEqual(0, self._update_and_count_zone_updates(pool_data))

    def test_update_pool_new_target_updates_zones(self):
        self._create_pool_with_zones()

        pool_data = get_pools()[0]
        new_target = copy.deepcopy(pool_data['targets'][0])
        new_target['options']['api_endpoint'] = 'http://192.0.2.5:8081'
        pool_data['targets'].append(new_target)

        self.assertEqual(2, self._update_and_count_zone_updates(pool_data))
