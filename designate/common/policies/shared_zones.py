# All Rights Reserved.
#
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
        name="get_shared_zone",
        check_str=base.RULE_ADMIN_OR_OWNER,
        description="Get Shared Zone",
        operations=[
            {
                'path': '/v2/zones/share/{shared_zone_id}',
                'method': 'GET'
            }
        ]
    ),
    policy.DocumentedRuleDefault(
        name="share_zone",
        check_str=base.RULE_ADMIN_OR_OWNER,
        description="Share Zone",
        operations=[
            {
                'path': '/v2/zones/share',
                'method': 'POST'
            }
        ]
    ),
    policy.DocumentedRuleDefault(
        name="find_shared_zones",
        check_str=base.RULE_ADMIN_OR_OWNER,
        description="List Shared Zones",
        operations=[
            {
                'path': '/v2/zones/share',
                'method': 'GET'
            }
        ]
    ),
    policy.DocumentedRuleDefault(
        name="unshare_zone",
        check_str=base.RULE_ADMIN_OR_OWNER,
        description="Unshare Zone",
        operations=[
            {
                'path': '/v2/zones/share/{shared_zone_id}',
                'method': 'DELETE'
            }
        ]
    )
]


def list_rules():
    return rules
