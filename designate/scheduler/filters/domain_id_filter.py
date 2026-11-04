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

    Keeps the pools whose domain_id matches context.project_domain_id,
    plus the pools explicitly shared with that domain.

    The filter only narrows the list it receives, so it can sit anywhere
    in the chain. First in the chain it returns every pool available to
    the domain, possibly several, and leaves the choice to the attribute
    filters; after them it only drops the pools the domain may not use.

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

        shared_pool_ids = {
            shared_pool.pool_id
            for shared_pool in self.storage.find_shared_pools(context)
            if shared_pool.target_domain_id == context.project_domain_id
        }

        pools_list = objects.PoolList()
        for pool in pools:
            if (pool.domain_id == context.project_domain_id or
                    pool.id in shared_pool_ids):
                pools_list.append(pool)

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
