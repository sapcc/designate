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
from oslo_log import log as logging

from designate import objects
from designate.scheduler.filters import base

LOG = logging.getLogger(__name__)


class DomainIDFilter(base.Filter):
    """Filter pools by the Keystone domain of the user's project.

    Selects pools whose domain_id matches context.project_domain_id,
    plus any pools explicitly shared with that domain.

    .. warning::

        This should only be enabled if required, as it will restrict
        pool selection to domain-specific pools only.
    """

    name = 'domain_id'
    """Name to enable in the ``[designate:central:scheduler].filters`` option
    list
    """

    def filter(self, context, pools, zone):
        """Filter pools by project_domain_id from context.

        :param context: :class:`designate.context.DesignateContext`
        :param pools: :class:`designate.objects.pool.PoolList`
        :param zone: :class:`designate.objects.zone.Zone`
        :return: :class:`designate.objects.pool.PoolList`
        """
        # If the context has no project_domain_id (e.g. system-scoped token),
        # return all pools unchanged — no domain-based filtering applies.
        if not context.project_domain_id:
            return pools

        LOG.debug(
            'Filtering pools for project_domain_id=%s',
            context.project_domain_id
        )

        seen_pool_ids = set()
        pools_list = objects.PoolList()

        for pool in pools:
            if context.project_domain_id == pool.domain_id:
                pools_list.append(pool)
                seen_pool_ids.add(pool.id)

        shared_pool_list = self.storage.find_shared_pools(context)
        for shared_pool in shared_pool_list:
            if shared_pool.target_domain_id == context.project_domain_id:
                if shared_pool.pool_id not in seen_pool_ids:
                    pool = self.storage.get_pool(context, shared_pool.pool_id)
                    pools_list.append(pool)
                    seen_pool_ids.add(shared_pool.pool_id)

        LOG.debug(
            'Matched %d pools for project_domain_id=%s',
            len(pools_list), context.project_domain_id
        )
        if not pools_list:
            LOG.warning(
                'No matching pools for project_domain_id=%s',
                context.project_domain_id
            )
        return pools_list
