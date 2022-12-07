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
from oslo_config import cfg
from oslo_log import log as logging
from paste import deploy

from designate import exceptions
from designate import heartbeat_emitter
from designate import service
from designate import utils

LOG = logging.getLogger(__name__)


class Service(service.WSGIService):
    def __init__(self):
        super(Service, self).__init__(
            self.wsgi_application,
            self.service_name,
            cfg.CONF['service:api'].listen,
        )
        self.heartbeat = heartbeat_emitter.get_heartbeat_emitter(
            self.service_name)

    def start(self):
        super(Service, self).start()
        self.heartbeat.start()

    def stop(self, graceful=True):
        self.heartbeat.stop()
        super(Service, self).stop(graceful)

    @property
    def service_name(self):
        return 'api'

    @property
    def wsgi_application(self):
        api_paste_config = cfg.CONF['service:api'].api_paste_config
        config_paths = utils.find_config(api_paste_config)

        if len(config_paths) == 0:
            msg = 'Unable to determine appropriate api-paste-config file'
            raise exceptions.ConfigurationError(msg)

        LOG.info('Using api-paste-config found at: %s', config_paths[0])

        return deploy.loadapp("config:%s" % config_paths[0], name='osapi_dns')
