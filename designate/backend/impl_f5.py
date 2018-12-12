# Copyright 2018 SAP SE.
#
# Author: Dmitry Galkin <galkindmitrii@gmail.com>
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

"""
F5 backend. Create and delete zones on F5 Load Balancer via iControl API
"""
from random import shuffle
import requests
from requests.auth import HTTPBasicAuth
from requests.exceptions import HTTPError, ConnectionError
from oslo_log import log as logging

from designate.backend import base
from designate.utils import DEFAULT_MDNS_PORT

LOG = logging.getLogger(__name__)
DEFAULT_MASTER_PORT = DEFAULT_MDNS_PORT


class F5Backend(base.Backend):
    __plugin_name__ = 'f5'

    __backend_status__ = 'integrated'

    def __init__(self, target):
        super(F5Backend, self).__init__(target)

        self._host = self.options.get('host', '127.0.0.1')
        self._port = int(self.options.get('port', 53))
        self._auth = HTTPBasicAuth(self.options.get('icontrol_user', 'admin'),
                                   self.options.get('icontrol_pass', 'admin'))

    def _generate_icontrol_base_request(self, method, http_url, data):
        """
        Generate a request to use iControl API
        """
        f5_host = self.options.get('icontrol_host', '127.0.0.1')
        f5_port = int(self.options.get('icontrol_port', 443))

        base_url = "https://%s:%s/" % (f5_host, f5_port)
        url = base_url + http_url

        headers = {'Content-Type': 'application/json',
                   'Accept': 'application/json'}

        f5_request = requests.Request(method, url,
                                      data=data, auth=self._auth,
                                      headers=headers)
        return f5_request.prepare()

    def create_zone(self, context, zone):
        """
        Create a new Zone by executing iControl API, then notify mDNS
        Do not raise exceptions if the zone already exists.
        """
        LOG.debug('Creating Zone %s' % zone)
        masters = []
        for master in self.masters:
            host = master['host']
            port = master['port']
            masters.append('%s:%s' % (host, port))

        # Ensure different MiniDNS instances are targeted for AXFRs
        shuffle(masters)

        # F5 does not accept . in the end
        if zone.endswith("."):
            zone = zone[:-1]

        method = 'POST'
        url = 'mgmt/tm/ltm/dns/zone/'
        data = {'name': zone,
                'dnsExpressServer': 'designate-mdns',
                'dnsExpressNotifyTsigVerify': 'yes'}

        try:
            self._execute_call(method=method, url=url, data=data)
        except (ConnectionError, HTTPError) as exc:
            LOG.debug('An Error occured while creating a zone: %s', exc)

        self.mdns_api.notify_zone_changed(
            context, zone, self._host, self._port, self.timeout,
            self.retry_interval, self.max_retries, self.delay)

    def delete_zone(self, context, zone):
        """
        Delete a new Zone by calling iControl API
        Do not raise exceptions if the zone does not exist.
        """
        LOG.debug('Deleting Zone %s' % zone)

        # F5 does not accept . in the end
        if zone.endswith("."):
            zone = zone[:-1]

        method = 'DELETE'
        url = 'mgmt/tm/ltm/dns/zone/~Common~'.join(zone)
        data = {'name': zone}

        try:
            self._execute_call(method=method, url=url, data=data)
        except (ConnectionError, HTTPError) as exc:
            LOG.debug('An Error occured while deleting a zone: %s', exc)

    def _execute_call(self, **kwargs):
        """
        Execute iControl via HTTP

        :param icontrol_op: iControl arguments
        :type icontrol_op: list
        :returns: None
        """
        sess = requests.Session()
        f5_req = self._generate_icontrol_base_request(kwargs['method'],
                                                      kwargs['url'],
                                                      kwargs['data'])

        LOG.debug('Executing iControl request: %s', f5_req)
        resp = sess.send(f5_req, verify=False, timeout=20)
        LOG.debug('iControl response: %s', resp.text)
