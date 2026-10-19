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

from oslo_config import fixture as cfg_fixture
import oslotest.base
import testscenarios

import designate.conf
from designate import exceptions
from designate import objects
from designate import scheduler


CONF = designate.conf.CONF
load_tests = testscenarios.load_tests_apply_scenarios

DEFAULT_POOL_ID = BRONZE_POOL_ID = '67d71c2a-645c-4dde-a6b8-60a172c9ede8'
SILVER_POOL_ID = '5fabcd37-262c-4cf3-8625-7f419434b6df'
GOLD_POOL_ID = '24702e43-8a52-440f-ab74-19fc16048860'


def build_test_pools():
    pools = objects.PoolList.from_list(
        [
            {'id': DEFAULT_POOL_ID},
            {'id': SILVER_POOL_ID},
            {'id': GOLD_POOL_ID},
        ]

    )

    # Pool 0 is also the default pool.
    pool_0_attributes = objects.PoolAttributeList.from_list([
        {
            'key': 'service_tier',
            'value': 'bronze'
        },
    ])
    pool_1_attributes = objects.PoolAttributeList.from_list([
        {
            'key': 'service_tier',
            'value': 'silver'
        },
    ])
    pool_2_attributes = objects.PoolAttributeList.from_list([
        {
            'key': 'service_tier',
            'value': 'gold'
        },
    ])

    pools[0].attributes = pool_0_attributes
    pools[1].attributes = pool_1_attributes
    pools[2].attributes = pool_2_attributes

    return pools


class AttributeSchedulerPermutationsTest(oslotest.base.BaseTestCase):
    def setUp(self):
        super().setUp()
        self.CONF = self.useFixture(cfg_fixture.Config(CONF)).conf
        self.context = mock.Mock()

        self.CONF.set_override(
            'scheduler_filters', ['attribute'], 'service:central'
        )
        self.CONF.set_override(
            'default_pool_id', DEFAULT_POOL_ID, 'service:central'
        )

        attrs = {
            'find_pools.return_value': build_test_pools()
        }
        mock_storage = mock.Mock(**attrs)

        self.scheduler = scheduler.get_scheduler(storage=mock_storage)

    def test_get_gold_tier(self):
        zone = objects.Zone(
            name='example.com.',
            type='PRIMARY',
            email='hostmaster@example.com',
            attributes=objects.ZoneAttributeList.from_list(
                [
                    {
                        'key': 'service_tier',
                        'value': 'gold'
                    },
                ]
            )
        )

        result = self.scheduler.schedule_zone(self.context, zone)

        self.assertEqual(GOLD_POOL_ID, result)

    def test_get_silver_tier(self):
        zone = objects.Zone(
            name='example.com.',
            type='PRIMARY',
            email='hostmaster@example.com',
            attributes=objects.ZoneAttributeList.from_list(
                [
                    {
                        'key': 'service_tier',
                        'value': 'silver'
                    },
                ]
            )
        )

        result = self.scheduler.schedule_zone(self.context, zone)

        self.assertEqual(SILVER_POOL_ID, result)

    def test_get_bronze_tier(self):
        zone = objects.Zone(
            name='example.com.',
            type='PRIMARY',
            email='hostmaster@example.com',
            attributes=objects.ZoneAttributeList.from_list(
                [
                    {
                        'key': 'service_tier',
                        'value': 'bronze'
                    },
                ]
            )
        )

        result = self.scheduler.schedule_zone(self.context, zone)

        self.assertEqual(BRONZE_POOL_ID, result)

    def test_tier_not_found_raises_exception(self):
        zone = objects.Zone(
            name='example.com.',
            type='PRIMARY',
            email='hostmaster@example.com',
            attributes=objects.ZoneAttributeList.from_list(
                [
                    {
                        'key': 'service_tier',
                        'value': 'blue'
                    },
                ]
            )
        )

        self.assertRaises(
            exceptions.NoValidPoolFound,
            self.scheduler.schedule_zone, self.context, zone
        )

    def test_no_tier_raises_exception(self):
        zone = objects.Zone(
            name='example.com.',
            type='PRIMARY',
            email='hostmaster@example.com',
            attributes=objects.ZoneAttributeList.from_list(
                []
            )
        )

        # When no attribute is requested it will return all available pools.
        # NOTE(eandersson): This is probably not intended behavior.
        #                   We probably want this to return NoValidPoolFound,
        #                   so that we can use a fallback filter with the
        #                   attribute filter.
        self.assertRaises(
            exceptions.MultiplePoolsFound,
            self.scheduler.schedule_zone, self.context, zone
        )


class DefaultSchedulerPermutationsTest(oslotest.base.BaseTestCase):
    def setUp(self):
        super().setUp()
        self.CONF = self.useFixture(cfg_fixture.Config(CONF)).conf
        self.context = mock.Mock()

        self.CONF.set_override(
            'scheduler_filters', ['default_pool'], 'service:central'
        )
        self.CONF.set_override(
            'default_pool_id', DEFAULT_POOL_ID, 'service:central'
        )

        attrs = {
            'find_pools.return_value': build_test_pools()
        }
        mock_storage = mock.Mock(**attrs)

        self.scheduler = scheduler.get_scheduler(storage=mock_storage)

    def test_get_default_pool(self):
        zone = objects.Zone(
            name='example.com.',
            type='PRIMARY',
            email='hostmaster@example.com',
        )

        result = self.scheduler.schedule_zone(self.context, zone)

        self.assertEqual(DEFAULT_POOL_ID, result)


class FallbackSchedulerPermutationsTest(oslotest.base.BaseTestCase):
    def setUp(self):
        super().setUp()
        self.CONF = self.useFixture(cfg_fixture.Config(CONF)).conf
        self.context = mock.Mock()

        self.CONF.set_override(
            'scheduler_filters', ['attribute', 'fallback'], 'service:central'
        )
        self.CONF.set_override(
            'default_pool_id', DEFAULT_POOL_ID, 'service:central'
        )

        attrs = {
            'find_pools.return_value': build_test_pools()
        }
        mock_storage = mock.Mock(**attrs)

        self.scheduler = scheduler.get_scheduler(storage=mock_storage)

    def test_tier_not_found_return_default(self):
        zone = objects.Zone(
            name='example.com.',
            type='PRIMARY',
            email='hostmaster@example.com',
            attributes=objects.ZoneAttributeList.from_list(
                [
                    {
                        'key': 'service_tier',
                        'value': 'that does not exist'
                    },
                ]
            )
        )

        result = self.scheduler.schedule_zone(self.context, zone)

        self.assertEqual(DEFAULT_POOL_ID, result)


OWNER_DOMAIN_ID = 'owner-domain'
IAAS_DOMAIN_ID = 'iaas-domain'
CUSTOMER_DOMAIN_ID = 'customer-domain'

DOMAIN_ID_FILTER_ORDERS = [
    # The order used for shared pools by the designate helm chart.
    ('domain_id_last',
     {'scheduler_filters': ['attribute', 'pool_id_attribute', 'domain_id']}),
    ('domain_id_first',
     {'scheduler_filters': ['domain_id', 'attribute', 'pool_id_attribute']}),
]
STORAGE_POOL_VIEWS = [
    # storage.find_pools() returns every pool to an elevated context, and to
    # API users only the pools owned by or shared with their domain plus the
    # pools without a domain.
    ('admin', {'admin_view': True}),
    ('member', {'admin_view': False}),
]


def build_domain_test_pools():
    # Bronze (the default pool) and silver belong to the owner domain, gold
    # to an IaaS domain. No pool belongs to the customer domain.
    pools = build_test_pools()
    pools[0].domain_id = OWNER_DOMAIN_ID
    pools[1].domain_id = OWNER_DOMAIN_ID
    pools[2].domain_id = IAAS_DOMAIN_ID
    return pools


def build_zone(attributes=None):
    zone = objects.Zone(
        name='example.com.',
        type='PRIMARY',
        email='hostmaster@example.com'
    )
    if attributes is not None:
        zone.attributes = objects.ZoneAttributeList.from_list(
            [{'key': key, 'value': value} for key, value in attributes.items()]
        )
    return zone


class DomainIDSchedulerPermutationsTest(oslotest.base.BaseTestCase):
    """Pools shared between Keystone domains (pools RBAC).

    Every test runs with domain_id last and first in the filter chain and
    with the admin and the member view of the pools in storage. The
    scheduling result must be the same in all of them.
    """
    scenarios = testscenarios.multiply_scenarios(
        DOMAIN_ID_FILTER_ORDERS, STORAGE_POOL_VIEWS
    )

    def setUp(self):
        super().setUp()
        self.CONF = self.useFixture(cfg_fixture.Config(CONF)).conf
        self.CONF.set_override(
            'scheduler_filters', self.scheduler_filters, 'service:central'
        )
        self.CONF.set_override(
            'default_pool_id', DEFAULT_POOL_ID, 'service:central'
        )
        self.context = mock.Mock(project_domain_id=CUSTOMER_DOMAIN_ID,
                                 project_domain_name='customer')

        self.pools = build_domain_test_pools()
        self.shares = [
            (SILVER_POOL_ID, CUSTOMER_DOMAIN_ID),
            (GOLD_POOL_ID, CUSTOMER_DOMAIN_ID),
        ]
        storage = mock.Mock()
        storage.find_pools.side_effect = self._find_pools
        storage.get_pool.side_effect = self._get_pool
        storage.find_shared_pools.side_effect = self._find_shared_pools

        self.scheduler = scheduler.get_scheduler(storage=storage)

    def _find_pools(self, context, *args, **kwargs):
        # The same rule as the domain aware pool query in storage.
        domain_id = context.project_domain_id
        visible = [
            pool for pool in self.pools
            if self.admin_view or not domain_id or
            pool.domain_id in (domain_id, None) or
            (pool.id, domain_id) in self.shares
        ]
        return objects.PoolList(objects=visible)

    def _get_pool(self, context, pool_id):
        # Unlike find_pools(), storage.get_pool() does not filter by domain.
        for pool in self.pools:
            if pool.id == pool_id:
                return pool
        raise exceptions.PoolNotFound()

    def _find_shared_pools(self, context, *args, **kwargs):
        owners = {pool.id: pool.domain_id for pool in self.pools}
        return objects.SharedPoolList.from_list([
            {
                'pool_id': pool_id,
                'domain_id': owners[pool_id],
                'target_domain_id': target_domain_id,
            }
            for pool_id, target_domain_id in self.shares
        ])

    def schedule(self, **attributes):
        zone = build_zone(attributes)
        return self.scheduler.schedule_zone(self.context, zone)

    def test_zone_in_pool_shared_with_domain(self):
        self.assertEqual(GOLD_POOL_ID, self.schedule(service_tier='gold'))
        self.assertEqual(SILVER_POOL_ID, self.schedule(service_tier='silver'))

    def test_pool_not_available_to_domain(self):
        # Bronze is neither owned by nor shared with the customer domain.
        self.assertRaises(
            exceptions.NoValidPoolFound, self.schedule, service_tier='bronze'
        )

    def test_pool_not_available_with_single_share(self):
        # Only silver is shared. A zone asking for gold must fail instead of
        # being placed into silver.
        self.shares = [(SILVER_POOL_ID, CUSTOMER_DOMAIN_ID)]

        self.assertRaises(
            exceptions.NoValidPoolFound, self.schedule, service_tier='gold'
        )

    def test_zone_in_own_pool_with_shared_pools(self):
        # The customer domain owns bronze and gets silver and gold shared.
        self.pools[0].domain_id = CUSTOMER_DOMAIN_ID

        self.assertEqual(BRONZE_POOL_ID, self.schedule(service_tier='bronze'))
        self.assertEqual(GOLD_POOL_ID, self.schedule(service_tier='gold'))

    def test_pool_owned_by_and_shared_with_domain(self):
        # Silver belongs to the customer domain and is shared with it too.
        self.pools[1].domain_id = CUSTOMER_DOMAIN_ID

        self.assertEqual(SILVER_POOL_ID, self.schedule(service_tier='silver'))

    def test_owner_domain_with_pool_shared_with_it(self):
        # Like the cloud admin domain approving zone requests: it owns
        # bronze and silver and gets gold shared on top.
        self.context.project_domain_id = OWNER_DOMAIN_ID
        self.shares.append((GOLD_POOL_ID, OWNER_DOMAIN_ID))

        self.assertEqual(SILVER_POOL_ID, self.schedule(service_tier='silver'))
        self.assertEqual(GOLD_POOL_ID, self.schedule(service_tier='gold'))

    def test_shares_with_other_domains_are_ignored(self):
        self.shares = [
            (SILVER_POOL_ID, 'other-domain'),
            (GOLD_POOL_ID, CUSTOMER_DOMAIN_ID),
        ]

        self.assertEqual(GOLD_POOL_ID, self.schedule(service_tier='gold'))
        self.assertRaises(
            exceptions.NoValidPoolFound, self.schedule, service_tier='silver'
        )

    def test_context_without_domain(self):
        # A system scoped token has no project domain: no domain filtering.
        self.context.project_domain_id = None

        self.assertEqual(BRONZE_POOL_ID, self.schedule(service_tier='bronze'))

    def test_zone_without_attributes_is_ambiguous(self):
        # Two pools are available to the domain and nothing picks one.
        self.assertRaises(
            exceptions.MultiplePoolsFound,
            self.scheduler.schedule_zone, self.context, build_zone()
        )
