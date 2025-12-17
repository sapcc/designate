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

from designate.exceptions import RelationNotLoaded
from designate import objects
from designate.scheduler.filters import base

LOG = logging.getLogger(__name__)


class PoolDomainsAttributeFilter(base.Filter):

    name = 'default_domain_name'
    """Name to enable in the ``[designate:central:scheduler].filters`` option
    list
    """

    def filter(self, context, pools, zone):
        """Attempt to load and set the pool by context domain name

        :param context: :class:`designate.context.DesignateContext` - Context
            Object from request
        :param pools: :class:`designate.objects.pool.PoolList` - List of pools
            to choose from
        :param zone: :class:`designate.objects.zone.Zone` - Zone to be created
        :return: :class:`designate.objects.pool.PoolList` -- A PoolList with
            containing a single pool.
        """
        if len(pools) < 2:
            return pools
        pools_list = objects.PoolList()
        for pool in pools:
            try:
                attrs = pool.attributes.to_dict()
                if "domains" in attrs:
                    pool_domains = attrs.get("domains").split(",")
                    if context.domain in pool_domains:
                        pools_list.append(pool)
            except RelationNotLoaded:
                continue
        if not pools_list:
            return pools
        return pools_list
