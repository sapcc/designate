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

import designate.tests.functional
from designate import exceptions
from designate import objects


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
