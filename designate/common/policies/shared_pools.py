# Copyright 2025 Cloudification GmbH. All rights reserved.
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.
from oslo_policy import policy

from designate.common.policies import base

rules = [
    policy.DocumentedRuleDefault(
        name="get_pool_share",
        check_str=base.RULE_ADMIN,
        scope_types=['system', 'domain', 'project'],
        description="Get a Pool Share",
        operations=[
            {
                'path': '/v2/pools/{pool_id}/shares/{pool_share_id}',
                'method': 'GET'
            }
        ],
    ),
    policy.DocumentedRuleDefault(
        name="share_pool",
        check_str=base.RULE_ADMIN,
        scope_types=['system', 'domain', 'project'],
        description="Share a Pool",
        operations=[
            {
                'path': '/v2/pools/{pool_id}/shares',
                'method': 'POST'
            }
        ],
    ),
    policy.DocumentedRuleDefault(
        name="find_pool_shares",
        # Using rule ANY here because the search criteria will narrow the
        # results appropriate for the API call.
        check_str=base.RULE_ANY,
        description="List Shared Pools",
        operations=[
            {
                'path': '/v2/pools/{pool_id}/shares',
                'method': 'GET'
            }
        ]
    ),
    policy.RuleDefault(
        name="find_domain_pool_share",
        check_str=base.RULE_ADMIN,
        scope_types=['system', 'domain', 'project'],
        description="Check the can query for a specific domains shares.",
    ),
    policy.DocumentedRuleDefault(
        name="unshare_pool",
        check_str=base.RULE_ADMIN,
        scope_types=['system', 'domain', 'project'],
        description="Unshare Pool",
        operations=[
            {
                'path': '/v2/pools/{pool_id}/shares/{shared_pool_id}',
                'method': 'DELETE'
            }
        ],
    )
]


def list_rules():
    return rules
