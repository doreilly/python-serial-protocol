import asyncio
import logging

from .timing import EventMinder
from .machine import EventMachine
from .protocol import ProtocolDelegate

logger = logging.getLogger(__name__)


class RequestTimeout(asyncio.TimeoutError):
    
    def __init__(self, request):
        self.request = request


class AsyncIOEventMinder(EventMinder):
    
    def __init__(self, loop=None):
        if loop is None:
            loop = asyncio.get_event_loop()

        super().__init__()
        self.loop = loop
        self._timer_handle = None

    def reset_timer(self):
        if self._timer_handle is not None:
            self._timer_handle.cancel()
            self._timer_handle = None
        
        delay = self._next_event_delay()

        if delay is not None:
            self._timer_handle = self.loop.call_later(
                delay, self.run)


class AsyncIOEventMachineProtocol(asyncio.Protocol):

    @classmethod
    def factory(cls, event_parser, terminator, *, loop=None):
        return lambda: cls(event_parser, terminator, loop=loop)

    def __init__(self, event_parser, terminator, *, loop=None):
        self._transport = None
        self.futures = {}
        self.event_queue = asyncio.Queue()
        self.event_parser = event_parser
        self.machine = EventMachine(
            AsyncIOEventMinder(loop=loop),
            self,
            terminator)

    # - asyncio.Protocol methods -
    
    def connection_made(self, transport):
        self._transport = transport

    def data_received(self, data):
        self.machine.receive_data(data)
    
    # - ProtocolDelegate methods -

    def request_timed_out(self, request):
        try:
            f = self.futures.pop(request)
        except KeyError:  # pragma: no cover
            logger.exception('Timeout called for unknown request.')
        else:
            f.set_exception(RequestTimeout(request))

    def event_received(self, event):
        self.event_queue.put_nowait(event)

    def request_completed(self, request, response):
        try:
            f = self.futures.pop(request)
        except KeyError:  # pragma: no cover
            logger.exception('Completed called for unknown request.')
        else:
            f.set_result(response)

    def event_for_data(self, data, requests):
        return self.event_parser(data, requests)

    # - asyncio interface -

    def send_request(self, request):
        self.machine.send(request, self._transport.write)
        return self.futures.setdefault(request, asyncio.Future())

    def get_latest_event(self):
        return self.event_queue.get()
