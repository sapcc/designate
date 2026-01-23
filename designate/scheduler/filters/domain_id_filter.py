# Copyright 2025 Cloudification GmbH. All rights reserved.
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
    """

    .. warning::

        This should only be enabled if required, as it will raise a
        403 Forbidden if a user without the correct role uses it.
    """

    name = 'domain_id'
    """Name to enable in the ``[designate:central:scheduler].filters`` option
    list
    """

    def filter(self, context, pools, zone):
        """Attempt to load and set the pool by domain_id  from context.

        :param context: :class:`designate.context.DesignateContext` - Context
            Object from request
        :param pools: :class:`designate.objects.pool.PoolList` - List of pools
            to choose from
        :param zone: :class:`designate.objects.zone.Zone` - Zone to be created
        :return: :class:`designate.objects.pool.PoolList` -- A PoolList
            containing a single pool.
        :raises: Forbidden, PoolNotFound
        """
        pools_list = objects.PoolList()
        if not context.domain_id:
            return pools
        LOG.debug(f"Filtering pools for domain_id={context.domain_id}")
        for pool in pools:
            if context.domain_id == pool.domain_id:
                pools_list.append(pool)
        shared_pool_list = self.storage.find_shared_pools(context)
        if shared_pool_list:
            for shared_pool in shared_pool_list:
                if shared_pool.target_domain_id == context.domain_id:
                    pool = self.storage.get_pool(
                        context,
                        shared_pool.pool_id
                    )
                    pools_list.append(pool)
        LOG.debug(f"Matched {len(pools_list)} pools for domain {context.domain_id}")
        if not pools_list:
            LOG.warning(f"No matching pools for domain_id={context.domain_id}")
        return pools_list
