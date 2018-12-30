import unittest
from unittest.mock import MagicMock

from serial_protocol.machine import EventMachine
from serial_protocol.protocol import ProtocolDelegate

from .example_machine import \
    ASCIIKVS, GET, SET, NOWResponse, NOResponse, BADResponse, \
    event_from_data


class TestMedium:

    def __init__(self, machine):
        self.simulator = ASCIIKVS()
        self.machine = machine
    
    def write(self, data):
        r = self.simulator.feed(data)
        if r:
            self.machine.receive_data(r)
    
    def get_broadcast(self):
        self.machine.receive_data(self.simulator.broadcast())


class TestDelegate(ProtocolDelegate):

    def __init__(self):
        self.events = []
        self.responses = []
        self.timeouts = []
    
    def event_for_data(self, data, requests):
        return event_from_data(data, requests)
    
    def request_timed_out(self, request):
        self.timeouts.append(request)
    
    def request_completed(self, request, response):
        self.responses.append((request, response))

    def event_received(self, event):
        self.events.append(event)


class TestTimingFreeExampleMachineProtocol(unittest.TestCase):

    def setUp(self):
        self.delegate = TestDelegate()
        self.minder = MagicMock()
        self.machine = EventMachine(
            self.minder, self.delegate, terminator=b'\r')
        self.medium = TestMedium(self.machine)
    
    def test_SET(self):
        command = SET(b'A', b'Z')
        self.assertAlmostEqual(command.timeout, 0.1)

        self.machine.send(command, self.medium.write)

        self.assertEqual(len(self.delegate.responses), 1)
        request, response = self.delegate.responses[0]
        self.assertEqual(request, command)
        self.assertEqual(response.value, b'Z')
        self.assertTrue(self.minder.notify_after.called)
        self.assertTrue(self.minder.remove.called)
    
    def test_GET(self):
        set_command = SET(b'A', b'Z')
        self.machine.send(set_command, self.medium.write)
        get_command = GET(b'A')
        self.machine.send(get_command, self.medium.write)

        self.assertEqual(len(self.delegate.responses), 2)
        (req1, res1), (req2, res2) = self.delegate.responses
        self.assertEqual(req1, set_command)
        self.assertEqual(res1.value, b'Z')
        self.assertEqual(req2, get_command)
        self.assertEqual(res2.value, b'Z')
    
    def test_bad_command(self):
        set_command = SET(b'C', b'g')
        self.machine.send(set_command, self.medium.write)

        self.assertEqual(len(self.delegate.responses), 1)
        request, response = self.delegate.responses[0]
        self.assertEqual(set_command, request)
        self.assertIsInstance(response, BADResponse)
    
    def test_out_of_range_SET(self):
        set_command = SET(b'B', b'q')
        self.machine.send(set_command, self.medium.write)

        self.assertEqual(len(self.delegate.responses), 1)
        request, response = self.delegate.responses[0]
        self.assertEqual(set_command, request)
        self.assertIsInstance(response, NOResponse)
        self.assertEqual(response.value, b'A')
    
    def test_notification(self):
        self.medium.get_broadcast()

        self.assertEqual(len(self.delegate.responses), 0)
        self.assertEqual(len(self.delegate.events), 1)
        e = self.delegate.events[0]
        self.assertIsInstance(e, NOWResponse)
        self.assertEqual(e.A, b'A')
        self.assertEqual(e.B, b'A')
