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

"""Add shared pool object

Revision ID: 591b07cc1eab
Revises: f49c4409c8ba
Create Date: 2025-10-05 06:48:43.625989

"""
from oslo_utils import uuidutils


from alembic import op
from designate.storage.sqlalchemy.types import UUID
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '591b07cc1eab'
down_revision = 'f49c4409c8ba'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Check if the equivalent legacy migration has already run
    # CCloud only, Shared Zones were used since years, therefore
    # we need to make old implementation compatible with Dalmatian release

    meta = sa.MetaData()

    op.create_table(
        'shared_pools', meta,
        sa.Column('id', UUID,
                  default=uuidutils.generate_uuid, primary_key=True),
        sa.Column('created_at', sa.DateTime),
        sa.Column('updated_at', sa.DateTime),
        sa.Column('pool_id', UUID, nullable=False),
        sa.Column('domain_id', sa.String(36), nullable=False),
        sa.Column('target_domain_id', sa.String(36), nullable=False),

        sa.UniqueConstraint('pool_id', 'domain_id', 'target_domain_id',
                            name='unique_shared_pool'),
        sa.ForeignKeyConstraint(['pool_id'], ['pools.id'], ondelete='CASCADE'),
        mysql_engine='InnoDB',
        mysql_charset='utf8',
    )

    op.add_column('pools',
                  sa.Column('domain_id', sa.String(36), nullable=True),)
    op.add_column(
        'pools',
        sa.Column('shared', sa.Boolean, default=False)
    )


def downgrade() -> None:
    # Revert the changes made in the upgrade function
    op.drop_column('pools', 'shared')
    op.drop_column('pools', 'domain_id')

    op.drop_table('shared_pools')
