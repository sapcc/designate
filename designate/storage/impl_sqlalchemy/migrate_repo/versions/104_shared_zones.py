# Copyright 2020 Cloudification GmbH. All rights reserved.
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

from sqlalchemy import String, DateTime
from sqlalchemy.schema import (Table, Column, MetaData, UniqueConstraint,
                               ForeignKeyConstraint)

from designate import utils
from designate.sqlalchemy.types import UUID

meta = MetaData()

shared_zones_table = Table(
    'shared_zones', meta,
    Column('id', UUID(), default=utils.generate_uuid, primary_key=True),
    Column('created_at', DateTime),
    Column('updated_at', DateTime),
    Column('zone_id', UUID(), nullable=False),
    Column('tenant_id', String(36), default=None, nullable=False),
    Column('target_tenant_id', String(36), default=None, nullable=False),

    UniqueConstraint('zone_id', 'tenant_id', 'target_tenant_id',
                     name='unique_shared_zone'),
    ForeignKeyConstraint(['zone_id'], ['zones.id'], ondelete='CASCADE'),

    mysql_engine='InnoDB',
    mysql_charset='utf8'
)


def upgrade(migrate_engine):
    meta.bind = migrate_engine

    Table('zones', meta, autoload=True)

    shared_zones_table.create(checkfirst=True)
