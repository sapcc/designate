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
import pecan

from designate.api.v2.controllers import rest
from designate.common import keystone
from designate.objects.adapters import DesignateAdapter
from designate.objects import SharedPool
from designate import utils

LOG = logging.getLogger(__name__)


class SharedPoolsController(rest.RestController):
    SORT_KEYS = ['created_at', 'updated_at', ]

    @pecan.expose(template='json:', content_type='application/json')
    @utils.validate_uuid('pool_id', 'pool_share_id')
    def get_one(self, pool_id, pool_share_id):
        """Get Pool Share"""
        request = pecan.request
        context = request.environ['context']

        pool = self.central_api.get_shared_pool(
                context, pool_id, pool_share_id)

        LOG.info(
            "Retrieved %(pool)s",
            {"pool": pool}
        )

        return DesignateAdapter.render('API_v2', pool, request=request)

    @pecan.expose(template='json:', content_type='application/json')
    @utils.validate_uuid('pool_id')
    def get_all(self, pool_id, **params):
        """List all Shared Pools"""
        request = pecan.request
        context = request.environ['context']

        # Extract the pagination params
        marker, limit, sort_key, sort_dir = utils.get_paging_params(
            context, params, self.SORT_KEYS)

        # Extract any filter params
        accepted_filters = ('target_domain_id',)
        criterion = self._apply_filter_params(
            params, accepted_filters, {})

        criterion['pool_id'] = pool_id

        shared_pools = self.central_api.find_shared_pools(
            context, criterion, marker, limit, sort_key, sort_dir)

        LOG.info("Retrieved %(shared_pools)s", {'shared_pools': shared_pools})

        return DesignateAdapter.render('API_v2', shared_pools, request=request)

    @pecan.expose(template='json:', content_type='application/json')
    @utils.validate_uuid('pool_id')
    def post_all(self, pool_id):
        """Share Pool"""
        request = pecan.request
        response = pecan.response
        context = request.environ['context']

        payload = request.body_dict

        keystone.verify_domain_id(
            context, payload.get('target_domain_id', None)
        )

        pool_share = DesignateAdapter.parse('API_v2', payload, SharedPool())

        pool_share = self.central_api.share_pool(context, pool_id, pool_share)

        response.status_int = 201

        LOG.info(
            "Shared pool %(shared_pool)s",
            {'shared_pool': pool_share}
        )

        return DesignateAdapter.render(
            'API_v2', pool_share, request=request)

    @pecan.expose(template='json:', content_type='application/json')
    @utils.validate_uuid('pool_id', 'pool_share_id')
    def delete_one(self, pool_id, pool_share_id):
        """Unshare Pool"""
        request = pecan.request
        response = pecan.response
        context = request.environ['context']

        pool = self.central_api.unshare_pool(context, pool_id, pool_share_id)
        response.status_int = 204

        LOG.info("Unshared pool %(pool)s", {'pool': pool})
