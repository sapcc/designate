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
"""WSGI script for Designate API."""

import os

from oslo_config import cfg
from oslo_log import log as logging
from paste import deploy

from designate import conf
from designate import service
from designate import policy
from designate import rpc
from designate.common import config


CONF = conf.CONF

CONFIG_FILES = ['api-paste.ini', 'designate.conf', 'hostname.conf']


def _get_config_files(env=None):
    if env is None:
        env = os.environ
    dirname = env.get('OS_DESIGNATE_CONFIG_DIR', '/etc/designate').strip()
    return [os.path.join(dirname, config_file) for config_file in CONFIG_FILES]


def init_application():
    conf_files = _get_config_files()
    logging.register_options(cfg.CONF)
    cfg.CONF([], project='designate', default_config_files=conf_files)
    config.set_defaults()
    logging.setup(cfg.CONF, 'designate')

    policy.init()

    if not rpc.initialized():
        rpc.init(CONF)

    heartbeat = service.Heartbeat('api')
    heartbeat.start()

    conf = conf_files[0]

    return deploy.loadapp('config:%s' % conf, name='osapi_dns')
