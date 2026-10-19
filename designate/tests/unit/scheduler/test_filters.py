# (c) Copyright 2016 Hewlett Packard Enterprise Development Company LP.
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

import fixtures

import oslotest.base

from designate import exceptions
from designate import objects
from designate import policy
from designate.scheduler.filters import attribute_filter
from designate.scheduler.filters import default_pool_filter
from designate.scheduler.filters import domain_id_filter
from designate.scheduler.filters import fallback_filter
from designate.scheduler.filters import in_doubt_default_pool_filter
from designate.scheduler.filters import pool_domains_attribute_filter
from designate.scheduler.filters import pool_id_attribute_filter


class SchedulerFilterTest(oslotest.base.BaseTestCase):
    def setUp(self):
        super().setUp()
        self.context = mock.Mock()
        self.context.project_domain_name = 'test'
        self.zone = objects.Zone(
            name='example.com.',
            type='PRIMARY',
            email='hostmaster@example.com'
        )

        attrs = {
            'get_pool.return_value': objects.Pool(
                id='6c346011-e581-429b-a7a2-6cdf0aba91c3')
        }

        mock_storage = mock.Mock(**attrs)
        self.test_filter = self.FILTER(storage=mock_storage)


class SchedulerDefaultPoolFilterTest(SchedulerFilterTest):
    FILTER = default_pool_filter.DefaultPoolFilter

    def test_default_operation(self):
        pools = objects.PoolList.from_list(
            [{'id': '794ccc2c-d751-44fe-b57f-8894c9f5c842'}]
        )
        pools = self.test_filter.filter(self.context, pools, self.zone)

        self.assertEqual(pools[0].id, '794ccc2c-d751-44fe-b57f-8894c9f5c842')

    def test_multiple_pools(self):
        pools = objects.PoolList.from_list(
            [
                {'id': '794ccc2c-d751-44fe-b57f-8894c9f5c842'},
                {'id': '5fabcd37-262c-4cf3-8625-7f419434b6df'}
            ]
        )
        pools = self.test_filter.filter(self.context, pools, self.zone)

        self.assertEqual(pools[0].id, '794ccc2c-d751-44fe-b57f-8894c9f5c842')

    def test_no_pools(self):
        pools = objects.PoolList()
        pools = self.test_filter.filter(self.context, pools, self.zone)

        self.assertEqual(pools[0].id, '794ccc2c-d751-44fe-b57f-8894c9f5c842')


class SchedulerFallbackFilterTest(SchedulerFilterTest):
    FILTER = fallback_filter.FallbackFilter

    def test_default_operation(self):
        pools = objects.PoolList.from_list(
            [{'id': '794ccc2c-d751-44fe-b57f-8894c9f5c842'}]
        )
        pools = self.test_filter.filter(self.context, pools, self.zone)

        self.assertEqual(pools[0].id, '794ccc2c-d751-44fe-b57f-8894c9f5c842')

    def test_multiple_pools(self):
        pools = objects.PoolList.from_list(
            [
                {'id': '6c346011-e581-429b-a7a2-6cdf0aba91c3'},
                {'id': '5fabcd37-262c-4cf3-8625-7f419434b6df'}
            ]
        )
        pools = self.test_filter.filter(self.context, pools, self.zone)

        self.assertEqual(len(pools), 2)

        for pool in pools:
            self.assertIn(
                pool.id,
                [
                    '6c346011-e581-429b-a7a2-6cdf0aba91c3',
                    '5fabcd37-262c-4cf3-8625-7f419434b6df',
                ]
            )

    def test_no_pools(self):
        pools = objects.PoolList()
        pools = self.test_filter.filter(self.context, pools, self.zone)

        self.assertEqual(pools[0].id, '794ccc2c-d751-44fe-b57f-8894c9f5c842')


class SchedulerPoolIDAttributeFilterTest(SchedulerFilterTest):
    FILTER = pool_id_attribute_filter.PoolIDAttributeFilter

    def setUp(self):
        super().setUp()
        self.zone = objects.Zone(
            name='example.com.',
            type='PRIMARY',
            email='hostmaster@example.com',
            attributes=objects.ZoneAttributeList.from_list(
                [
                    {
                        'key': 'pool_id',
                        'value': '6c346011-e581-429b-a7a2-6cdf0aba91c3'
                    }
                ]
            )
        )

    def test_default_operation(self):
        pools = objects.PoolList.from_list(
            [{'id': '6c346011-e581-429b-a7a2-6cdf0aba91c3'}]
        )
        self.useFixture(fixtures.MockPatchObject(
            policy, 'check',
            return_value=None
        ))

        pools = self.test_filter.filter(self.context, pools, self.zone)

        self.assertEqual('6c346011-e581-429b-a7a2-6cdf0aba91c3', pools[0].id)

    def test_multiple_pools(self):
        pools = objects.PoolList.from_list(
            [
                {'id': '6c346011-e581-429b-a7a2-6cdf0aba91c3'},
                {'id': '5fabcd37-262c-4cf3-8625-7f419434b6df'}
            ]
        )

        self.useFixture(fixtures.MockPatchObject(
            policy, 'check',
            return_value=None
        ))

        pools = self.test_filter.filter(self.context, pools, self.zone)

        self.assertEqual(len(pools), 1)

        self.assertEqual('6c346011-e581-429b-a7a2-6cdf0aba91c3', pools[0].id)

    def test_no_pools(self):
        pools = objects.PoolList()

        self.useFixture(fixtures.MockPatchObject(
            policy, 'check',
            return_value=None
        ))

        pools = self.test_filter.filter(self.context, pools, self.zone)

        self.assertEqual(len(pools), 0)

    def test_pools_missing_from_attribute_list(self):
        zone = objects.Zone(
            name='example.com.',
            type='PRIMARY',
            email='hostmaster@example.com',
            attributes=objects.ZoneAttributeList.from_list([])
        )
        pools = objects.PoolList()
        pools = self.test_filter.filter(self.context, pools, zone)

        self.assertEqual(len(pools), 0)

    def test_get_pool_failure(self):
        mock_storage = mock.Mock()
        mock_storage.get_pool.side_effect = Exception()

        test_filter = self.FILTER(storage=mock_storage)

        pools = objects.PoolList()
        pools = test_filter.filter(self.context, pools, self.zone)

        self.assertEqual(len(pools), 0)

    def test_policy_failure(self):
        pools = objects.PoolList.from_list(
            [{'id': '6c346011-e581-429b-a7a2-6cdf0aba91c3'}]
        )

        self.useFixture(fixtures.MockPatchObject(
            policy, 'check',
            side_effect=exceptions.Forbidden
        ))

        self.assertRaises(
            exceptions.Forbidden,
            self.test_filter.filter, self.context, pools, self.zone,
        )

        policy.check.assert_called_once_with(
            'zone_create_forced_pool', self.context, pools[0]
        )


class SchedulerAttributeFilterTest(SchedulerFilterTest):
    FILTER = attribute_filter.AttributeFilter

    def setUp(self):
        super().setUp()
        self.zone = objects.Zone(
            name='example.com.',
            type='PRIMARY',
            email='hostmaster@example.com',
            attributes=objects.ZoneAttributeList.from_list(
                [
                    {
                        'key': 'attribute_one',
                        'value': 'True'
                    },
                    {
                        'key': 'attribute_two',
                        'value': 'False'
                    },
                    {
                        'key': 'attribute_three',
                        'value': 'foo'
                    }
                ]
            )
        )

    def test_default_operation(self):
        pools = objects.PoolList.from_list(
            [
                {
                    'id': '6c346011-e581-429b-a7a2-6cdf0aba91c3',
                }
            ]
        )

        pools[0].attributes = objects.PoolAttributeList.from_list(
            [
                {
                    'key': 'attribute_one',
                    'value': 'True'
                },
                {
                    'key': 'attribute_two',
                    'value': 'False'
                },
                {
                    'key': 'attribute_three',
                    'value': 'foo'
                }
            ])

        pools = self.test_filter.filter(self.context, pools, self.zone)

        self.assertEqual('6c346011-e581-429b-a7a2-6cdf0aba91c3', pools[0].id)

    def test_multiple_pools_all_match(self):
        pools = objects.PoolList.from_list(
            [
                {'id': '6c346011-e581-429b-a7a2-6cdf0aba91c3'},
                {'id': '5fabcd37-262c-4cf3-8625-7f419434b6df'}
            ]

        )

        attributes = objects.PoolAttributeList.from_list(
            [
                {
                    'key': 'attribute_one',
                    'value': 'True'
                },
                {
                    'key': 'attribute_two',
                    'value': 'False'
                },
                {
                    'key': 'attribute_three',
                    'value': 'foo'
                }
            ])

        pools[0].attributes = attributes
        pools[1].attributes = attributes

        pools = self.test_filter.filter(self.context, pools, self.zone)

        self.assertEqual(2, len(pools))

    def test_multiple_pools_one_match(self):
        pools = objects.PoolList.from_list(
            [
                {'id': '6c346011-e581-429b-a7a2-6cdf0aba91c3'},
                {'id': '5fabcd37-262c-4cf3-8625-7f419434b6df'}
            ]

        )

        pool_0_attributes = objects.PoolAttributeList.from_list(
            [
                {
                    'key': 'attribute_one',
                    'value': 'True'
                },
                {
                    'key': 'attribute_two',
                    'value': 'False'
                },
                {
                    'key': 'attribute_three',
                    'value': 'foo'
                }
            ])

        pool_1_attributes = objects.PoolAttributeList.from_list(
            [
                {
                    'key': 'attribute_four',
                    'value': 'True'
                },
                {
                    'key': 'attribute_five',
                    'value': 'False'
                },
                {
                    'key': 'attribute_three',
                    'value': 'foo'
                }
            ])

        pools[0].attributes = pool_0_attributes
        pools[1].attributes = pool_1_attributes

        pools = self.test_filter.filter(self.context, pools, self.zone)

        self.assertEqual(1, len(pools))
        self.assertEqual('6c346011-e581-429b-a7a2-6cdf0aba91c3', pools[0].id)

    def test_multiple_pools_no_match(self):
        pools = objects.PoolList.from_list(
            [
                {'id': '6c346011-e581-429b-a7a2-6cdf0aba91c3'},
                {'id': '5fabcd37-262c-4cf3-8625-7f419434b6df'}
            ]

        )

        pool_0_attributes = objects.PoolAttributeList.from_list(
            [
                {
                    'key': 'attribute_six',
                    'value': 'True'
                },
                {
                    'key': 'attribute_two',
                    'value': 'False'
                },
                {
                    'key': 'attribute_seven',
                    'value': 'foo'
                }
            ])

        pool_1_attributes = objects.PoolAttributeList.from_list(
            [
                {
                    'key': 'attribute_four',
                    'value': 'True'
                },
                {
                    'key': 'attribute_five',
                    'value': 'False'
                },
                {
                    'key': 'attribute_three',
                    'value': 'foo'
                }
            ])

        pools[0].attributes = pool_0_attributes
        pools[1].attributes = pool_1_attributes

        pools = self.test_filter.filter(self.context, pools, self.zone)

        self.assertEqual(0, len(pools))

    def test_no_match_non_bool(self):
        pools = objects.PoolList.from_list(
            [
                {'id': '6c346011-e581-429b-a7a2-6cdf0aba91c3'},
            ]

        )

        pool_0_attributes = objects.PoolAttributeList.from_list(
            [
                {
                    'key': 'attribute_one',
                    'value': 'True'
                },
                {
                    'key': 'attribute_two',
                    'value': 'False'
                },
                {
                    'key': 'attribute_three',
                    'value': 'bar'
                }
            ])

        pools[0].attributes = pool_0_attributes

        pools = self.test_filter.filter(self.context, pools, self.zone)

        self.assertEqual(0, len(pools))

    def test_zone_attributes_not_set(self):
        pools = objects.PoolList.from_list([])

        zone = objects.Zone(
            name='example.com.',
            type='PRIMARY',
            email='hostmaster@example.com',
        )

        pools = self.test_filter.filter(self.context, pools, zone)

        self.assertEqual(0, len(pools))

    def test_pool_attributes_not_set(self):
        pools = objects.PoolList.from_list(
            [
                {'id': '6c346011-e581-429b-a7a2-6cdf0aba91c3'},
            ]

        )

        pools = self.test_filter.filter(self.context, pools, self.zone)

        self.assertEqual(1, len(pools))

    def _forced_pool_zone(self):
        return objects.Zone(
            name='example.com.',
            type='PRIMARY',
            email='hostmaster@example.com',
            attributes=objects.ZoneAttributeList.from_list([
                {'key': 'pool_id',
                 'value': '6c346011-e581-429b-a7a2-6cdf0aba91c3'},
            ])
        )

    def test_forced_pool_in_candidates(self):
        self.useFixture(fixtures.MockPatchObject(policy, 'check'))
        pools = objects.PoolList.from_list([
            {'id': '6c346011-e581-429b-a7a2-6cdf0aba91c3'},
            {'id': '5fabcd37-262c-4cf3-8625-7f419434b6df'},
        ])

        pools = self.test_filter.filter(
            self.context, pools, self._forced_pool_zone())

        self.assertEqual(1, len(pools))
        self.assertEqual('6c346011-e581-429b-a7a2-6cdf0aba91c3', pools[0].id)

    def test_forced_pool_not_in_candidates(self):
        # The zone asks for a pool that an earlier filter removed, e.g. a
        # pool not available to the user's domain.
        self.useFixture(fixtures.MockPatchObject(policy, 'check'))
        pools = objects.PoolList.from_list(
            [{'id': '5fabcd37-262c-4cf3-8625-7f419434b6df'}]
        )
        pools[0].attributes = objects.PoolAttributeList.from_list(
            [{'key': 'attribute_one', 'value': 'True'}]
        )

        self.assertRaises(
            exceptions.NoValidPoolFound,
            self.test_filter.filter,
            self.context, pools, self._forced_pool_zone(),
        )

    def test_forced_pool_does_not_exist(self):
        self.test_filter.storage.get_pool.side_effect = (
            exceptions.PoolNotFound()
        )
        pools = objects.PoolList.from_list(
            [{'id': '5fabcd37-262c-4cf3-8625-7f419434b6df'}]
        )

        self.assertRaises(
            exceptions.NoValidPoolFound,
            self.test_filter.filter,
            self.context, pools, self._forced_pool_zone(),
        )

    def test_forced_pool_policy_failure(self):
        self.useFixture(fixtures.MockPatchObject(
            policy, 'check',
            side_effect=exceptions.Forbidden
        ))
        pools = objects.PoolList.from_list(
            [{'id': '6c346011-e581-429b-a7a2-6cdf0aba91c3'}]
        )

        self.assertRaises(
            exceptions.Forbidden,
            self.test_filter.filter,
            self.context, pools, self._forced_pool_zone(),
        )


class SchedulerInDoubtDefaultPoolFilterTest(SchedulerFilterTest):
    FILTER = in_doubt_default_pool_filter.InDoubtDefaultPoolFilter

    def test_pools_with_default(self):
        pools = objects.PoolList.from_list(
            [
                {'id': '6c346011-e581-429b-a7a2-6cdf0aba91c3'},
                {'id': '5fabcd37-262c-4cf3-8625-7f419434b6df'}
            ]
        )
        pools = self.test_filter.filter(self.context, pools, self.zone)

        self.assertEqual(1, len(pools))
        self.assertEqual(pools[0].id, '6c346011-e581-429b-a7a2-6cdf0aba91c3')

    def test_pools_without_default(self):
        pools = objects.PoolList.from_list(
            [
                {'id': '24702e43-8a52-440f-ab74-19fc16048860'},
                {'id': '5fabcd37-262c-4cf3-8625-7f419434b6df'}
            ]
        )
        pools = self.test_filter.filter(self.context, pools, self.zone)

        self.assertEqual(2, len(pools))

    def test_no_pools(self):
        pools = objects.PoolList()
        pools = self.test_filter.filter(self.context, pools, self.zone)

        self.assertEqual(0, len(pools))

    def test_get_pool_failure(self):
        mock_storage = mock.Mock()
        mock_storage.get_pool.side_effect = Exception()

        test_filter = self.FILTER(storage=mock_storage)

        pools = objects.PoolList.from_list(
            [
                {'id': '24702e43-8a52-440f-ab74-19fc16048860'},
                {'id': '5fabcd37-262c-4cf3-8625-7f419434b6df'}
            ]
        )
        pools = test_filter.filter(self.context, pools, self.zone)

        self.assertEqual(len(pools), 2)


class DomainIDFilterTest(SchedulerFilterTest):
    FILTER = domain_id_filter.DomainIDFilter

    def setUp(self):
        super().setUp()
        self.context.project_domain_id = 'test'

    def test_pools_default_no_shared_pools(self):
        current_pools = objects.PoolList.from_list(
            [
                {'id': '6c346011-e581-429b-a7a2-6cdf0aba91c3',
                 "domain_id": "test"},
                {'id': '5fabcd37-262c-4cf3-8625-7f419434b6df'}
            ]
        )
        mock_storage = mock.Mock()
        mock_storage.find_shared_pools.return_value = []
        test_filter = self.FILTER(storage=mock_storage)
        pools = test_filter.filter(self.context, current_pools, self.zone)

        self.assertEqual(1, len(pools))
        self.assertEqual(pools[0].id, '6c346011-e581-429b-a7a2-6cdf0aba91c3')

    def test_domainless_context(self):
        cpools = objects.PoolList.from_list(
            [
                {'id': '24702e43-8a52-440f-ab74-19fc16048860'},
                {'id': '5fabcd37-262c-4cf3-8625-7f419434b6df'}
            ]
        )
        domainless_context = mock.Mock()
        domainless_context.project_domain_id = None
        mock_storage = mock.Mock()
        mock_storage.find_shared_pools.return_value = []
        test_filter = self.FILTER(storage=mock_storage)
        pools = test_filter.filter(domainless_context, cpools, self.zone)
        self.assertEqual(len(pools), 2)

    def test_domain_id_shared_pools(self):
        current_pools = objects.PoolList.from_list(
            [
                {'id': '24702e43-8a52-440f-ab74-19fc16048860'},
                {'id': '5fabcd37-262c-4cf3-8625-7f419434b6df'}
            ]
        )
        mock_storage = mock.Mock()
        mock_storage.find_shared_pools.return_value = objects.SharedPoolList.from_list([  # noqa
                {'target_domain_id': 'test',
                 "pool_id": "5fabcd37-262c-4cf3-8625-7f419434b6df",
                 "domain_id": "default"},
        ])
        mock_storage.get_pool.return_value = current_pools[1]
        test_filter = self.FILTER(storage=mock_storage)
        pools = test_filter.filter(self.context, current_pools, self.zone)

        self.assertEqual(len(pools), 1)
        self.assertEqual(current_pools[1].id, pools[0].id)

    def test_domain_id_shared_pools_and_pools(self):
        self.context.project_domain_id = "test"
        pools = objects.PoolList.from_list(
            [
                {'id': '6c346011-e581-429b-a7a2-6cdf0aba91c3',
                 "domain_id": "default"},
                {'id': '5fabcd37-262c-4cf3-8625-7f419434b6df',
                 'domain_id': 'test'}
            ]
        )
        mock_storage = mock.Mock()
        mock_storage.find_shared_pools.return_value = objects.SharedPoolList.from_list([  # noqa
                {'target_domain_id': 'test',
                 "pool_id": "6c346011-e581-429b-a7a2-6cdf0aba91c3",
                 "domain_id": "default"},
        ])
        mock_storage.get_pool.return_value = pools[0]
        test_filter = self.FILTER(storage=mock_storage)
        pools = test_filter.filter(self.context, pools, self.zone)

        self.assertEqual(len(pools), 2)

    def test_no_domain_id_pools(self):
        mock_storage = mock.Mock()
        mock_storage.find_shared_pools.return_value = []
        test_filter = self.FILTER(storage=mock_storage)
        pools = objects.PoolList.from_list(
            [
                {'id': '24702e43-8a52-440f-ab74-19fc16048860'},
                {'id': '5fabcd37-262c-4cf3-8625-7f419434b6df'}
            ]
        )
        pools = test_filter.filter(self.context, pools, self.zone)

        self.assertEqual(len(pools), 0)

    def test_multiple_domain_ids(self):
        current_pools = objects.PoolList.from_list(
            [
                {'id': '6c346011-e581-429b-a7a2-6cdf0aba91c3',
                 "domain_id": "default"},
                {'id': '5fabcd37-262c-4cf3-8625-7f419434b6df',
                 "domain_id": "test"}
            ]
        )
        mock_storage = mock.Mock()
        mock_storage.find_shared_pools.return_value = []
        mock_storage.get_pool.return_value = current_pools[0]
        test_filter = self.FILTER(storage=mock_storage)
        pools = test_filter.filter(self.context, current_pools, self.zone)

        self.assertEqual(1, len(pools))
        self.assertEqual(pools[0].id,
                         '5fabcd37-262c-4cf3-8625-7f419434b6df')

    def test_no_duplicate_when_pool_owned_and_shared(self):
        pool_id = '6c346011-e581-429b-a7a2-6cdf0aba91c3'
        current_pools = objects.PoolList.from_list([
            {'id': pool_id, 'domain_id': 'test'},
        ])
        mock_storage = mock.Mock()
        mock_storage.find_shared_pools.return_value = (
            objects.SharedPoolList.from_list([{
                'target_domain_id': 'test',
                'pool_id': pool_id,
                'domain_id': 'test',
            }])
        )
        test_filter = self.FILTER(storage=mock_storage)
        result = test_filter.filter(self.context, current_pools, self.zone)

        self.assertEqual(1, len(result))
        self.assertEqual(pool_id, result[0].id)

    def test_returns_all_pools_available_to_domain(self):
        # First in the chain the filter gets every pool. It has to return
        # all pools the domain may use, owned and shared, so that the
        # attribute filters after it can choose among them.
        own_id = '6c346011-e581-429b-a7a2-6cdf0aba91c3'
        shared_ids = ['5fabcd37-262c-4cf3-8625-7f419434b6df',
                      '24702e43-8a52-440f-ab74-19fc16048860']
        foreign_id = '794ccc2c-d751-44fe-b57f-8894c9f5c842'
        domainless_id = '67d71c2a-645c-4dde-a6b8-60a172c9ede8'
        current_pools = objects.PoolList.from_list([
            {'id': own_id, 'domain_id': 'test'},
            {'id': shared_ids[0], 'domain_id': 'default'},
            {'id': shared_ids[1], 'domain_id': 'iaas'},
            {'id': foreign_id, 'domain_id': 'default'},
            {'id': domainless_id},
        ])
        mock_storage = mock.Mock()
        mock_storage.find_shared_pools.return_value = (
            objects.SharedPoolList.from_list([
                {'target_domain_id': 'test',
                 'pool_id': shared_ids[0],
                 'domain_id': 'default'},
                {'target_domain_id': 'test',
                 'pool_id': shared_ids[1],
                 'domain_id': 'iaas'},
                {'target_domain_id': 'other',
                 'pool_id': foreign_id,
                 'domain_id': 'default'},
            ])
        )
        mock_storage.get_pool.side_effect = lambda context, pool_id: next(
            pool for pool in current_pools if pool.id == pool_id
        )
        test_filter = self.FILTER(storage=mock_storage)

        pools = test_filter.filter(self.context, current_pools, self.zone)

        self.assertEqual([own_id] + shared_ids, [pool.id for pool in pools])

    def test_does_not_add_pools_removed_by_previous_filters(self):
        # The attribute filter already picked one of the two pools shared
        # with the domain. Adding the other one back makes the scheduler
        # fail with MultiplePoolsFound.
        all_pools = objects.PoolList.from_list([
            {'id': '24702e43-8a52-440f-ab74-19fc16048860',
             'domain_id': 'default'},
            {'id': '5fabcd37-262c-4cf3-8625-7f419434b6df',
             'domain_id': 'default'},
        ])
        current_pools = objects.PoolList.from_list([
            {'id': '24702e43-8a52-440f-ab74-19fc16048860',
             'domain_id': 'default'},
        ])
        mock_storage = mock.Mock()
        mock_storage.find_shared_pools.return_value = (
            objects.SharedPoolList.from_list([
                {'target_domain_id': 'test',
                 'pool_id': pool.id,
                 'domain_id': 'default'}
                for pool in all_pools
            ])
        )
        mock_storage.get_pool.side_effect = lambda context, pool_id: next(
            pool for pool in all_pools if pool.id == pool_id
        )
        test_filter = self.FILTER(storage=mock_storage)

        pools = test_filter.filter(self.context, current_pools, self.zone)

        self.assertEqual(['24702e43-8a52-440f-ab74-19fc16048860'],
                         [pool.id for pool in pools])

    def test_does_not_add_shared_pool_to_empty_list(self):
        # The previous filters found no pool for the request. The zone must
        # not end up in the pool shared with the domain instead.
        shared_pool = objects.Pool.from_dict(
            {'id': '5fabcd37-262c-4cf3-8625-7f419434b6df',
             'domain_id': 'default'}
        )
        mock_storage = mock.Mock()
        mock_storage.find_shared_pools.return_value = (
            objects.SharedPoolList.from_list([{
                'target_domain_id': 'test',
                'pool_id': shared_pool.id,
                'domain_id': 'default',
            }])
        )
        mock_storage.get_pool.return_value = shared_pool
        test_filter = self.FILTER(storage=mock_storage)

        pools = test_filter.filter(self.context, objects.PoolList(), self.zone)

        self.assertEqual(0, len(pools))

    def test_keeps_own_pool_picked_by_previous_filters(self):
        # The attribute filter picked the domain's own pool. The pools shared
        # with the domain must not be added next to it.
        own_id = '6c346011-e581-429b-a7a2-6cdf0aba91c3'
        current_pools = objects.PoolList.from_list([
            {'id': own_id, 'domain_id': 'test'},
        ])
        mock_storage = mock.Mock()
        mock_storage.find_shared_pools.return_value = (
            objects.SharedPoolList.from_list([
                {'target_domain_id': 'test',
                 'pool_id': '5fabcd37-262c-4cf3-8625-7f419434b6df',
                 'domain_id': 'default'},
                {'target_domain_id': 'test',
                 'pool_id': '24702e43-8a52-440f-ab74-19fc16048860',
                 'domain_id': 'iaas'},
            ])
        )
        test_filter = self.FILTER(storage=mock_storage)

        pools = test_filter.filter(self.context, current_pools, self.zone)

        self.assertEqual([own_id], [pool.id for pool in pools])
        mock_storage.get_pool.assert_not_called()

    def test_drops_pool_not_available_to_domain(self):
        # The previous filters picked a pool that is shared with another
        # domain only.
        current_pools = objects.PoolList.from_list([
            {'id': '794ccc2c-d751-44fe-b57f-8894c9f5c842',
             'domain_id': 'default'},
        ])
        mock_storage = mock.Mock()
        mock_storage.find_shared_pools.return_value = (
            objects.SharedPoolList.from_list([{
                'target_domain_id': 'other',
                'pool_id': '794ccc2c-d751-44fe-b57f-8894c9f5c842',
                'domain_id': 'default',
            }])
        )
        test_filter = self.FILTER(storage=mock_storage)

        pools = test_filter.filter(self.context, current_pools, self.zone)

        self.assertEqual(0, len(pools))

    def test_domainless_context_ignores_shares(self):
        domainless_context = mock.Mock(project_domain_id=None)
        current_pools = objects.PoolList.from_list([
            {'id': '24702e43-8a52-440f-ab74-19fc16048860',
             'domain_id': 'default'},
            {'id': '5fabcd37-262c-4cf3-8625-7f419434b6df',
             'domain_id': 'iaas'},
        ])
        mock_storage = mock.Mock()
        test_filter = self.FILTER(storage=mock_storage)

        pools = test_filter.filter(
            domainless_context, current_pools, self.zone
        )

        self.assertEqual(2, len(pools))
        mock_storage.find_shared_pools.assert_not_called()


class PoolDomainsAttributeFilter(SchedulerFilterTest):
    FILTER = pool_domains_attribute_filter.PoolDomainsAttributeFilter

    def setUp(self):
        super().setUp()
        self.context.domain_id = 'domain1'
        self.context.domain = 'domain1'

    def test_one_pool(self):
        pools = objects.PoolList.from_list(
            [
                {
                    'id': '6c346011-e581-429b-a7a2-6cdf0aba91c3',
                }
            ]
        )
        pools = self.test_filter.filter(self.context, pools, self.zone)

        self.assertEqual('6c346011-e581-429b-a7a2-6cdf0aba91c3',
                         pools[0].id)

    def test_multiple_pools_all_match(self):
        pools = objects.PoolList.from_list(
            [
                {'id': '6c346011-e581-429b-a7a2-6cdf0aba91c3'},
                {'id': '5fabcd37-262c-4cf3-8625-7f419434b6df'}
            ]

        )

        attributes = objects.PoolAttributeList.from_list(
            [
                {
                    'key': 'domains',
                    'value': 'domain1,domain2,domain3'
                },
            ])

        pools[0].attributes = attributes
        pools[1].attributes = attributes

        pools = self.test_filter.filter(self.context, pools, self.zone)

        self.assertEqual(2, len(pools))

    def test_multiple_pools_one_match(self):
        pools = objects.PoolList.from_list(
            [
                {'id': '6c346011-e581-429b-a7a2-6cdf0aba91c3'},
                {'id': '5fabcd37-262c-4cf3-8625-7f419434b6df'}
            ]
        )

        pool_0_attributes = objects.PoolAttributeList.from_list(
            [
                {
                    'key': 'domains',
                    'value': 'domain1,domain2,domain3'
                },
            ])

        pool_1_attributes = objects.PoolAttributeList.from_list(
            [
                {
                    'key': 'domains',
                    'value': 'domain2,domain3'
                },
            ])

        pools[0].attributes = pool_0_attributes
        pools[1].attributes = pool_1_attributes

        pools = self.test_filter.filter(self.context, pools, self.zone)

        self.assertEqual(1, len(pools))
        self.assertEqual('6c346011-e581-429b-a7a2-6cdf0aba91c3', pools[0].id)

    def test_multiple_pools_no_match(self):
        pools = objects.PoolList.from_list(
            [
                {'id': '6c346011-e581-429b-a7a2-6cdf0aba91c3'},
                {'id': '5fabcd37-262c-4cf3-8625-7f419434b6df'}
            ]

        )

        pool_0_attributes = objects.PoolAttributeList.from_list(
            [
                {
                    'key': 'domains',
                    'value': 'domain4,domain2,domain3'
                },
            ])

        pool_1_attributes = objects.PoolAttributeList.from_list(
            [
                {
                    'key': 'domains',
                    'value': 'domain4,domain2,domain3'
                },
            ])

        pools[0].attributes = pool_0_attributes
        pools[1].attributes = pool_1_attributes

        pools = self.test_filter.filter(self.context, pools, self.zone)

        self.assertEqual(2, len(pools))

    def test_pool_attributes_not_set(self):
        pools = objects.PoolList.from_list(
            [
                {'id': '6c346011-e581-429b-a7a2-6cdf0aba91c3'},
                {'id': '5fabcd37-262c-4cf3-8625-7f419434b6df'}
            ]

        )

        pools = self.test_filter.filter(self.context, pools, self.zone)

        self.assertEqual(2, len(pools))

    def test_pool_attributes_empty(self):
        pools = objects.PoolList.from_list(
            [
                {'id': '6c346011-e581-429b-a7a2-6cdf0aba91c3'},
                {'id': '5fabcd37-262c-4cf3-8625-7f419434b6df'}
            ]

        )

        pools = self.test_filter.filter(self.context, pools, self.zone)
        pools[0].attributes = objects.PoolAttributeList.from_list([
                {
                    'key': 'attribute_one',
                    'value': 'True'
                },
        ]
        )
        pools[1].attributes = objects.PoolAttributeList.from_list([])
        self.assertEqual(2, len(pools))
