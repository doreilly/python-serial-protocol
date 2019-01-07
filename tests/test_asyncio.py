import asyncio
import unittest
from unittest.mock import MagicMock

from serial_protocol.asyncio import \
    AsyncIOEventMachineProtocol, AsyncIOEventMinder, RequestTimeout

from .example_machine import ASCIIKVS, event_from_data, \
    GET, SET, OKResponse, NOResponse, BADResponse, NOWResponse


class TestEventMinder(unittest.TestCase):

    def setUp(self):
        self.loop = asyncio.get_event_loop()
        self.minder = AsyncIOEventMinder(loop=self.loop)
    
    def test_minder_calls_call_later(self):
        loop = MagicMock()
        minder = AsyncIOEventMinder(loop=loop)
        mock = MagicMock()
        minder.notify_after(0.05, mock.callable, 1)

        self.assertTrue(loop.call_later.called)
        self.assertAlmostEqual(
            loop.call_later.call_args[0][0],
            0.05,
            delta=0.001)
        self.assertFalse(mock.callable.called)

    def test_event_minder_notify_after(self):
        mock = MagicMock()
        self.minder.notify_after(0.001, mock.callable, 1)
        sleeper = asyncio.sleep(0.002, loop=self.loop)

        self.loop.run_until_complete(sleeper)
        self.assertTrue(mock.callable.called)
        self.assertEqual(mock.callable.call_args[0], (1,))
        self.assertIsNone(self.minder._timer_handle)
    
    def test_event_minder_remove(self):
        mock = MagicMock()

        async def canceller():
            event = self.minder.notify_after(0.005, mock.callable, 0)
            await asyncio.sleep(0.002)
            self.minder.remove(event)
            await asyncio.sleep(0.005)
        
        self.loop.run_until_complete(canceller())
        self.assertFalse(mock.callable.called)
        self.assertIsNone(self.minder._timer_handle)
        self.assertEqual(len(self.minder._sched._queue), 0)
    
    def test_event_minder_never_execute(self):
        mock = MagicMock()

        async def partial_runner():
            self.minder.notify_after(1.0, mock.callable, 0)
            await asyncio.sleep(0.002)
        
        self.loop.run_until_complete(partial_runner())
        self.assertFalse(mock.callable.called)
        self.assertIsNotNone(self.minder._timer_handle)
        self.assertEqual(len(self.minder._sched._queue), 1)
    
    def test_multiple_callbacks(self):
        mock = MagicMock()

        async def dual_runner():
            self.minder.notify_after(0.001, mock.callable1, 1)
            self.minder.notify_after(0.002, mock.callable2, 2)
            await asyncio.sleep(0.003)
        
        self.loop.run_until_complete(dual_runner())
        self.assertTrue(mock.callable1.called)
        self.assertTrue(mock.callable2.called)
        self.assertIsNone(self.minder._timer_handle)
    
    def test_one_complete_one_pending(self):
        mock = MagicMock()

        async def dual_runner():
            self.minder.notify_after(0.001, mock.callable1, 1)
            self.minder.notify_after(0.2, mock.callable2, 2)
            await asyncio.sleep(0.003)
        
        self.loop.run_until_complete(dual_runner())
        self.assertTrue(mock.callable1.called)
        self.assertFalse(mock.callable2.called)
        self.assertIsNotNone(self.minder._timer_handle)


class AsyncIOSimulatorProtocol(asyncio.Protocol):

    def __init__(self, simulate_delay=0):
        self.simulator = ASCIIKVS()
        self.delay = simulate_delay
    
    def connection_made(self, transport):
        self.transport = transport
    
    def connection_lost(self, exc):
        self.transport = None
    
    def data_received(self, data):
        if data[0] == ord(b'b'):  # special signal to broadcast
            self.transport.write(self.simulator.broadcast())
            return
        r = self.simulator.feed(data)
        if r:
            asyncio.get_event_loop().call_later(
                self.delay, self.transport.write, r)


def create_test_server(loop, host='localhost', port=12345):
    protocol_factory = AsyncIOSimulatorProtocol
    return loop.create_server(protocol_factory, host, port)


class TestExampleMachine(unittest.TestCase):

    def setUp(self):
        self.loop = asyncio.get_event_loop()
        self.protocol = AsyncIOEventMachineProtocol.factory(
            event_from_data,
            terminator=b'\r',
            loop=self.loop)
    
    def tearDown(self):
        async def closer():
            self.server.close()
            await self.server.wait_closed()
        
        if hasattr(self, 'server'):
            self.loop.run_until_complete(closer())

    def _create_server(self, delay=None):
        if delay is None:
            protocol_factory = AsyncIOSimulatorProtocol
        else:
            protocol_factory = (  # noqa: E731
                lambda: AsyncIOSimulatorProtocol(simulate_delay=delay))
        return self.loop.create_server(protocol_factory, 'localhost', 12345)

    def _create_client(self):
        return self.loop.create_connection(self.protocol, 'localhost', 12345)
    
    async def _init_connection(self, delay=None):
        self.server = await self._create_server(delay=delay)
        self.transport, self.client = await self._create_client()

    def test_simple_GET(self):
        get_command = GET(b'A')
        
        async def runner():
            await self._init_connection()
            result = await self.client.send_request(get_command)
            return result

        result = self.loop.run_until_complete(runner())
        self.assertIsInstance(result, OKResponse)
        self.assertEqual(result.value, b'A')
    
    def test_simple_SET(self):
        set_command = SET(b'A', b'Z')
        
        async def runner():
            await self._init_connection()
            result = await self.client.send_request(set_command)
            return result

        result = self.loop.run_until_complete(runner())
        self.assertIsInstance(result, OKResponse)
        self.assertEqual(result.value, b'Z')
    
    def test_no_response(self):
        set_command = SET(b'A', b'q')
        
        async def runner():
            await self._init_connection()
            result = await self.client.send_request(set_command)
            return result

        result = self.loop.run_until_complete(runner())
        self.assertIsInstance(result, NOResponse)
        self.assertEqual(result.value, b'A')

    def test_bad_response(self):
        set_command = SET(b'C', b'A')
        
        async def runner():
            await self._init_connection()
            result = await self.client.send_request(set_command)
            return result

        result = self.loop.run_until_complete(runner())
        self.assertIsInstance(result, BADResponse)
    
    def test_timeout(self):
        get_command = GET(b'A')

        async def runner():
            await self._init_connection(delay=1.0)
            try:
                await self.client.send_request(get_command)
            except RequestTimeout:
                pass
            else:
                self.assertFalse(True, 'exception not raised')
            finally:
                self.server.close()
                await self.server.wait_closed()
        
        self.loop.run_until_complete(runner())
    
    def test_broadcasts(self):
        set_command = SET(b'B', b'Q')

        async def runner():
            await self._init_connection()
            self.transport.write(b'b\n')
            await asyncio.sleep(0.001)
            result = await self.client.send_request(set_command)
            self.transport.write(b'b\n')
            await asyncio.sleep(0.001)
            self.transport.write(b'b\n')
            await asyncio.sleep(0.001)
            return result
        
        result = self.loop.run_until_complete(runner())
        self.assertEqual(result.value, b'Q')
        self.assertEqual(self.client.event_queue.qsize(), 3)
        responses = [self.client.event_queue.get_nowait() for _ in range(3)]
        self.assertIsInstance(responses[0], NOWResponse)
        self.assertEqual(responses[0].B, b'A')
        self.assertEqual(responses[1].B, b'Q')
    
    def test_broadcasts_dequeue(self):
        events = []
        
        async def puller():
            while True:
                events.append(await self.client.get_latest_event())
        
        async def runner():
            await self._init_connection()
            asyncio.ensure_future(puller())
            self.transport.write(b'b\n')
            await asyncio.sleep(0.001)
            self.transport.write(b'b\n')
            await asyncio.sleep(0.001)
            self.transport.write(b'b\n')
            await asyncio.sleep(0.001)
        
        self.loop.run_until_complete(runner())
        self.assertEqual(self.client.event_queue.qsize(), 0)
        self.assertEqual(len(events), 3)
    
    def test_concurrent_requests(self):
        set_command = SET(b'A', b'Z')
        get_command = GET(b'A')
        
        async def runner():
            await self._init_connection(delay=0.05)
            c1 = self.client.send_request(get_command)
            c2 = self.client.send_request(set_command)
            await asyncio.wait((c1, c2), loop=self.loop)
            return [c1.result(), c2.result()]

        results = self.loop.run_until_complete(runner())
        self.assertEqual(results[0].value, b'A')
        self.assertEqual(results[1].value, b'Z')
    
    def test_several_concurrent_requests(self):
        async def runner():
            results = []
            await self._init_connection(delay=0.05)
            self.client.send_request(SET(b'A', b'B'))
            self.client.send_request(SET(b'A', b'C'))
            self.client.send_request(SET(b'A', b'D'))
            self.client.send_request(SET(b'A', b'E'))
            c1 = self.client.send_request(GET(b'A'))
            self.client.send_request(SET(b'A', b'F'))
            self.client.send_request(SET(b'A', b'G'))
            self.client.send_request(SET(b'A', b'H'))
            self.client.send_request(SET(b'A', b'I'))
            self.client.send_request(SET(b'A', b'J'))
            c2 = self.client.send_request(GET(b'A'))
            for f in asyncio.as_completed((c1, c2), loop=self.loop):
                results.append(await f)
            return results
        
        results = self.loop.run_until_complete(runner())
        self.assertEqual(results[0].value, b'E')
        self.assertEqual(results[1].value, b'J')
