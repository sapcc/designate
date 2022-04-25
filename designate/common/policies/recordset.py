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


from oslo_log import versionutils
from oslo_policy import policy

from designate.common.policies import base

DEPRECATED_REASON = """
The record set API now supports system scope and default roles.
"""

deprecated_create_recordset = policy.DeprecatedRule(
    name="create_recordset",
    check_str=base.RULE_ZONE_PRIMARY_OR_ADMIN,
    deprecated_reason=DEPRECATED_REASON,
    deprecated_since=versionutils.deprecated.WALLABY
)
deprecated_get_recordsets = policy.DeprecatedRule(
    name="get_recordsets",
    check_str=base.RULE_ADMIN_OR_OWNER,
    deprecated_reason=DEPRECATED_REASON,
    deprecated_since=versionutils.deprecated.WALLABY
)
deprecated_get_recordset = policy.DeprecatedRule(
    name="get_recordset",
    check_str=base.RULE_ADMIN_OR_OWNER,
    deprecated_reason=DEPRECATED_REASON,
    deprecated_since=versionutils.deprecated.WALLABY
)
deprecated_update_recordset = policy.DeprecatedRule(
    name="update_recordset",
    check_str=base.RULE_ZONE_PRIMARY_OR_ADMIN,
    deprecated_reason=DEPRECATED_REASON,
    deprecated_since=versionutils.deprecated.WALLABY
)
deprecated_delete_recordset = policy.DeprecatedRule(
    name="delete_recordset",
    check_str=base.RULE_ZONE_PRIMARY_OR_ADMIN,
    deprecated_reason=DEPRECATED_REASON,
    deprecated_since=versionutils.deprecated.WALLABY
)
deprecated_count_recordset = policy.DeprecatedRule(
    name="count_recordset",
    check_str=base.RULE_ADMIN_OR_OWNER,
    deprecated_reason=DEPRECATED_REASON,
    deprecated_since=versionutils.deprecated.WALLABY
)

PROJECT_MEMBER_AND_PRIMARY_ZONE = (
    '(' + base.PROJECT_MEMBER + ') and (\'PRIMARY\':%(zone_type)s)'
)
SYSTEM_ADMIN_AND_PRIMARY_ZONE = (
    '(' + base.SYSTEM_ADMIN + ') and (\'PRIMARY\':%(zone_type)s)'
)
SYSTEM_ADMIN_AND_SECONDARY_ZONE = (
    '(' + base.SYSTEM_ADMIN + ') and (\'SECONDARY\':%(zone_type)s)'
)

SYSTEM_ADMIN_OR_PROJECT_MEMBER = ''.join(
    [PROJECT_MEMBER_AND_PRIMARY_ZONE,
     SYSTEM_ADMIN_AND_PRIMARY_ZONE,
     SYSTEM_ADMIN_AND_SECONDARY_ZONE]
)


rules = [
    policy.DocumentedRuleDefault(
        name="create_recordset",
        check_str=SYSTEM_ADMIN_AND_SECONDARY_ZONE,
        scope_types=['system', 'project'],
        description="Create Recordset",
        operations=[
            {
                'path': '/v2/zones/{zone_id}/recordsets',
                'method': 'POST'
            }, {
                'path': '/v2/reverse/floatingips/{region}:{floatingip_id}',
                'method': 'PATCH'
            }
        ],
        deprecated_rule=deprecated_create_recordset
    ),
    policy.RuleDefault(
        name="get_recordsets",
        check_str=base.RULE_ADMIN_OR_OWNER_OR_ZONE_SHARED,
        scope_types=['system', 'project'],
        deprecated_rule=deprecated_get_recordsets
    ),
    policy.DocumentedRuleDefault(
        name="get_recordset",
        check_str=base.RULE_ADMIN_OR_OWNER_OR_ZONE_SHARED,
        scope_types=['system', 'project'],
        description="Get recordset",
        operations=[
            {
                'path': '/v2/zones/{zone_id}/recordsets/{recordset_id}',
                'method': 'GET'
            }, {
                'path': '/v2/zones/{zone_id}/recordsets/{recordset_id}',
                'method': 'DELETE'
            }, {
                'path': '/v2/zones/{zone_id}/recordsets/{recordset_id}',
                'method': 'PUT'
            }
        ],
        deprecated_rule=deprecated_get_recordset
    ),
    policy.DocumentedRuleDefault(
        name="update_recordset",
        check_str=SYSTEM_ADMIN_AND_SECONDARY_ZONE,
        scope_types=['system', 'project'],
        description="Update recordset",
        operations=[
            {
                'path': '/v2/zones/{zone_id}/recordsets/{recordset_id}',
                'method': 'PUT'
            }, {
                'path': '/v2/reverse/floatingips/{region}:{floatingip_id}',
                'method': 'PATCH'
            }
        ],
        deprecated_rule=deprecated_update_recordset
    ),
    policy.DocumentedRuleDefault(
        name="delete_recordset",
        check_str=SYSTEM_ADMIN_AND_SECONDARY_ZONE,
        scope_types=['system', 'project'],
        description="Delete RecordSet",
        operations=[
            {
                'path': '/v2/zones/{zone_id}/recordsets/{recordset_id}',
                'method': 'DELETE'
            }
        ],
        deprecated_rule=deprecated_delete_recordset
    ),
    policy.RuleDefault(
        name="count_recordset",
        check_str=base.RULE_ADMIN_OR_OWNER_OR_ZONE_SHARED,
        scope_types=['system', 'project'],
        description="Count recordsets",
        deprecated_rule=deprecated_count_recordset
    ),
    policy.RuleDefault(
        name="find_recordset",
        check_str=base.RULE_ADMIN_OR_OWNER_OR_ZONE_SHARED,
        scope_types=['system', 'project'],
        description="Find recordsets"
    )
]


def list_rules():
    return rules
