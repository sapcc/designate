# Copyright 2021 NS1 Inc. https://www.ns1.com
#
# Author: Dragan Blagojevic <dblagojevic@daitan.com>
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
import requests_mock
from designate import exceptions
from designate import objects
from designate.backend import impl_ns1
import designate.tests
from designate.tests import fixtures


class NS1BackendTestCase(designate.tests.TestCase):
    def setUp(self):
        super(NS1BackendTestCase, self).setUp()
        self.stdlog = fixtures.StandardLogging()
        self.useFixture(self.stdlog)

        self.api_address = 'https://192.0.2.3/v1/zones/example.com'
        self.context = self.get_context()
        self.zone = objects.Zone(
            id='e2bed4dc-9d01-11e4-89d3-123b93f75cba',
            name='example.com.',
            email='example@example.com',
        )

        self.target = {
            'id': '4588652b-50e7-46b9-b688-a9bad40a873e',
            'type': 'ns1',
            'masters': [
                {'host': '192.0.2.1', 'port': 53},
                {'host': '192.0.2.2', 'port': 35},
            ],
            'options': [
                {'key': 'api_endpoint', 'value': '192.0.2.3'},
                {'key': 'api_token', 'value': 'test_key'},
            ],
        }
        self.target_tsig = {
            'id': '4588652b-50e7-46b9-b688-a9bad40a873e',
            'type': 'ns1',
            'masters': [
                {'host': '192.0.2.1', 'port': 53},
                {'host': '192.0.2.2', 'port': 35},
            ],
            'options': [
                {'key': 'api_endpoint', 'value': '192.0.2.3'},
                {'key': 'api_token', 'value': 'test_key'},
                {'key': 'tsigkey_name', 'value': 'test_key'},
                {'key': 'tsigkey_hash', 'value': 'hmac-sha512'},
                {'key': 'tsigkey_value', 'value': 'aaaabbbbccc'},
            ],
        }
        self.put_request_json = {
            'zone': u'example.com',
            'secondary': {
                'enabled': True,
                'primary_ip': '192.0.2.1',
                'primary_port': 53
            }
        }
        self.put_request_tsig_json = {
            'zone': u'example.com',
            'secondary': {
                'enabled': True,
                'primary_ip': '192.0.2.1',
                'primary_port': 53,
                'tsig': {
                    'enabled': True,
                    'hash': 'hmac-sha512',
                    'name': 'test_key',
                    'key': 'aaaabbbbccc'
                }
            }
        }

        self.backend = impl_ns1.NS1Backend(
            objects.PoolTarget.from_dict(self.target)
        )
        self.backend_tsig = impl_ns1.NS1Backend(
            objects.PoolTarget.from_dict(self.target_tsig)
        )

    @requests_mock.mock()
    def test_create_zone_success(self, req_mock):
        req_mock.put(self.api_address)
        req_mock.get(
            self.api_address,
            status_code=404
        )

        self.backend.create_zone(self.context, self.zone)

        self.assertEqual(
            req_mock.last_request.json(),
            self.put_request_json
        )

        self.assertEqual(
            req_mock.last_request.headers.get('X-NSONE-Key'), 'test_key'
        )

    @requests_mock.mock()
    def test_create_zone_with_tsig_success(self, req_mock):
        req_mock.put(self.api_address)
        req_mock.get(
            self.api_address,
            status_code=404
        )

        self.backend_tsig.create_zone(self.context, self.zone)

        self.assertEqual(
            req_mock.last_request.json(),
            self.put_request_tsig_json
        )

        self.assertEqual(
            req_mock.last_request.headers.get('X-NSONE-Key'), 'test_key'
        )

    @requests_mock.mock()
    def test_create_zone_already_exists(self, req_mock):

        req_mock.get(self.api_address, status_code=200)
        req_mock.put(self.api_address)

        self.backend.create_zone(self.context, self.zone)

        self.assertIn(
            "Can't create zone example.com. because it already exists",
            self.stdlog.logger.output
        )

        self.assertEqual(
            req_mock.last_request.headers.get('X-NSONE-Key'), 'test_key'
        )

    @requests_mock.mock()
    def test_create_zone_fail(self, req_mock):
        req_mock.put(
            self.api_address,
            status_code=500,
        )
        req_mock.get(
            self.api_address,
            status_code=404,
        )

        self.assertRaisesRegexp(
            exceptions.Backend,
            '500 Server Error: None for url: '
            '%s' % self.api_address,
            self.backend.create_zone, self.context, self.zone
        )

        self.assertEqual(
            req_mock.last_request.headers.get('X-NSONE-Key'), 'test_key'
        )

    @requests_mock.mock()
    def test_delete_zone_success(self, req_mock):
        req_mock.delete(self.api_address, status_code=200)
        req_mock.get(self.api_address, status_code=200)

        self.backend.delete_zone(self.context, self.zone)

        self.assertEqual(
            req_mock.last_request.headers.get('X-NSONE-Key'), 'test_key'
        )

    @requests_mock.mock()
    def test_delete_zone_missing(self, req_mock):
        req_mock.delete(self.api_address, status_code=200)
        req_mock.get(self.api_address, status_code=404)

        self.backend.delete_zone(self.context, self.zone)

        self.assertIn(
            "Trying to delete zone "
            "<Zone id:'e2bed4dc-9d01-11e4-89d3-123b93f75cba' type:'None' "
            "name:'example.com.' pool_id:'None' serial:'None' action:'None' "
            "status:'None'> "
            "but that zone is not "
            "present in the ns1 backend. Assuming success.",
            self.stdlog.logger.output
        )

        self.assertEqual(
            req_mock.last_request.headers.get('X-NSONE-Key'), 'test_key'
        )

    @requests_mock.mock()
    def test_delete_zone_fail(self, req_mock):
        req_mock.delete(self.api_address, status_code=500)
        req_mock.get(self.api_address, status_code=200)

        self.assertRaisesRegexp(
            exceptions.Backend,
            '500 Server Error: None for url: '
            '%s' % self.api_address,
            self.backend.delete_zone, self.context, self.zone
        )
        self.assertEqual(
            req_mock.last_request.headers.get('X-NSONE-Key'), 'test_key'
        )
