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
        self.context.domain_id = 'test'

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
        domainless_context.domain_id = None
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
        mock_storage.find_shared_pools.return_value = objects.SharedPoolList.from_list([ # noqa
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
        self.context.domain_id = "test"
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
