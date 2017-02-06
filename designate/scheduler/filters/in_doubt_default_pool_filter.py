# Copyright 2017 SAP SE
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

from oslo_config import cfg

from designate.scheduler.filters import base
from designate import objects

cfg.CONF.register_opts([
    cfg.StrOpt('default_pool_id',
               default='794ccc2c-d751-44fe-b57f-8894c9f5c842',
               help="The name of the default pool"),
], group='service:central')


class InDoubtDefaultPoolFilter(base.Filter):
    """If the previous filter(s) didn't make a clear selection of one pool,
    this filter will choose the default pool.

    If there are no pools available to schedule to, this filter will insert
    the default_pool_id, similar to the fallback filter.

    If there are multiple pools available to schedule to, this filter will
    choose the default pool, regardless whether the default pool is within the
    list of available pools.

    .. note::

        This should be used as one of the last filters.

    """

    name = 'in_doubt_default_pool'
    """Name to enable in the ``[designate:central:scheduler].filters`` option
    list
    """

    def filter(self, context, pools, zone):
        if len(pools) is not 1:
            pools = objects.PoolList()
            pools.append(
                objects.Pool(id=cfg.CONF['service:central'].default_pool_id))
            return pools
        else:
            return pools
