from datetime import timedelta
import unittest
from unittest.mock import MagicMock

from rx import Observable
from rx.concurrency.historicalscheduler import HistoricalScheduler

from serial_protocol.rx import RxEventMinder, RxSerialProtocol, RxTimeoutError

from .example_machine import ASCIIKVS, event_from_data, \
    GET, SET, OKResponse, NOResponse, BADResponse, NOWResponse


class TestEventMinder(unittest.TestCase):

    def setUp(self):
        self.scheduler = HistoricalScheduler()
        self.minder = RxEventMinder(self.scheduler)
    
    def test_event_minder_notify_after(self):
        mock = MagicMock()
        self.minder.notify_after(1.0, mock.callable, 1)
        
        self.scheduler.advance_by(timedelta(seconds=2.0))
        self.assertTrue(mock.callable.called)
        self.assertEqual(mock.callable.call_args[0], (1,))
        self.assertIsNone(self.minder.current_disposable)
    
    def test_event_minder_remove(self):
        mock = MagicMock()
        
        event = self.minder.notify_after(1.0, mock.callable, 0)
        self.scheduler.advance_by(timedelta(seconds=0.5))
        self.minder.remove(event)
        self.scheduler.advance_by(timedelta(seconds=1.0))
        
        self.assertFalse(mock.callable.called)
        self.assertIsNone(self.minder.current_disposable)
        self.assertEqual(len(self.minder._sched._queue), 0)
    
    def test_event_minder_never_execute(self):
        mock = MagicMock()

        self.minder.notify_after(1.0, mock.callable, 0)
        self.scheduler.advance_by(timedelta(seconds=0.2))
        
        self.assertFalse(mock.callable.called)
        self.assertIsNotNone(self.minder.current_disposable)
        self.assertEqual(len(self.minder._sched._queue), 1)
    
    def test_multiple_callbacks(self):
        mock = MagicMock()

        self.minder.notify_after(0.001, mock.callable1, 1)
        self.minder.notify_after(0.002, mock.callable2, 2)
        self.scheduler.advance_by(timedelta(0.003))
        
        self.assertTrue(mock.callable1.called)
        self.assertTrue(mock.callable2.called)
        self.assertIsNone(self.minder.current_disposable)
    
    def test_one_complete_one_pending(self):
        mock = MagicMock()

        self.minder.notify_after(0.001, mock.callable1, 1)
        self.minder.notify_after(0.2, mock.callable2, 2)
        self.scheduler.advance_by(timedelta(seconds=0.003))
        
        self.assertTrue(mock.callable1.called)
        self.assertFalse(mock.callable2.called)
        self.assertIsNotNone(self.minder.current_disposable)


class TestExampleMachine(unittest.TestCase):

    def setUp(self):
        self.simulator = ASCIIKVS()
        self.scheduler = HistoricalScheduler()
        self.protocol = RxSerialProtocol(
            event_from_data,
            terminator=b'\r',
            scheduler=self.scheduler)

    def _write(self, data):
        result = self.simulator.feed(data)
        if result:
            self.protocol.received_data(result)
    
    def test_simple_GET(self):
        get_command = GET(b'A')
        _result = []
        
        ob = self.protocol.send_request(get_command, write=self._write)
        ob.subscribe(on_next=lambda r: _result.append(r))
        result = _result[0]

        self.assertIsInstance(result, OKResponse)
        self.assertEqual(result.value, b'A')
    
    def test_simple_SET(self):
        set_command = SET(b'A', b'Z')
        _result = []
        
        ob = self.protocol.send_request(set_command, write=self._write)
        ob.subscribe(on_next=lambda r: _result.append(r))
        result = _result[0]

        self.assertIsInstance(result, OKResponse)
        self.assertEqual(result.value, b'Z')
    
    def test_no_response(self):
        set_command = SET(b'A', b'q')
        _result = []

        ob = self.protocol.send_request(set_command, write=self._write)
        ob.subscribe(on_next=lambda r: _result.append(r))
        result = _result[0]

        self.assertIsInstance(result, NOResponse)
        self.assertEqual(result.value, b'A')

    def test_bad_response(self):
        set_command = SET(b'C', b'A')
        _result = []

        ob = self.protocol.send_request(set_command, write=self._write)
        ob.subscribe(on_next=lambda r: _result.append(r))
        result = _result[0]

        self.assertIsInstance(result, BADResponse)
    
    def test_timeout(self):
        get_command = GET(b'A')
        _result = []
        _error = []
        
        def _write(data):
            # forget to write the data to the simulator...oops.
            pass
        
        ob = self.protocol.send_request(get_command, write=_write)
        ob.subscribe(
            on_next=lambda r: _result.append(r),
            on_error=lambda e: _error.append(e))
        self.scheduler.advance_by(timedelta(seconds=5.0))

        error = _error[0]
        
        self.assertIsNotNone(error)
        self.assertIsInstance(error, RxTimeoutError)

    def test_broadcasts(self):
        set_command = SET(b'B', b'Q')
        results = []
        events = []

        def _feed_now_event(*args):
            msg = self.simulator.broadcast()
            self.protocol.received_data(msg)

        broadcaster = Observable.interval(
            timedelta(seconds=1.0),
            scheduler=self.scheduler
        ).subscribe(on_next=_feed_now_event)

        event_soaker = self.protocol.events \
            .subscribe(on_next=lambda e: events.append(e))
        
        self.scheduler.advance_by(timedelta(seconds=0.5))
        self.assertEqual(len(events), 0)
        self.scheduler.advance_by(timedelta(seconds=1.0))
        self.assertEqual(len(events), 1)
        obs = self.protocol.send_request(set_command, write=self._write)
        obs.subscribe(on_next=lambda r: results.append(r))
        self.scheduler.advance_by(timedelta(seconds=1.0))
        self.scheduler.advance_by(timedelta(seconds=1.0))
        
        self.assertEqual(results[0].value, b'Q')
        self.assertEqual(len(events), 3)
        self.assertIsInstance(events[0], NOWResponse)
        self.assertEqual(events[0].B, b'A')
        self.assertEqual(events[1].B, b'Q')

        broadcaster.dispose()
        event_soaker.dispose()
    
    def test_concurrent_requests(self):
        set_command = SET(b'A', b'Z')
        get_command = GET(b'A')
        results = []
        
        o1 = self.protocol.send_request(get_command, write=self._write)
        o2 = self.protocol.send_request(set_command, write=self._write)
        Observable.merge([o1, o2]).subscribe(on_next=lambda r: results.append(r))

        self.assertEqual(results[0].value, b'A')
        self.assertEqual(results[1].value, b'Z')
    
    def test_several_concurrent_requests(self):
        results = []

        Observable.merge([
            self.protocol.send_request(SET(b'A', b'B'), write=self._write),
            self.protocol.send_request(SET(b'A', b'C'), write=self._write),
            self.protocol.send_request(SET(b'A', b'D'), write=self._write),
            self.protocol.send_request(SET(b'A', b'E'), write=self._write),
            self.protocol.send_request(GET(b'A'), write=self._write),
            self.protocol.send_request(SET(b'A', b'F'), write=self._write),
            self.protocol.send_request(SET(b'A', b'G'), write=self._write),
            self.protocol.send_request(SET(b'A', b'H'), write=self._write),
            self.protocol.send_request(SET(b'A', b'I'), write=self._write),
            self.protocol.send_request(SET(b'A', b'J'), write=self._write),
            self.protocol.send_request(GET(b'A'), write=self._write),
        ]).subscribe(on_next=lambda r: results.append(r))
        
        self.assertEqual(results[4].value, b'E')
        self.assertEqual(results[10].value, b'J')
