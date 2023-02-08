# Copyright 2015 Hewlett-Packard Development Company, L.P.
#
# Author: Federico Ceratto <federico.ceratto@hpe.com>
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
# under the License.
from unittest import mock

import oslotest.base
from oslo_config import cfg
from oslo_config import fixture as cfg_fixture

import designate.dnsutils
import designate.rpc
import designate.service
from designate import storage
import designate.utils
from designate.mdns import handler
from designate.mdns import service
from designate.tests import fixtures

CONF = cfg.CONF


class MdnsServiceTest(oslotest.base.BaseTestCase):
    @mock.patch.object(storage, 'get_storage', mock.Mock())
    def setUp(self):
        super(MdnsServiceTest, self).setUp()
        self.stdlog = fixtures.StandardLogging()
        self.useFixture(self.stdlog)

        conf = self.useFixture(cfg_fixture.Config(CONF))
        conf.conf([], project='designate')

        self.service = service.Service()

    @mock.patch.object(designate.service.DNSService, 'start')
    @mock.patch.object(designate.service.RPCService, 'start')
    def test_service_start(self, mock_rpc_start, mock_dns_start):
        self.service.start()

        self.assertTrue(mock_dns_start.called)
        self.assertTrue(mock_rpc_start.called)

    def test_service_stop(self):
        self.service.dns_service.stop = mock.Mock()
        self.service.heartbeat.stop = mock.Mock()

        self.service.stop()

        self.assertTrue(self.service.dns_service.stop.called)
        self.assertTrue(self.service.heartbeat.stop.called)

        self.assertIn('Stopping mdns service', self.stdlog.logger.output)

    def test_service_name(self):
        self.assertEqual('mdns', self.service.service_name)

    def test_mdns_rpc_topic(self):
        CONF.set_override('topic', 'test-topic', 'service:mdns')

        self.service = service.Service()

        self.assertEqual('test-topic', self.service.rpc_topic)
        self.assertEqual('mdns', self.service.service_name)

    @mock.patch.object(storage, 'get_storage')
    def test_storage_driver(self, mock_get_driver):
        self.service._storage = None

        mock_driver = mock.MagicMock()
        mock_driver.name = 'noop_driver'
        mock_get_driver.return_value = mock_driver

        self.assertIsInstance(self.service.storage, mock.MagicMock)

        self.assertTrue(mock_get_driver.called)

    @mock.patch.object(handler, 'RequestHandler')
    @mock.patch.object(designate.service.DNSService, 'start')
    @mock.patch.object(designate.utils, 'cache_result')
    def test_dns_application(self, mock_cache_result, mock_dns_start,
                             mock_request_handler):

        app = self.service.dns_application

        self.assertIsInstance(app, designate.dnsutils.DNSMiddleware)
