# Copyright 2021 Cloudification GmbH
#
# Author: cloudification <contact@cloudification.io>
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

import oslotest.base
from oslo_log import log as logging

from designate import exceptions
from designate import objects

LOG = logging.getLogger(__name__)


class CERTRecordTest(oslotest.base.BaseTestCase):
    def test_parse_cert(self):
        cert_record = objects.CERT()
        cert_record._from_string(
            'DPKIX 1 RSASHA256 KR1L0GbocaIOOim1+qdHtOSrDcOsGiI2NCcxuX2/Tqc=')  # noqa

        self.assertEqual('DPKIX', cert_record.cert_type)
        self.assertEqual(1, cert_record.key_tag)
        self.assertEqual('RSASHA256', cert_record.cert_algo)
        self.assertEqual('KR1L0GbocaIOOim1+qdHtOSrDcOsGiI2NCcxuX2/Tqc=',
            cert_record.certificate)

    def test_parse_invalid_cert_type_value(self):
        cert_record = objects.CERT()
        self.assertRaisesRegex(
            exceptions.InvalidObject,
            'Cert type value should be between 0 and 65535',
            cert_record._from_string,
            '99999 1 RSASHA256 KR1L0GbocaIOOim1+qdHtOSrDcOsGiI2NCcxuX2/Tqc='
        )

    def test_parse_invalid_cert_type_mnemonic(self):
        cert_record = objects.CERT()
        self.assertRaisesRegex(
            exceptions.InvalidObject,
            'Cert type is not valid Mnemonic.',
            cert_record._from_string,
            'FAKETYPE 1 RSASHA256 KR1L0GbocaIOOim1+qdHtOSrDcOsGiI2NCcxuX2/Tqc='
        )

    def test_parse_invalid_cert_algo_value(self):
        cert_record = objects.CERT()
        self.assertRaisesRegex(
            exceptions.InvalidObject,
            'Cert algorithm value should be between 0 and 255',
            cert_record._from_string,
            'DPKIX 1 256 KR1L0GbocaIOOim1+qdHtOSrDcOsGiI2NCcxuX2/Tqc='
        )

    def test_parse_invalid_cert_algo_mnemonic(self):
        cert_record = objects.CERT()
        self.assertRaisesRegex(
            exceptions.InvalidObject,
            'Cert algorithm is not valid Mnemonic.',
            cert_record._from_string,
            'DPKIX 1 FAKESHA256 KR1L0GbocaIOOim1+qdHtOSrDcOsGiI2NCcxuX2/Tqc='
        )

    def test_parse_invalid_cert_certificate(self):
        cert_record = objects.CERT()
        self.assertRaisesRegex(
            exceptions.InvalidObject,
            'Cert certificate is not valid.',
            cert_record._from_string,
            'DPKIX 1 RSASHA256 KR1L0GbocaIOOim1+qdHtOSrDcOsGiI2NCcxuX2/Tqc'
        )
