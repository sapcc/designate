# Copyright (c) 2014 Rackspace Hosting
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
from oslo_config import cfg
from oslo_log import log as logging
import oslo_messaging as messaging

from designate.common import profiler
from designate.loggingutils import rpc_logging
from designate import rpc

CONF = cfg.CONF
LOG = logging.getLogger(__name__)

MDNS_API = None


def reset():
    global MDNS_API
    MDNS_API = None


@profiler.trace_cls("rpc")
@rpc_logging(LOG, 'mdns')
class MdnsAPI(object):

    """
    Client side of the mdns RPC API.

    Notify API version history:

        1.0 - Added notify_zone_changed and poll_for_serial_number.
        1.1 - Added get_serial_number.
        2.0 - Changed method signatures.
        2.1 - Removed unused functions.
        2.2 - Changed get_serial_number signature to make upgrade safer.

    XFR API version history:
        1.0 - Added perform_zone_xfr.
    """
    RPC_NOTIFY_API_VERSION = '2.2'
    RPC_XFR_API_VERSION = '1.0'

    def __init__(self, topic=None):
        self.topic = topic if topic else cfg.CONF['service:mdns'].topic

        notify_target = messaging.Target(topic=self.topic,
                                         namespace='notify',
                                         version=self.RPC_NOTIFY_API_VERSION)
        self.notify_client = rpc.get_client(notify_target, version_cap='2.2')

        xfr_target = messaging.Target(topic=self.topic,
                                      namespace='xfr',
                                      version=self.RPC_XFR_API_VERSION)
        self.xfr_client = rpc.get_client(xfr_target, version_cap='1.0')

    @classmethod
    def get_instance(cls):
        """
        The rpc.get_client() which is called upon the API object initialization
        will cause a assertion error if the designate.rpc.TRANSPORT isn't setup
        by rpc.init() before.

        This fixes that by creating the rpcapi when demanded.
        """
        global MDNS_API
        if not MDNS_API:
            MDNS_API = cls()
        return MDNS_API

    def get_serial_number(self, context, zone, host, port, timeout,
                          retry_interval, max_retries, delay):
        LOG.info(
            "get_serial_number: Calling mdns for zone '%(zone)s', serial "
            "%(serial)s' on nameserver '%(host)s:%(port)s'",
            {
                'zone': zone.name,
                'serial': zone.serial,
                'host': host,
                'port': port
            })
        cctxt = self.notify_client.prepare()
        return cctxt.call(
            context, 'get_serial_number', zone=zone,
            host=host, port=port, timeout=timeout,
            retry_interval=retry_interval, max_retries=max_retries,
            delay=delay
        )

    def perform_zone_xfr(self, context, zone):
        LOG.info("perform_zone_xfr: Calling mdns for zone %(zone)s",
                 {"zone": zone.name})
        return self.xfr_client.cast(context, 'perform_zone_xfr', zone=zone)
