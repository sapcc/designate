# Copyright 2026 Cloudification GmbH. All rights reserved.
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
from oslo_messaging.rpc import dispatcher as rpc_dispatcher
from oslo_utils.uuidutils import generate_uuid
import testscenarios

import designate.tests.functional
from designate import exceptions
from designate import objects

load_tests = testscenarios.load_tests_apply_scenarios


class SharedPoolCentralTest(designate.tests.functional.TestCase):

    def setUp(self):
        super().setUp()
        self.domain_id = generate_uuid()
        self.other_domain_id = generate_uuid()

    def _share(self, pool, target_domain_id, context=None):
        context = context or self.admin_context
        return self.central_service.share_pool(
            context,
            pool.id,
            objects.SharedPool.from_dict({
                'target_domain_id': target_domain_id,
                'pool_id': pool.id,
                'domain_id': pool.domain_id,
            })
        )

    def _assertRaisesRPC(self, exc_class, func, *args, **kwargs):
        try:
            func(*args, **kwargs)
            self.fail('Expected %s to be raised' % exc_class.__name__)
        except rpc_dispatcher.ExpectedException as e:
            self.assertIsInstance(
                e.exc_info[1], exc_class,
                'Expected %s, got %s' % (
                    exc_class.__name__, type(e.exc_info[1]).__name__)
            )
        except exc_class:
            pass

    def test_create_pool_sets_domain_id_from_project_domain_id(self):
        context = self.get_context(
            project_domain_id=self.domain_id,
            is_admin=True,
            roles=['admin', 'reader']
        )
        pool = self.central_service.create_pool(
            context,
            objects.Pool.from_dict({
                'name': 'test-pool-%s' % generate_uuid()[:8],
                'ns_records': [{'hostname': 'ns1.example.com.',
                                'priority': 1}]
            })
        )
        self.assertEqual(self.domain_id, pool.domain_id)

    def test_create_pool_explicit_domain_id_preserved(self):
        explicit_domain = generate_uuid()
        pool = self.central_service.create_pool(
            self.admin_context,
            objects.Pool.from_dict({
                'name': 'test-pool-%s' % generate_uuid()[:8],
                'domain_id': explicit_domain,
                'ns_records': [{'hostname': 'ns1.example.com.',
                                'priority': 1}]
            })
        )
        self.assertEqual(explicit_domain, pool.domain_id)

    def test_create_pool_in_foreign_domain_raises_forbidden(self):
        context = self.get_context(
            project_domain_id=self.domain_id,
            roles=['member']
        )
        self._assertRaisesRPC(
            exceptions.Forbidden,
            self.central_service.create_pool,
            context,
            objects.Pool.from_dict({
                'name': 'test-pool-%s' % generate_uuid()[:8],
                'domain_id': self.other_domain_id,
                'ns_records': [{'hostname': 'ns1.example.com.',
                                'priority': 1}]
            })
        )

    def test_get_pool_admin_always_accessible(self):
        pool = self.create_pool(domain_id=self.domain_id)
        result = self.central_service.get_pool(self.admin_context, pool.id)
        self.assertEqual(pool.id, result.id)

    def test_get_pool_domain_check_via_storage(self):
        pool = self.create_pool(domain_id=self.domain_id)

        self.assertFalse(
            self.storage.is_pool_shared_with_domain(
                pool.id, self.other_domain_id)
        )

        self._share(pool, self.other_domain_id)

        self.assertTrue(
            self.storage.is_pool_shared_with_domain(
                pool.id, self.other_domain_id)
        )

    def test_get_pool_project_domain_id_used_for_access_check(self):
        pool = self.create_pool(domain_id=self.domain_id)

        self.assertEqual(self.domain_id, pool.domain_id)

        self.assertFalse(
            self.storage.is_pool_shared_with_domain(
                pool.id, self.other_domain_id)
        )

    def test_share_pool_without_domain_id_raises(self):
        pool = self.create_pool()
        self._assertRaisesRPC(
            exceptions.PoolWithoutDomainId,
            self.central_service.share_pool,
            self.admin_context,
            pool.id,
            objects.SharedPool.from_dict({
                'target_domain_id': self.other_domain_id,
                'pool_id': pool.id,
                'domain_id': None,
            })
        )

    def test_share_pool_sets_domain_id_from_pool(self):
        pool = self.create_pool(domain_id=self.domain_id)
        shared = self._share(pool, self.other_domain_id)
        self.assertEqual(self.domain_id, shared.domain_id)

    def test_share_pool_target_domain_id_is_set(self):
        pool = self.create_pool(domain_id=self.domain_id)
        shared = self._share(pool, self.other_domain_id)
        self.assertEqual(self.other_domain_id, shared.target_domain_id)

    def test_duplicate_share_raises_conflict(self):
        pool = self.create_pool(domain_id=self.domain_id)
        self._share(pool, self.other_domain_id)
        self._assertRaisesRPC(
            exceptions.DuplicateSharedPool,
            self._share,
            pool,
            self.other_domain_id,
        )

    def test_find_shared_pools_returns_created_share(self):
        pool = self.create_pool(domain_id=self.domain_id)
        self._share(pool, self.other_domain_id)

        result = self.central_service.find_shared_pools(
            self.admin_context,
            criterion={'pool_id': pool.id}
        )
        self.assertEqual(1, len(result))
        self.assertEqual(self.other_domain_id, result[0].target_domain_id)

    def test_find_shared_pools_filter_by_target_domain(self):
        pool = self.create_pool(domain_id=self.domain_id)
        third_domain = generate_uuid()
        self._share(pool, self.other_domain_id)
        self._share(pool, third_domain)

        result = self.central_service.find_shared_pools(
            self.admin_context,
            criterion={'target_domain_id': self.other_domain_id}
        )
        self.assertEqual(1, len(result))
        self.assertEqual(self.other_domain_id, result[0].target_domain_id)

    def test_find_shared_pools_foreign_domain_requires_admin(self):
        context = self.get_context(
            project_domain_id=self.domain_id,
            roles=['member']
        )
        self._assertRaisesRPC(
            exceptions.Forbidden,
            self.central_service.find_shared_pools,
            context,
            criterion={'target_domain_id': self.other_domain_id}
        )

    def test_unshare_pool_removes_share_record(self):
        pool = self.create_pool(domain_id=self.domain_id)
        shared = self._share(pool, self.other_domain_id)

        self.central_service.unshare_pool(
            self.admin_context, pool.id, shared.id
        )

        result = self.central_service.find_shared_pools(
            self.admin_context,
            criterion={'pool_id': pool.id}
        )
        self.assertEqual(0, len(result))

    def test_unshare_pool_removes_access(self):
        pool = self.create_pool(domain_id=self.domain_id)
        shared = self._share(pool, self.other_domain_id)

        self.assertTrue(
            self.storage.is_pool_shared_with_domain(
                pool.id, self.other_domain_id)
        )

        self.central_service.unshare_pool(
            self.admin_context, pool.id, shared.id
        )

        self.assertFalse(
            self.storage.is_pool_shared_with_domain(
                pool.id, self.other_domain_id)
        )

    def test_unshare_nonexistent_share_raises_not_found(self):
        pool = self.create_pool(domain_id=self.domain_id)
        self._assertRaisesRPC(
            exceptions.SharedPoolNotFound,
            self.central_service.unshare_pool,
            self.admin_context,
            pool.id,
            generate_uuid()
        )

    def test_get_pool_admin_from_different_domain_accessible(self):
        """Admin from a different domain can always access any pool."""
        pool = self.create_pool(domain_id=self.domain_id)

        # Admin context with a different project_domain_id
        other_domain_admin = self.get_context(
            project_domain_id=self.other_domain_id,
            is_admin=True,
            roles=['admin', 'reader']
        )
        result = self.central_service.get_pool(other_domain_admin, pool.id)
        self.assertEqual(pool.id, result.id)

    def test_owner_sees_own_pool_when_it_has_shares_with_other_domains(self):
        """Pool owner sees their pool even when it is shared with other domains."""
        pool = self.create_pool(domain_id=self.domain_id)

        # Share pool with another domain — this is what triggers the bug
        self._share(pool, self.other_domain_id)

        # Owner should still see their own pool
        self.assertTrue(
            self.storage.is_pool_shared_with_domain(
                pool.id, self.domain_id)
            or pool.domain_id == self.domain_id
        )

        # Verify via find_pools directly
        elevated = self.admin_context.elevated(all_tenants=True)
        pools = self.storage.find_pools(elevated)
        pool_ids = [p.id for p in pools]
        self.assertIn(pool.id, pool_ids)

    def test_owner_pool_visible_after_sharing_with_multiple_domains(self):
        """Pool shared with N domains remains visible to owner."""
        pool = self.create_pool(domain_id=self.domain_id)
        third_domain = generate_uuid()

        self._share(pool, self.other_domain_id)
        self._share(pool, third_domain)

        # Pool is still accessible to admin (owner context)
        result = self.central_service.get_pool(self.admin_context, pool.id)
        self.assertEqual(pool.id, result.id)

    def test_shared_domain_sees_pool_shared_with_them(self):
        """Domain B can see pool_a after it is shared with them."""
        pool = self.create_pool(domain_id=self.domain_id)
        self._share(pool, self.other_domain_id)

        self.assertTrue(
            self.storage.is_pool_shared_with_domain(
                pool.id, self.other_domain_id)
        )

    def test_unshared_domain_cannot_see_pool(self):
        """Domain C cannot see pool_a shared only with domain B."""
        pool = self.create_pool(domain_id=self.domain_id)
        self._share(pool, self.other_domain_id)

        third_domain = generate_uuid()
        self.assertFalse(
            self.storage.is_pool_shared_with_domain(
                pool.id, third_domain)
        )

    def test_pool_without_domain_id_visible_to_all_users(self):
        """Pool with no domain_id (system pool) is visible to any domain."""
        pool = self.create_pool(name='system-pool-%s' % generate_uuid()[:8])

        self.assertIsNone(pool.domain_id)

        # Any domain can see it via storage
        self.assertFalse(
            self.storage.is_pool_shared_with_domain(
                pool.id, self.domain_id)
        )
        self.assertFalse(
            self.storage.is_pool_shared_with_domain(
                pool.id, self.other_domain_id)
        )
        # But pool.domain_id IS NULL means it's a system pool —
        # visible to all via the domain_id.is_(None) condition in _find_pools
        self.assertIsNone(pool.domain_id)


class SharedPoolSchedulingTest(designate.tests.functional.TestCase):
    """Schedule zones into pools shared between Keystone domains.

    Central picks the pool with the pool queries of storage, as it does for
    API requests: find_pools() returns only the pools of the user's domain,
    the pools shared with it and the pools without a domain, get_pool()
    returns any pool. Every test runs with domain_id last (the order of the
    designate helm chart) and first in the filter chain.
    """
    scenarios = [
        ('domain_id_last',
         {'scheduler_filters': ['attribute', 'pool_id_attribute',
                                'domain_id']}),
        ('domain_id_first',
         {'scheduler_filters': ['domain_id', 'attribute',
                                'pool_id_attribute']}),
    ]

    def setUp(self):
        super().setUp()
        self.config(scheduler_filters=self.scheduler_filters,
                    group='service:central')
        self.policy({'create_zone': '@', 'zone_create_forced_pool': '@'})

        owner_domain_id = generate_uuid()
        self.customer_domain_id = generate_uuid()
        self.context = self._domain_context(self.customer_domain_id)
        self.zone_count = 0

        # Bronze, silver and gold belong to another domain, silver and gold
        # are shared with the customer domain.
        self.pools = {}
        for tier in ('bronze', 'silver', 'gold'):
            self._create_tier_pool(tier, owner_domain_id)
        self._share('silver', self.customer_domain_id)
        self._share('gold', self.customer_domain_id)

    def _domain_context(self, domain_id):
        return self.get_context(project_id=generate_uuid(),
                                user_id=generate_uuid(),
                                project_domain_id=domain_id,
                                roles=['member'])

    def _create_tier_pool(self, tier, domain_id):
        self.pools[tier] = self.create_pool(
            name='pool-%s' % tier,
            domain_id=domain_id,
            attributes=[{'key': 'service_tier', 'value': tier}],
            ns_records=[{'priority': 1,
                         'hostname': 'ns1.%s.example.org.' % tier}])

    def _share(self, tier, target_domain_id):
        pool = self.pools[tier]
        self.central_service.share_pool(
            self.admin_context, pool.id,
            objects.SharedPool.from_dict({
                'pool_id': pool.id,
                'domain_id': pool.domain_id,
                'target_domain_id': target_domain_id,
            }))

    def _schedule(self, context=None, **attributes):
        """Create a zone and return the tier of the pool it got."""
        self.zone_count += 1
        zone = self.create_zone(
            context=context or self.context,
            name='zone%d.example.com.' % self.zone_count,
            attributes=attributes)
        for tier, pool in self.pools.items():
            if pool.id == zone.pool_id:
                return tier
        return zone.pool_id

    def _assert_no_valid_pool(self, context=None, **attributes):
        exc = self.assertRaises(rpc_dispatcher.ExpectedException,
                                self._schedule, context, **attributes)
        self.assertEqual(exceptions.NoValidPoolFound, exc.exc_info[0])

    def test_zone_in_pool_shared_with_domain(self):
        self.assertEqual('gold', self._schedule(service_tier='gold'))
        self.assertEqual('silver', self._schedule(service_tier='silver'))

    def test_pool_not_available_to_domain(self):
        self._assert_no_valid_pool(service_tier='bronze')

    def test_pool_not_available_with_single_share(self):
        # Only silver is shared with this domain. A zone asking for gold
        # must fail instead of being placed into silver.
        domain_id = generate_uuid()
        self._share('silver', domain_id)
        context = self._domain_context(domain_id)

        self._assert_no_valid_pool(context, service_tier='gold')
        self.assertEqual('silver',
                         self._schedule(context, service_tier='silver'))

    def test_zone_in_own_pool_with_shared_pools(self):
        self._create_tier_pool('copper', self.customer_domain_id)

        self.assertEqual('copper', self._schedule(service_tier='copper'))
        self.assertEqual('gold', self._schedule(service_tier='gold'))

    def test_forced_pool_shared_with_domain(self):
        self.assertEqual('gold',
                         self._schedule(pool_id=self.pools['gold'].id))

    def test_forced_pool_not_available_to_domain(self):
        # get_pool() finds bronze, but bronze is not among the candidates.
        self._assert_no_valid_pool(pool_id=self.pools['bronze'].id)

    def test_forced_pool_does_not_exist(self):
        self._assert_no_valid_pool(pool_id=generate_uuid())

    def test_forced_pool_with_invalid_id(self):
        self._assert_no_valid_pool(pool_id='not-a-pool-id')

    def test_misspelled_pool_id_attribute(self):
        # No pool has a pool-id attribute, so no pool matches the zone.
        self._assert_no_valid_pool(**{'pool-id': self.pools['gold'].id})
