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


RULE_ADMIN_OR_OWNER = 'rule:admin_or_owner'
RULE_ADMIN_OR_OWNER_OR_ZONE_SHARED = 'rule:admin_or_owner_or_zone_shared'
RULE_ADMIN = 'rule:admin'
RULE_ZONE_PRIMARY_OR_ADMIN = \
    "('PRIMARY':%(zone_type)s and rule:admin_or_owner) "\
    "OR ('SECONDARY':%(zone_type)s AND is_admin:True)"
RULE_ZONE_TRANSFER = "rule:admin_or_owner OR tenant:%(target_tenant_id)s " \
                     "OR None:%(target_tenant_id)s"
RULE_ANY = "@"

# Generic policy check string for system administrators. These are the people
# who need the highest level of authorization to operate the deployment.
# They're allowed to create, read, update, or delete any system-specific
# resource. They can also operate on project-specific resources where
# applicable (e.g., cleaning up blacklists)
SYSTEM_ADMIN = 'role:admin and system_scope:all'

# Generic policy check string for read-only access to system-level resources.
# This persona is useful for someone who needs access for auditing or even
# support. These uses are also able to view project-specific resources where
# applicable (e.g., listing all pools)
SYSTEM_READER = 'role:reader and system_scope:all'

# This check string is reserved for actions that require the highest level of
# authorization on a project or resources within the project
PROJECT_ADMIN = 'role:admin and project_id:%(project_id)s'

# This check string is the primary use case for typical end-users, who are
# working with resources that belong to a project (e.g., creating DNS zones)
PROJECT_MEMBER = 'role:member and project_id:%(project_id)s'

# This check string should only be used to protect read-only project-specific
# resources. It should not be used to protect APIs that make writable changes.
PROJECT_READER = 'role:reader and project_id:%(project_id)s'

# The following are common composite check strings that are useful for
# protecting APIs designed to operate with multiple scopes
SYSTEM_ADMIN_OR_PROJECT_MEMBER = (
    '(' + SYSTEM_ADMIN + ') or (' + PROJECT_MEMBER + ')'
)
SYSTEM_OR_PROJECT_READER = (
    '(' + SYSTEM_READER + ') or (' + PROJECT_READER + ')'
)

rules = [
    policy.RuleDefault(
        name="admin",
        check_str="role:admin or is_admin:True"),
    policy.RuleDefault(
        name="primary_zone",
        check_str="target.zone_type:SECONDARY"),
    policy.RuleDefault(
        name="owner",
        check_str="tenant:%(tenant_id)s"),
    policy.RuleDefault(
        name="admin_or_owner",
        check_str="rule:admin or rule:owner"),
    policy.RuleDefault(
        name="default",
        check_str="rule:admin_or_owner"),
    policy.RuleDefault(
        name="target",
        check_str="tenant:%(target_tenant_id)s"),
    policy.RuleDefault(
        name="owner_or_target",
        check_str="rule:target or rule:owner"),
    policy.RuleDefault(
        name="owner_or_zone_shared",
        check_str="rule:owner or 'True':%(zone_shared)s"),
    policy.RuleDefault(
        name="admin_or_owner_or_target",
        check_str="rule:owner_or_target or rule:admin"),
    policy.RuleDefault(
        name="admin_or_owner_or_zone_shared",
        check_str="rule:owner_or_zone_shared or rule:admin"),
    policy.RuleDefault(
        name="admin_or_target",
        check_str="rule:admin or rule:target"),
    policy.RuleDefault(
        name="zone_primary_or_admin",
        check_str=RULE_ZONE_PRIMARY_OR_ADMIN)
]


def list_rules():
    return rules
