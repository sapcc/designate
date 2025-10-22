# Copyright 2020 Cloudification GmbH. All rights reserved.
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
from designate.tests.functional.api import v2
from oslo_utils.uuidutils import  generate_uuid


class ApiV2SharedPoolsTest(v2.ApiV2TestCase):
    def setUp(self):
        super().setUp()

        self.pool = self.create_pool(domain_id=generate_uuid())
        self.target_domain_id = '2'
        self.endpoint_url = '/pools/{}/shares'

    def _create_valid_shared_pool(self):
        return self.client.post_json(
            self.endpoint_url.format(self.pool.id),
            {
                'target_domain_id': self.target_domain_id,
            }, headers={'X-Test-Role': 'admin'}
        )

    def test_share_pool(self):
        response = self._create_valid_shared_pool()

        # Check the headers are what we expect
        self.assertEqual(201, response.status_int)
        self.assertEqual('application/json', response.content_type)

        # Check the body structure is what we expect
        self.assertIn('links', response.json)
        self.assertIn('self', response.json['links'])

        # Check the values returned are what we expect
        self.assertIn('id', response.json)
        self.assertIn('created_at', response.json)
        self.assertEqual(
            self.target_domain_id,
            response.json['target_domain_id'])
        self.assertEqual(
            self.pool.id,
            response.json['pool_id'])
        self.assertIsNone(response.json['updated_at'])
        self.assertEqual(
            self.pool.domain_id,
            response.json['domain_id'])

    def test_share_pool_with_no_domain_id_no_pool_id(self):
        self._assert_exception(
            'invalid_uuid', 400, self.client.post_json,
            self.endpoint_url.format(""), {"target_domain_id": ""},
            headers={'X-Test-Role': 'admin'}
        )

    def test_share_pool_with_target_id_no_pool_id(self):
        self._assert_exception(
            'invalid_uuid', 400, self.client.post_json,
            self.endpoint_url.format(""), {"target_domain_id": "2"},
            headers={'X-Test-Role': 'admin'}
        )

    def test_share_pool_with_invalid_pool_id(self):
        self._assert_exception(
            'invalid_uuid', 400, self.client.post_json,
            self.endpoint_url.format("invalid"), {"target_domain_id": "2",
                                                  "pool_id": "s"},
            headers={'X-Test-Role': 'admin'}
        )

    def test_get_pool_share(self):
        shared_pool = self._create_valid_shared_pool()

        response = self.client.get(
            '{}/{}'.format(self.endpoint_url.format(self.pool.id),
                           shared_pool.json['id']),
            headers={'X-Test-Role': 'admin'}
        )
        # Check the headers are what we expect
        self.assertEqual(200, response.status_int)
        self.assertEqual('application/json', response.content_type)

        # Check the body structure is what we expect
        self.assertIn('links', response.json)
        self.assertIn('self', response.json['links'])

        # Check the values returned are what we expect
        self.assertIn('id', response.json)
        self.assertIn('created_at', response.json)
        self.assertEqual(
            self.target_domain_id,
            response.json['target_domain_id'])
        self.assertEqual(
            self.pool.id,
            response.json['pool_id'])
        self.assertIn('updated_at', response.json)

    def test_list_pool_shares(self):
        response = self.client.get(self.endpoint_url.format(self.pool.id),
                                   headers={'X-Test-Role': 'admin'})

        # Check the headers are what we expect
        self.assertEqual(200, response.status_int)
        self.assertEqual('application/json', response.content_type)

        # Check the body structure is what we expect
        self.assertIn('shared_pools', response.json)
        self.assertIn('links', response.json)
        self.assertIn('self', response.json['links'])

        # We should start with 0 pool shares
        self.assertEqual(0, len(response.json['shared_pools']))

        self._create_valid_shared_pool()

        data = self.client.get(self.endpoint_url.format(self.pool.id),
                               headers={'X-Test-Role': 'admin'})
        self.assertEqual(1, len(data.json['shared_pools']))

    def test_delete_pool_share(self):
        shared_pool = self._create_valid_shared_pool()

        response = self.client.delete(
            '{}/{}'.format(self.endpoint_url.format(self.pool.id),
                           shared_pool.json['id']),
            headers={'X-Test-Role': 'admin'}
        )

        # Check the headers are what we expect
        self.assertEqual(204, response.status_int)
