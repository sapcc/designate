# Copyright 2012 Managed I.T.
#
# Author: Kiall Mac Innes <kiall@managedit.ie>
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
from unittest import mock

import testtools

import designate.tests
from designate import context
from designate import exceptions
from designate import policy


class TestDesignateContext(designate.tests.TestCase):
    def test_deepcopy(self):
        orig = context.DesignateContext(
            user_id='12345', project_id='54321'
        )
        copy = orig.deepcopy()

        self.assertEqual(orig.to_dict(), copy.to_dict())

    def test_tsigkey_id_override(self):
        orig = context.DesignateContext(
            tsigkey_id='12345', project_id='54321'
        )
        copy = orig.to_dict()

        self.assertEqual('TSIG:12345 54321 - - -', copy['user_identity'])

    def test_elevated(self):
        ctxt = context.DesignateContext(
            user_id='12345', project_id='54321'
        )
        admin_ctxt = ctxt.elevated()

        self.assertFalse(ctxt.is_admin)
        self.assertTrue(admin_ctxt.is_admin)
        self.assertEqual(0, len(ctxt.roles))

    def test_elevated_with_show_deleted(self):
        ctxt = context.DesignateContext(
            user_id='12345', project_id='54321'
        )
        admin_ctxt = ctxt.elevated(show_deleted=True)

        self.assertTrue(admin_ctxt.show_deleted)

    def test_all_tenants(self):
        ctxt = context.DesignateContext(
            user_id='12345', project_id='54321'
        )
        admin_ctxt = ctxt.elevated()
        admin_ctxt.all_tenants = True

        self.assertFalse(ctxt.is_admin)
        self.assertTrue(admin_ctxt.is_admin)
        self.assertTrue(admin_ctxt.all_tenants)

    def test_all_tenants_policy_failure(self):
        ctxt = context.DesignateContext(
            user_id='12345', project_id='54321'
        )

        with testtools.ExpectedException(exceptions.Forbidden):
            ctxt.all_tenants = True

    def test_edit_managed_records(self):
        ctxt = context.DesignateContext(
            user_id='12345', project_id='54321'
        )
        admin_ctxt = ctxt.elevated()

        admin_ctxt.edit_managed_records = True

        self.assertFalse(ctxt.is_admin)
        self.assertTrue(admin_ctxt.is_admin)
        self.assertTrue(admin_ctxt.edit_managed_records)

    def test_edit_managed_records_failure(self):
        ctxt = context.DesignateContext(
            user_id='12345', project_id='54321'
        )
        with testtools.ExpectedException(exceptions.Forbidden):
            ctxt.edit_managed_records = True

    def test_hard_delete(self):
        ctxt = context.DesignateContext(
            user_id='12345', project_id='54321'
        )
        admin_ctxt = ctxt.elevated()

        admin_ctxt.hard_delete = True

        self.assertFalse(ctxt.is_admin)
        self.assertTrue(admin_ctxt.is_admin)
        self.assertTrue(admin_ctxt.hard_delete)

    def test_hard_delete_failure(self):
        ctxt = context.DesignateContext(
            user_id='12345', project_id='54321'
        )
        with testtools.ExpectedException(exceptions.Forbidden):
            ctxt.hard_delete = True

    @mock.patch.object(policy, 'check')
    def test_sudo(self, mock_policy_check):
        ctxt = context.DesignateContext(
            user_id='12345', project_id='old_tenant'
        )
        ctxt.sudo('new_tenant')

        self.assertTrue(mock_policy_check.called)
        self.assertEqual('new_tenant', ctxt.tenant)
        self.assertEqual('old_tenant', ctxt.original_tenant)
