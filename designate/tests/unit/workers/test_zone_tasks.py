# Copyright 2016 Rackspace Inc.
#
# Author: Eric Larson <eric.larson@rackspace.com>
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
# under the License.mport threading
from unittest import mock

import dns.exception
import oslotest.base
from oslo_config import cfg
from oslo_config import fixture as cfg_fixture

from designate import exceptions
from designate import objects
from designate.tests.unit import utils
from designate.worker import processing
from designate.worker import utils as wutils
from designate.worker.tasks import zone

CONF = cfg.CONF

QUERY_RESULTS = {
    'delete_success_all': {
        'case': {
            'action': 'DELETE',
            'results': [0, 0, 0, 0],
            'zone_serial': 1,
            'positives': 4,
            'no_zones': 4,
            'consensus_serial': 0
        }
    },
    'delete_success_half': {
        'case': {
            'action': 'DELETE',
            'results': [1, 0, 1, 0],
            'zone_serial': 1,
            'positives': 2,
            'no_zones': 2,
            'consensus_serial': 0
        },
    },
    'update_success_all': {
        'case': {
            'action': 'UPDATE',
            'results': [2, 2, 2, 2],
            'zone_serial': 2,
            'positives': 4,
            'no_zones': 0,
            'consensus_serial': 2
        },
    },
    'update_fail_all': {
        'case': {
            'action': 'UPDATE',
            'results': [1, 1, 1, 1],
            'zone_serial': 2,
            'positives': 0,
            'no_zones': 0,
            # The consensus serial is never updated b/c the nameserver
            # serials are less than the zone serial.
            'consensus_serial': 0
        },
    },
    'update_success_with_higher_serial': {
        'case': {
            'action': 'UPDATE',
            'results': [2, 1, 0, 3],
            'zone_serial': 2,
            'positives': 2,
            'no_zones': 1,
            'consensus_serial': 2
        },
    },
    'update_success_all_higher_serial': {
        'case': {
            'action': 'UPDATE',
            'results': [3, 3, 3, 3],
            'zone_serial': 2,
            'positives': 4,
            'no_zones': 0,
            'consensus_serial': 3,
        }
    },
}


class TestZoneAction(oslotest.base.BaseTestCase):
    def setUp(self):
        super(TestZoneAction, self).setUp()
        self.context = mock.Mock()
        self.pool = 'default_pool'
        self.executor = mock.Mock()
        self.task = zone.ZoneAction(
            self.executor, self.context, self.pool, mock.Mock(), 'CREATE'
        )
        self.task._wait_for_nameservers = mock.Mock()

    def test_constructor(self):
        self.assertTrue(self.task)

    def test_call(self):
        self.task._zone_action_on_targets = mock.Mock(return_value=True)
        self.task._poll_for_zone = mock.Mock(return_value=True)
        result = self.task()
        self.assertTrue(result)

        self.assertTrue(self.task._wait_for_nameservers.called)
        self.assertTrue(self.task._zone_action_on_targets.called)
        self.assertTrue(self.task._poll_for_zone.called)

    def test_call_on_delete(self):
        mock_zone = mock.Mock()
        task = zone.ZoneAction(
            self.executor, self.context, self.pool, mock_zone, 'DELETE'
        )
        task._zone_action_on_targets = mock.Mock(return_value=True)
        task._poll_for_zone = mock.Mock(return_value=True)
        task._wait_for_nameservers = mock.Mock()

        self.assertTrue(task())

        self.assertEqual(0, mock_zone.serial)

    def test_call_fails_on_zone_targets(self):
        self.task._zone_action_on_targets = mock.Mock(return_value=False)
        self.assertFalse(self.task())

    def test_call_fails_on_poll_for_zone(self):
        self.task._zone_action_on_targets = mock.Mock(return_value=False)
        self.assertFalse(self.task())

    @mock.patch.object(zone, 'time')
    def test_wait_for_nameservers(self, mock_time):
        # It is just a time.sleep :(
        task = zone.ZoneAction(
            self.executor, self.context, self.pool, mock.Mock(), 'CREATE'
        )
        task._wait_for_nameservers()
        mock_time.sleep.assert_called_with(task.delay)


class TestZoneActionOnTarget(oslotest.base.BaseTestCase):
    def setUp(self):
        super(TestZoneActionOnTarget, self).setUp()
        self.backend = mock.Mock()
        self.target = objects.PoolTarget.from_dict({
            'id': '4588652b-50e7-46b9-b688-a9bad40a873e',
            'type': 'fake',
            'options': [
                {'key': 'host', 'value': '127.0.0.1'},
                {'key': 'port', 'value': 53},
            ],
            'backend': self.backend,
        })

        self.context = mock.Mock()
        self.executor = mock.Mock()
        self.zone_params = mock.Mock()

    @mock.patch.object(wutils, 'notify')
    def test_call_create(self, mock_notify):
        self.zone = objects.Zone(name='example.org.', action='CREATE')
        self.actor = zone.ZoneActionOnTarget(
            self.executor,
            self.context,
            self.zone,
            self.target,
            self.zone_params
        )

        self.assertTrue(self.actor())

        mock_notify.assert_called_once_with(
            self.zone.name,
            '127.0.0.1',
            port=53
        )

    @mock.patch.object(wutils, 'notify')
    def test_call_update(self, mock_notify):
        self.zone = objects.Zone(name='example.org.', action='UPDATE')
        self.actor = zone.ZoneActionOnTarget(
            self.executor,
            self.context,
            self.zone,
            self.target,
            self.zone_params,
        )

        self.assertTrue(self.actor())

        mock_notify.assert_called_once_with(
            self.zone.name,
            '127.0.0.1',
            port=53
        )

    @mock.patch.object(wutils, 'notify')
    def test_call_delete(self, mock_notify):
        self.zone = objects.Zone(name='example.org.', action='DELETE')
        self.actor = zone.ZoneActionOnTarget(
            self.executor,
            self.context,
            self.zone,
            self.target,
            self.zone_params
        )

        self.assertTrue(self.actor())

        mock_notify.assert_not_called()

    @mock.patch.object(wutils, 'notify')
    @mock.patch('time.sleep', mock.Mock())
    def test_call_exception_raised(self, mock_notify):
        self.backend.create_zone.side_effect = exceptions.BadRequest()
        self.zone = objects.Zone(name='example.org.', action='CREATE')
        self.actor = zone.ZoneActionOnTarget(
            self.executor,
            self.context,
            self.zone,
            self.target,
            self.zone_params
        )

        self.assertFalse(self.actor())

        mock_notify.assert_not_called()


class TestSendNotify(oslotest.base.BaseTestCase):
    def setUp(self):
        super(TestSendNotify, self).setUp()
        self.useFixture(cfg_fixture.Config(CONF))
        self.backend = mock.Mock()
        self.target = objects.PoolTarget.from_dict({
            'id': '4588652b-50e7-46b9-b688-a9bad40a873e',
            'type': 'fake',
            'options': [
                {'key': 'host', 'value': '127.0.0.1'},
                {'key': 'port', 'value': 53},
            ],
        })

        self.executor = mock.Mock()

    @mock.patch.object(wutils, 'notify')
    def test_call_notify(self, mock_notify):
        self.zone = objects.Zone(name='example.org.')
        self.actor = zone.SendNotify(
            self.executor,
            self.zone,
            self.target,
        )

        self.assertTrue(self.actor())

        mock_notify.assert_called_once_with(
            self.zone.name,
            '127.0.0.1',
            port=53
        )

    @mock.patch.object(wutils, 'notify')
    def test_call_notify_timeout(self, mock_notify):
        mock_notify.side_effect = dns.exception.Timeout()
        self.zone = objects.Zone(name='example.org.')
        self.actor = zone.SendNotify(
            self.executor,
            self.zone,
            self.target,
        )

        self.assertRaises(
            dns.exception.Timeout,
            self.actor
        )

    @mock.patch.object(wutils, 'notify')
    def test_call_dont_notify(self, mock_notify):
        CONF.set_override('notify', False, 'service:worker')

        self.zone = objects.Zone(name='example.org.')
        self.actor = zone.SendNotify(
            self.executor,
            self.zone,
            self.target,
        )

        self.assertTrue(self.actor())

        mock_notify.assert_not_called()


class TestZoneActor(oslotest.base.BaseTestCase):
    def setUp(self):
        super(TestZoneActor, self).setUp()
        self.context = mock.Mock()
        self.pool = mock.Mock()
        self.executor = mock.Mock()
        self.zone_params = mock.Mock()
        self.actor = zone.ZoneActor(
            self.executor,
            self.context,
            self.pool,
            mock.Mock(action='CREATE'),
            self.zone_params
        )

    def test_invalid_action(self):
        self.assertRaisesRegexp(
            exceptions.BadAction, 'Unexpected action: BAD',
            self.actor._validate_action, 'BAD'
        )

    def test_threshold_from_config(self):
        actor = zone.ZoneActor(
            self.executor, self.context, self.pool, mock.Mock(action='CREATE')
        )

        self.assertEqual(
            cfg.CONF['service:worker'].threshold_percentage,
            actor.threshold
        )

    def test_execute(self):
        self.pool.targets = ['target 1']
        self.actor.executor.run.return_value = ['foo']

        results = self.actor._execute()

        self.assertEqual(['foo'], results)

    def test_call(self):
        self.actor.pool.targets = ['target 1']
        self.actor.executor.run.return_value = [True]
        self.assertTrue(self.actor())

    def test_threshold_met_true(self):
        self.actor._threshold = 80

        results = [True] * 8 + [False] * 2

        self.assertTrue(self.actor._threshold_met(results))

    def test_threshold_met_false(self):
        self.actor._threshold = 90
        self.actor._update_status = mock.Mock()

        results = [False] + [True] * 8 + [False]

        self.assertFalse(self.actor._threshold_met(results))
        self.assertTrue(self.actor._update_status.called)
        self.assertEqual('ERROR', self.actor.zone.status)


@utils.parameterized_class
class TestParseQueryResults(oslotest.base.BaseTestCase):
    @utils.parameterized(QUERY_RESULTS)
    def test_result_cases(self, case):
        mock_zone = mock.Mock(action=case['action'])
        if case.get('zone_serial'):
            mock_zone.serial = case['zone_serial']

        result = zone.parse_query_results(
            case['results'], mock_zone
        )

        self.assertEqual(case['positives'], result.positives)
        self.assertEqual(case['no_zones'], result.no_zones)
        self.assertEqual(case['consensus_serial'], result.consensus_serial)


class TestZonePoller(oslotest.base.BaseTestCase):
    def setUp(self):
        super(TestZonePoller, self).setUp()
        self.context = mock.Mock()
        self.pool = mock.Mock()
        self.zone = mock.Mock(name='example.com.', serial=1)
        self.threshold = 80
        self.executor = mock.Mock()
        self.poller = zone.ZonePoller(
            self.executor,
            self.context,
            self.pool,
            self.zone,
        )
        self.poller._threshold = self.threshold

    def test_constructor(self):
        self.assertTrue(self.poller)
        self.assertEqual(self.threshold, self.poller.threshold)

    def test_call_on_success(self):
        ns_results = [2] * 8 + [0] * 2
        result = zone.DNSQueryResult(
            positives=8,
            no_zones=2,
            consensus_serial=2,
            results=ns_results,
        )
        self.poller.zone.action = 'UPDATE'
        self.poller.zone.serial = 2
        self.poller._do_poll = mock.Mock(return_value=result)
        self.poller._on_success = mock.Mock(return_value=True)
        self.poller._update_status = mock.Mock()

        self.assertTrue(self.poller())

        self.poller._on_success.assert_called_with(result, 'SUCCESS')
        self.poller._update_status.called
        self.poller.zone.serial = 2
        self.poller.zone.status = 'SUCCESS'

    def test_threshold_met_true(self):
        ns_results = [2] * 8 + [0] * 2
        result = zone.DNSQueryResult(
            positives=8,
            no_zones=2,
            consensus_serial=2,
            results=ns_results,
        )

        success, status = self.poller._threshold_met(result)

        self.assertTrue(success)
        self.assertEqual('SUCCESS', status)

    def test_threshold_met_false_low_positives(self):
        # 6 positives, 4 behind the serial (aka 0 no_zones)
        ns_results = [2] * 6 + [1] * 4
        result = zone.DNSQueryResult(
            positives=6,
            no_zones=0,
            consensus_serial=2,
            results=ns_results,
        )

        success, status = self.poller._threshold_met(result)

        self.assertFalse(success)
        self.assertEqual('ERROR', status)

    def test_threshold_met_true_no_zones(self):
        # Change is looking for serial 2
        # 4 positives, 4 no zones, 2 behind the serial
        ns_results = [2] * 4 + [0] * 4 + [1] * 2
        result = zone.DNSQueryResult(
            positives=4,
            no_zones=4,
            consensus_serial=1,
            results=ns_results,
        )

        # Set the threshold to 30%
        self.poller._threshold = 30
        self.poller.zone.action = 'UPDATE'

        success, status = self.poller._threshold_met(result)

        self.assertTrue(success)
        self.assertEqual('SUCCESS', status)

    def test_threshold_met_false_no_zones(self):
        # Change is looking for serial 2
        # 4 positives, 4 no zones
        ns_results = [2] * 4 + [0] * 4
        result = zone.DNSQueryResult(
            positives=4,
            no_zones=4,
            consensus_serial=2,
            results=ns_results,
        )

        # Set the threshold to 100%
        self.poller._threshold = 100
        self.poller.zone.action = 'UPDATE'

        success, status = self.poller._threshold_met(result)

        self.assertFalse(success)
        self.assertEqual('NO_ZONE', status)

    def test_threshold_met_false_no_zones_one_result(self):
        # Change is looking for serial 2
        # 4 positives, 4 no zones
        ns_results = [0]
        result = zone.DNSQueryResult(
            positives=0,
            no_zones=1,
            consensus_serial=2,
            results=ns_results,
        )

        # Set the threshold to 100%
        self.poller._threshold = 100
        self.poller.zone.action = 'UPDATE'

        success, status = self.poller._threshold_met(result)

        self.assertFalse(success)
        self.assertEqual('NO_ZONE', status)

    def test_on_success(self):
        query_result = mock.Mock(consensus_serial=10)

        result = self.poller._on_success(query_result, 'FOO')

        self.assertTrue(result)
        self.assertEqual(10, self.zone.serial)
        self.assertEqual('FOO', self.zone.status)

    def test_on_error_failure(self):
        result = self.poller._on_failure('FOO')

        self.assertFalse(result)
        self.assertEqual('FOO', self.zone.status)

    def test_on_no_zones_failure(self):
        result = self.poller._on_failure('NO_ZONE')

        self.assertFalse(result)
        self.assertEqual('NO_ZONE', self.zone.status)
        self.assertEqual('CREATE', self.zone.action)


class TestZonePollerPolling(oslotest.base.BaseTestCase):
    def setUp(self):
        super(TestZonePollerPolling, self).setUp()
        self.executor = processing.Executor()
        self.context = mock.Mock()
        self.zone = mock.Mock(name='example.com.', action='UPDATE', serial=10)
        self.pool = mock.Mock(nameservers=['ns1', 'ns2'])
        self.threshold = 80

        self.poller = zone.ZonePoller(
            self.executor,
            self.context,
            self.pool,
            self.zone,
        )

        self.max_retries = 4
        self.retry_interval = 2
        self.poller._max_retries = self.max_retries
        self.poller._retry_interval = self.retry_interval

    @mock.patch.object(zone, 'PollForZone')
    def test_do_poll(self, mock_poll_for_zone):
        mock_poll_for_zone.return_value = mock.Mock(return_value=10)
        result = self.poller._do_poll()

        self.assertTrue(result)

        self.assertEqual(2, result.positives)
        self.assertEqual(0, result.no_zones)
        self.assertEqual([10, 10], result.results)

    @mock.patch.object(zone, 'time', mock.Mock())
    def test_do_poll_with_retry(self):
        exe = mock.Mock()
        exe.run.side_effect = [
            [0, 0], [10, 10]
        ]
        self.poller.executor = exe

        result = self.poller._do_poll()

        self.assertTrue(result)

        zone.time.sleep.assert_called_with(self.retry_interval)

        # retried once
        self.assertEqual(1, len(zone.time.sleep.mock_calls))

    @mock.patch.object(zone, 'time', mock.Mock())
    def test_do_poll_with_retry_until_fail(self):
        exe = mock.Mock()
        exe.run.return_value = [0, 0]

        self.poller.executor = exe

        self.poller._do_poll()

        self.assertEqual(self.max_retries, len(zone.time.sleep.mock_calls))


class TestUpdateStatus(oslotest.base.BaseTestCase):
    def setUp(self):
        super(TestUpdateStatus, self).setUp()
        self.executor = processing.Executor()
        self.task = zone.UpdateStatus(self.executor, mock.Mock(), mock.Mock())
        self.task._central_api = mock.Mock()

    def test_call_on_delete(self):
        self.task.zone.action = 'DELETE'

        self.task()

        self.assertEqual('NONE', self.task.zone.action)
        self.assertEqual('NO_ZONE', self.task.zone.status)
        self.assertTrue(self.task.central_api.update_status.called)

    def test_call_on_success(self):
        self.task.zone.status = 'SUCCESS'

        self.task()

        self.assertEqual('NONE', self.task.zone.action)
        self.assertTrue(self.task.central_api.update_status.called)

    def test_call_central_call(self):
        self.task.zone.status = 'SUCCESS'

        self.task()

        self.task.central_api.update_status.assert_called_with(
            self.task.context,
            self.task.zone.id,
            self.task.zone.status,
            self.task.zone.serial,
        )

    def test_call_on_delete_error(self):
        self.task.zone.action = 'DELETE'
        self.task.zone.status = 'ERROR'

        self.task()

        self.assertEqual('DELETE', self.task.zone.action)
        self.assertEqual('ERROR', self.task.zone.status)
        self.assertTrue(self.task.central_api.update_status.called)

    def test_call_on_create_error(self):
        self.task.zone.action = 'CREATE'
        self.task.zone.status = 'ERROR'

        self.task()

        self.assertEqual('CREATE', self.task.zone.action)
        self.assertEqual('ERROR', self.task.zone.status)
        self.assertTrue(self.task.central_api.update_status.called)

    def test_call_on_update_error(self):
        self.task.zone.action = 'UPDATE'
        self.task.zone.status = 'ERROR'

        self.task()

        self.assertEqual('UPDATE', self.task.zone.action)
        self.assertEqual('ERROR', self.task.zone.status)
        self.assertTrue(self.task.central_api.update_status.called)


class TestPollForZone(oslotest.base.BaseTestCase):
    def setUp(self):
        super(TestPollForZone, self).setUp()
        self.zone = mock.Mock(serial=1)
        self.zone.name = 'example.org.'
        self.executor = processing.Executor()

        self.ns = mock.Mock(host='ns.example.org', port=53)
        self.task = zone.PollForZone(self.executor, self.zone, self.ns)
        self.task._max_retries = 3
        self.task._retry_interval = 2

    @mock.patch.object(zone.wutils, 'get_serial', mock.Mock(return_value=10))
    def test_get_serial(self):
        self.assertEqual(10, self.task._get_serial())

        zone.wutils.get_serial.assert_called_with(
            'example.org.',
            'ns.example.org',
            port=53
        )

    def test_call(self):
        self.task._get_serial = mock.Mock(return_value=10)

        result = self.task()

        self.assertEqual(10, result)

    def test_call_timeout(self):
        self.task._get_serial = mock.Mock(side_effect=dns.exception.Timeout)

        result = self.task()

        self.assertIsNone(result)

    def test_call_exception_raised(self):
        self.task._get_serial = mock.Mock(side_effect=IOError)

        result = self.task()

        self.assertIsNone(result)


class TestExportZone(oslotest.base.BaseTestCase):
    def setUp(self):
        super(TestExportZone, self).setUp()
        self.zone = mock.Mock(name='example.com.', serial=1)
        self.export = mock.Mock()
        self.export.id = '1'
        self.executor = processing.Executor()
        self.context = mock.Mock()

        self.task = zone.ExportZone(
            self.executor, self.context, self.zone, self.export
        )
        self.task._central_api = mock.Mock()
        self.task._storage = mock.Mock()
        self.task._quota = mock.Mock()

        self.task._quota.limit_check = mock.Mock()
        self.task._storage.count_recordsets = mock.Mock(return_value=1)
        self.task._synchronous_export = mock.Mock(return_value=True)

    def test_sync_export_right_size(self):
        self.task()
        self.assertEqual('COMPLETE', self.export.status)
        self.assertEqual(
            'designate://v2/zones/tasks/exports/%s/export' % self.export.id,
            self.export.location
        )

    def test_sync_export_wrong_size_fails(self):
        self.task._quota.limit_check = mock.Mock(
            side_effect=exceptions.OverQuota)

        self.task()
        self.assertEqual('ERROR', self.export.status)

    def test_async_export_fails(self):
        self.task._synchronous_export = mock.Mock(return_value=False)

        self.task()
        self.assertEqual('ERROR', self.export.status)
