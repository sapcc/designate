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
The zone API now supports system scope and default roles.
"""

deprecated_create_zone = policy.DeprecatedRule(
    name="create_zone",
    check_str=base.RULE_ADMIN_OR_OWNER,
    deprecated_reason=DEPRECATED_REASON,
    deprecated_since=versionutils.deprecated.WALLABY
)
deprecated_get_zones = policy.DeprecatedRule(
    name="get_zones",
    check_str=base.RULE_ADMIN_OR_OWNER,
    deprecated_reason=DEPRECATED_REASON,
    deprecated_since=versionutils.deprecated.WALLABY
)
deprecated_get_zone = policy.DeprecatedRule(
    name="get_zone",
    check_str=base.RULE_ADMIN_OR_OWNER,
    deprecated_reason=DEPRECATED_REASON,
    deprecated_since=versionutils.deprecated.WALLABY
)
deprecated_get_zone_servers = policy.DeprecatedRule(
    name="get_zone_servers",
    check_str=base.RULE_ADMIN_OR_OWNER,
    deprecated_reason=DEPRECATED_REASON,
    deprecated_since=versionutils.deprecated.WALLABY
)
deprecated_find_zones = policy.DeprecatedRule(
    name="find_zones",
    check_str=base.RULE_ADMIN_OR_OWNER,
    deprecated_reason=DEPRECATED_REASON,
    deprecated_since=versionutils.deprecated.WALLABY
)
deprecated_update_zone = policy.DeprecatedRule(
    name="update_zone",
    check_str=base.RULE_ADMIN_OR_OWNER,
    deprecated_reason=DEPRECATED_REASON,
    deprecated_since=versionutils.deprecated.WALLABY
)
deprecated_delete_zone = policy.DeprecatedRule(
    name="delete_zone",
    check_str=base.RULE_ADMIN_OR_OWNER,
    deprecated_reason=DEPRECATED_REASON,
    deprecated_since=versionutils.deprecated.WALLABY
)
deprecated_xfr_zone = policy.DeprecatedRule(
    name="xfr_zone",
    check_str=base.RULE_ADMIN_OR_OWNER,
    deprecated_reason=DEPRECATED_REASON,
    deprecated_since=versionutils.deprecated.WALLABY
)
deprecated_abandon_zone = policy.DeprecatedRule(
    name="abandon_zone",
    check_str=base.RULE_ADMIN,
    deprecated_reason=DEPRECATED_REASON,
    deprecated_since=versionutils.deprecated.WALLABY
)
deprecated_count_zones = policy.DeprecatedRule(
    name="count_zones",
    check_str=base.RULE_ADMIN_OR_OWNER,
    deprecated_reason=DEPRECATED_REASON,
    deprecated_since=versionutils.deprecated.WALLABY
)
deprecated_count_zones_pending_notify = policy.DeprecatedRule(
    name="count_zones_pending_notify",
    check_str=base.RULE_ADMIN_OR_OWNER,
    deprecated_reason=DEPRECATED_REASON,
    deprecated_since=versionutils.deprecated.WALLABY
)
deprecated_purge_zones = policy.DeprecatedRule(
    name="purge_zones",
    check_str=base.RULE_ADMIN,
    deprecated_reason=DEPRECATED_REASON,
    deprecated_since=versionutils.deprecated.WALLABY
)
deprecated_touch_zone = policy.DeprecatedRule(
    name="touch_zone",
    check_str=base.RULE_ADMIN_OR_OWNER,
    deprecated_reason=DEPRECATED_REASON,
    deprecated_since=versionutils.deprecated.WALLABY
)


rules = [
    policy.DocumentedRuleDefault(
        name="create_zone",
        check_str=base.SYSTEM_ADMIN_OR_PROJECT_MEMBER,
        scope_types=['system', 'project'],
        description="Create Zone",
        operations=[
            {
                'path': '/v2/zones',
                'method': 'POST'
            }
        ],
        deprecated_rule=deprecated_create_zone
    ),
    policy.RuleDefault(
        name="get_zones",
        check_str=base.SYSTEM_OR_PROJECT_READER,
        scope_types=['system', 'project'],
        deprecated_rule=deprecated_get_zones
    ),
    policy.DocumentedRuleDefault(
        name="get_zone",
        check_str=base.RULE_ADMIN_OR_OWNER_OR_ZONE_SHARED,
        scope_types=['system', 'project'],
        description="Get Zone",
        operations=[
            {
                'path': '/v2/zones/{zone_id}',
                'method': 'GET'
            }, {
                'path': '/v2/zones/{zone_id}',
                'method': 'PATCH'
            }, {
                'path': '/v2/zones/{zone_id}/recordsets/{recordset_id}',
                'method': 'PUT'
            }
        ],
        deprecated_rule=deprecated_get_zone
    ),
    policy.RuleDefault(
        name="get_zone_servers",
        check_str=base.SYSTEM_OR_PROJECT_READER,
        scope_types=['system', 'project'],
        deprecated_rule=deprecated_get_zone_servers
    ),
    policy.DocumentedRuleDefault(
        name="find_zones",
        check_str=base.SYSTEM_OR_PROJECT_READER,
        scope_types=['system', 'project'],
        description="List existing zones",
        operations=[
            {
                'path': '/v2/zones',
                'method': 'GET'
            }
        ],
        deprecated_rule=deprecated_get_zone_servers
    ),
    policy.DocumentedRuleDefault(
        name="update_zone",
        check_str=base.SYSTEM_ADMIN_OR_PROJECT_MEMBER,
        scope_types=['system', 'project'],
        description="Update Zone",
        operations=[
            {
                'path': '/v2/zones/{zone_id}',
                'method': 'PATCH'
            }
        ],
        deprecated_rule=deprecated_update_zone
    ),
    policy.DocumentedRuleDefault(
        name="delete_zone",
        check_str=base.SYSTEM_ADMIN_OR_PROJECT_MEMBER,
        scope_types=['system', 'project'],
        description="Delete Zone",
        operations=[
            {
                'path': '/v2/zones/{zone_id}',
                'method': 'DELETE'
            }
        ],
        deprecated_rule=deprecated_delete_zone
    ),
    policy.DocumentedRuleDefault(
        name="xfr_zone",
        check_str=base.SYSTEM_ADMIN_OR_PROJECT_MEMBER,
        scope_types=['system', 'project'],
        description="Manually Trigger an Update of a Secondary Zone",
        operations=[
            {
                'path': '/v2/zones/{zone_id}/tasks/xfr',
                'method': 'POST'
            }
        ],
        deprecated_rule=deprecated_xfr_zone
    ),
    policy.DocumentedRuleDefault(
        name="abandon_zone",
        check_str=base.SYSTEM_ADMIN,
        scope_types=['system'],
        description="Abandon Zone",
        operations=[
            {
                'path': '/v2/zones/{zone_id}/tasks/abandon',
                'method': 'POST'
            }
        ],
        deprecated_rule=deprecated_abandon_zone
    ),
    policy.RuleDefault(
        name="count_zones",
        check_str=base.SYSTEM_OR_PROJECT_READER,
        scope_types=['system', 'project'],
        deprecated_rule=deprecated_count_zones
    ),
    policy.RuleDefault(
        name="count_zones_pending_notify",
        check_str=base.SYSTEM_OR_PROJECT_READER,
        scope_types=['system', 'project'],
        deprecated_rule=deprecated_count_zones_pending_notify
    ),
    policy.RuleDefault(
        name="purge_zones",
        check_str=base.SYSTEM_ADMIN,
        scope_types=['system'],
        deprecated_rule=deprecated_purge_zones
    ),
    policy.RuleDefault(
        name="touch_zone",
        check_str=base.SYSTEM_ADMIN_OR_PROJECT_MEMBER,
        scope_types=['system', 'project'],
        deprecated_rule=deprecated_purge_zones
    )
]


def list_rules():
    return rules
