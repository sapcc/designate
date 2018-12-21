# Copyright 2018 Canonical Ltd.
#
# Author: Tytus Kurek <tytus.kurek@canonical.com>
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

from sqlalchemy import MetaData, Table, Enum

meta = MetaData()


def upgrade(migrate_engine):
    meta.bind = migrate_engine

    RECORD_TYPES = ['A', 'AAAA', 'CNAME', 'MX', 'SRV', 'TXT', 'SPF', 'NS',
                    'PTR', 'SSHFP', 'SOA', 'CAA']

    records_table = Table('recordsets', meta, autoload=True)
    records_table.columns.type.alter(name='type', type=Enum(*RECORD_TYPES))


def downgrade(migrate_engine):
    meta.bind = migrate_engine

    RECORD_TYPES = ['A', 'AAAA', 'CNAME', 'MX', 'SRV', 'TXT', 'SPF', 'NS',
                    'PTR', 'SSHFP', 'SOA']

    records_table = Table('recordsets', meta, autoload=True)

    # Delete all CAA records
    records_table.filter_by(name='type', type='CAA').delete()

    # Remove CAA from the ENUM
    records_table.columns.type.alter(type=Enum(*RECORD_TYPES))
