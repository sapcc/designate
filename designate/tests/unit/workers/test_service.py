# Copyright 2016 Rackspace Inc.
#
# Author: Eric Larson <eric.larson@rackspace.com>
#
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
# under the License.mport threading
from unittest import mock

import oslo_messaging as messaging
import oslotest.base
from oslo_config import cfg
from oslo_config import fixture as cfg_fixture

import designate.service
import designate.tests
from designate import backend
from designate import exceptions
from designate import objects
from designate.tests import fixtures
from designate.worker import processing
from designate.worker import service

CONF = cfg.CONF


class TestService(oslotest.base.BaseTestCase):
    def setUp(self):
        super(TestService, self).setUp()
        self.stdlog = fixtures.StandardLogging()
        self.useFixture(self.stdlog)
        conf = self.useFixture(cfg_fixture.Config(CONF))
        conf.conf([], project='designate')
        self.context = mock.Mock()
        self.zone = mock.Mock()
        self.service = service.Service()

    @mock.patch.object(designate.service.RPCService, 'start')
    def test_service_start(self, mock_rpc_start):
        self.service.start()

        self.assertTrue(mock_rpc_start.called)

    @mock.patch.object(designate.rpc, 'get_notification_listener')
    def test_service_stop(self, mock_notification_listener):
        self.service.stop()

        self.assertIn('Stopping worker service', self.stdlog.logger.output)

    def test_service_name(self):
        self.assertEqual('worker', self.service.service_name)

    def test_worker_rpc_topic(self):
        CONF.set_override('topic', 'test-topic', 'service:worker')

        self.service = service.Service()

        self.assertEqual('test-topic', self.service.rpc_topic)
        self.assertEqual('worker', self.service.service_name)

    def test_central_api(self):
        self.service._central_api = 'foo'
        self.assertEqual(self.service.central_api, 'foo')

    def test_storage(self):
        self.service._storage = 'foo'
        self.assertEqual(self.service.storage, 'foo')

    @mock.patch.object(backend, 'get_backend', mock.Mock())
    def test_setup_target_backends(self):
        pool = objects.Pool.from_dict({
            'targets': [
                {
                    'description': 'Fake DNS Cluster',
                    'masters': [],
                    'options': [],
                    'type': 'fake',
                    'pool_id': 'cf2e8eab-76cd-4162-bf76-8aeee3556de0',
                }
            ]
        })

        self.service._setup_target_backends(pool)

    def test_setup_target_backends_with_no_backends(self):
        pool = objects.Pool.from_dict({
            'targets': []
        })

        self.assertRaises(
            exceptions.NoPoolTargetsConfigured,
            self.service._setup_target_backends, pool
        )

    @mock.patch.object(backend, 'get_backend', mock.Mock())
    def test_load_pool(self):
        pool = objects.Pool.from_dict({
            'targets': [
                {
                    'description': 'Fake DNS Cluster',
                    'masters': [],
                    'options': [],
                    'type': 'fake',
                    'pool_id': 'cf2e8eab-76cd-4162-bf76-8aeee3556de0',
                }
            ]
        })

        self.service._central_api = mock.MagicMock()
        self.service._central_api.get_pool.return_value = pool
        self.assertIsInstance(
            self.service.load_pool('cf2e8eab-76cd-4162-bf76-8aeee3556de0'),
            objects.Pool
        )

    @mock.patch('time.sleep', mock.Mock())
    @mock.patch.object(backend, 'get_backend', mock.Mock())
    def test_load_pool_with_failures(self):
        pool_no_targets = objects.Pool.from_dict({
            'targets': [],
        })

        pool_success = objects.Pool.from_dict({
            'targets': [
                {
                    'description': 'Fake DNS Cluster',
                    'masters': [],
                    'options': [],
                    'type': 'fake',
                    'pool_id': 'cf2e8eab-76cd-4162-bf76-8aeee3556de0',
                }
            ]
        })

        self.service._central_api = mock.MagicMock()
        self.service._central_api.get_pool.side_effect = [
            messaging.exceptions.MessagingTimeout,
            exceptions.PoolNotFound,
            pool_no_targets,
            pool_success
        ]

        self.assertIsInstance(
            self.service.load_pool('cf2e8eab-76cd-4162-bf76-8aeee3556de0'),
            objects.Pool
        )

    def test_create_zone(self):
        self.service._do_zone_action = mock.Mock()

        self.service.create_zone(self.context, self.zone)

        self.service._do_zone_action.assert_called_with(
            self.context, self.zone
        )

    def test_get_executor(self):
        self.assertIsInstance(self.service.executor, processing.Executor)

    def test_get_pools_map(self):
        self.assertIsInstance(self.service.pools_map, dict)

    def test_delete_zone(self):
        self.service._do_zone_action = mock.Mock()
        self.zone_params = {}

        self.service.delete_zone(self.context, self.zone)

        self.service._do_zone_action.assert_called_with(
            self.context, self.zone, self.zone_params
        )

    def test_update_zone(self):
        self.service._do_zone_action = mock.Mock()

        self.service.update_zone(self.context, self.zone)

        self.service._do_zone_action.assert_called_with(
            self.context, self.zone
        )

    @mock.patch.object(service.zonetasks, 'ZoneAction')
    def test_do_zone_action(self, mock_zone_action):
        self.service._executor = mock.Mock()
        self.service._pool = mock.Mock()
        self.service.get_pool = mock.Mock()
        pool = mock.Mock()
        pool.also_notifies = mock.MagicMock()
        pool.also_notifies.__iter__.return_value = []
        self.service.get_pool.return_value = pool
        self.zone_params = {}

        self.service._do_zone_action(self.context, self.zone,
                                     self.zone_params)

        mock_zone_action.assert_called_with(
            self.service.executor,
            self.context,
            pool,
            self.zone,
            self.zone.action,
            self.zone_params
        )

        self.service._executor.run.assert_called_with([mock_zone_action()])

    @mock.patch.object(service.zonetasks, 'ZoneAction')
    @mock.patch.object(service.zonetasks, 'SendNotify')
    def test_do_zone_action_also_notifies(self, mock_send_notify,
                                          mock_zone_action):
        self.service._executor = mock.Mock()
        self.service._pool = mock.Mock()
        self.service.get_pool = mock.Mock()
        pool = mock.Mock()
        pool.also_notifies = mock.MagicMock()
        pool.also_notifies.__iter__.return_value = [
            mock.Mock(host='192.168.1.1', port=53),
        ]
        self.service.get_pool.return_value = pool
        self.zone_params = {}

        self.service._do_zone_action(self.context, self.zone,
                                     self.zone_params)

        mock_zone_action.assert_called_with(
            self.service.executor,
            self.context,
            pool,
            self.zone,
            self.zone.action,
            self.zone_params
        )

        self.service._executor.run.assert_called_with(
            [mock_zone_action(), mock_send_notify()]
        )

    def test_get_pool(self):
        pool = mock.Mock()
        self.service.load_pool = mock.Mock()
        self.service.load_pool.return_value = pool
        self.service._pools_map = {'1': pool}

        self.assertEqual(pool, self.service.get_pool('1'))
        self.assertEqual(pool, self.service.get_pool('2'))

    @mock.patch.object(service.zonetasks, 'RecoverShard')
    def test_recover_shard(self, mock_recover_shard):
        self.service._executor = mock.Mock()
        self.service._pool = mock.Mock()

        self.service.recover_shard(self.context, 1, 10)

        mock_recover_shard.assert_called_with(
            self.service.executor,
            self.context,
            1, 10
        )

        self.service.executor.run.assert_called_with(mock_recover_shard())

    @mock.patch.object(service.zonetasks, 'ExportZone')
    def test_start_zone_export(self, mock_export_zone):
        self.service._executor = mock.Mock()
        self.service._pool = mock.Mock()
        zone = mock.Mock()
        export = mock.Mock()

        self.service.start_zone_export(self.context, zone, export)

        mock_export_zone.assert_called_with(
            self.service.executor,
            self.context,
            zone,
            export
        )

        self.service.executor.run.assert_called_with(mock_export_zone())
