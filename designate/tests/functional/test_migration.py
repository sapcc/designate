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
# Based on Nova's test_migrations.py


import os

from unittest import mock

from alembic import command as alembic_api
from alembic import config as alembic_config
from alembic import script as alembic_script
from oslo_db.sqlalchemy import enginefacade
from oslo_db.sqlalchemy import test_fixtures
from oslo_log import log as logging
import sqlalchemy as sa

from designate.storage import sqlalchemy as designate_sqlalchemy
from designate.storage.sqlalchemy.alembic import legacy_utils
import designate.tests.functional


LOG = logging.getLogger(__name__)
ALEMBIC_PATH = os.path.join(
    os.path.dirname(designate_sqlalchemy.__file__), 'alembic.ini'
)


class DesignateMigrationsWalk(
    test_fixtures.OpportunisticDBTestMixin,
    designate.tests.functional.TestCase,
):
    # Migrations can take a long time, particularly on underpowered CI nodes.
    # Give them some breathing room.
    TIMEOUT_SCALING_FACTOR = 4

    def setUp(self):
        super().setUp()
        self.engine = enginefacade.writer.get_engine()
        self.config = alembic_config.Config(ALEMBIC_PATH)
        self.init_version = 'c9f427f7180a'

    def _migrate_up(self, connection, revision):
        if revision == self.init_version:  # no tests for the initial revision
            alembic_api.upgrade(self.config, revision)
            return

        self.assertIsNotNone(
            getattr(self, '_check_%s' % revision, None),
            (
                'DB Migration %s does not have a test; you must add one'
            ) % revision,
        )

        pre_upgrade = getattr(self, '_pre_upgrade_%s' % revision, None)
        if pre_upgrade:
            pre_upgrade(connection)

        alembic_api.upgrade(self.config, revision)

        post_upgrade = getattr(self, '_check_%s' % revision, None)
        if post_upgrade:
            post_upgrade(connection)

    def _check_867a331ce1fc(self, connection):
        pass

    def _check_d9a1883e93e9(self, connection):
        pass

    def _check_bfcfc4a07487(self, connection):
        pass

    def _check_f9f969f9d85e(self, connection):
        pass

    def _check_a69b45715cc1(self, connection):
        pass

    def _check_0bcf910ea823(self, connection):
        pass

    def _check_d04819112169(self, connection):
        pass

    def _check_304d41c3847a(self, connection):
        pass

    def _check_15b34ff3ecb8(self, connection):
        pass

    def _check_7977deaa5167(self, connection):
        pass

    def _check_93a00a815f07(self, connection):
        pass

    def _check_b8999fd10721(self, connection):
        pass

    def _check_91eb1eb7c882(self, connection):
        pass

    def _check_e5e2199ed76e(self, connection):
        pass

    def _check_b20189fd288e(self, connection):
        pass

    def _check_a005af3aa38e(self, connection):
        pass

    def _check_9099de8ae11c(self, connection):
        pass

    def _check_f828412479ee(self, connection):
        pass

    def _check_b57384b28335(self, connection):
        pass

    def _check_d2a4aea32428(self, connection):
        pass

    def _check_f49c4409c8ba(self, connection):
        pass 
        
    def _check_018194635d9e(self, connection):
        # Fresh-install path: b20189fd288e already created the table with
        # project_id/target_project_id. The migration must be a no-op and
        # the upstream column names must still be present.
        inspector = sa.inspect(connection)
        cols = [c['name'] for c in inspector.get_columns('shared_zones')]
        self.assertIn('project_id', cols)
        self.assertIn('target_project_id', cols)
        self.assertNotIn('tenant_id', cols)
        self.assertNotIn('target_tenant_id', cols)

    def test_shared_zones_dalmatian_merge_legacy_path(self):
        # Legacy path: simulate a CCloud instance where shared_zones was
        # created with legacy tenant_id/target_tenant_id column names
        # (i.e. before the upstream Dalmatian shared_zones migration).
        # The migration must rename them to project_id/target_project_id.
        with self.engine.begin() as connection:
            self.config.attributes['connection'] = connection

            # Migrate up to just before the shared_zones migration so we
            # have a base schema, then manually create the legacy table.
            alembic_api.upgrade(self.config, 'e5e2199ed76e')

            op = sa.text(
                'CREATE TABLE shared_zones_legacy_test ('
                '  id VARCHAR(36) NOT NULL PRIMARY KEY,'
                '  created_at DATETIME,'
                '  updated_at DATETIME,'
                '  zone_id VARCHAR(36) NOT NULL,'
                '  tenant_id VARCHAR(36) NOT NULL,'
                '  target_tenant_id VARCHAR(36) NOT NULL'
                ')'
            )
            connection.execute(op)

            # Rename the test table to shared_zones to simulate legacy state.
            # b20189fd288e is guarded by legacy_utils; we skip it and stamp
            # alembic as if it already ran, then run 018194635d9e directly.
            connection.execute(sa.text('DROP TABLE IF EXISTS shared_zones'))
            connection.execute(sa.text(
                'ALTER TABLE shared_zones_legacy_test '
                'RENAME TO shared_zones'
            ))

            # Stamp past b20189fd288e and the chain up to f49c4409c8ba so
            # Alembic thinks those ran, then apply only 018194635d9e.
            alembic_api.stamp(self.config, 'f49c4409c8ba')

            alembic_api.upgrade(self.config, '018194635d9e')

            inspector = sa.inspect(connection)
            cols = [c['name'] for c in
                    inspector.get_columns('shared_zones')]
            self.assertIn('project_id', cols)
            self.assertIn('target_project_id', cols)
            self.assertNotIn('tenant_id', cols)
            self.assertNotIn('target_tenant_id', cols)

    def test_single_base_revision(self):
        script = alembic_script.ScriptDirectory.from_config(self.config)
        self.assertEqual(1, len(script.get_bases()))

    def test_walk_versions(self):
        with self.engine.begin() as connection:
            self.config.attributes['connection'] = connection
            script = alembic_script.ScriptDirectory.from_config(self.config)
            revisions = [x.revision for x in script.walk_revisions()]

            # for some reason, 'walk_revisions' gives us the revisions in
            # reverse chronological order, so we have to invert this
            revisions.reverse()
            self.assertEqual(revisions[0], self.init_version)

            for revision in revisions:
                LOG.info('Testing revision %s', revision)
                self._migrate_up(connection, revision)

    def test_is_migration_needed(self):
        with self.engine.begin() as connection:
            self.config.attributes['connection'] = connection
            script = alembic_script.ScriptDirectory.from_config(self.config)
            revisions = [x.revision for x in script.walk_revisions()]

            # for some reason, 'walk_revisions' gives us the revisions in
            # reverse chronological order, so we have to invert this
            revisions.reverse()
            self.assertEqual(revisions[0], self.init_version)

            for revision in revisions:
                LOG.info('Testing revision %s', revision)

                # Let's stop after the first revision
                # without is_migration_needed.
                if revision == 'b20189fd288e':
                    break
                self._migrate_up(connection, revision)

            # Reset alembic.
            alembic_api.stamp(self.config, None)

            # We should only need the last few revisions.
            with mock.patch.object(legacy_utils,
                                   'is_migration_needed',
                                   return_value=False):
                for revision in revisions:
                    # CCloud only, Dalmatian upgrade:
                    if revision == '018194635d9e':
                        # skip because it is temporary
                        continue
                    LOG.info('Testing revision %s', revision)
                    self._migrate_up(connection, revision)


class TestMigrationsWalkSQLite(
    DesignateMigrationsWalk,
    test_fixtures.OpportunisticDBTestMixin,
):
    pass
