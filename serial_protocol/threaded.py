from concurrent.futures import Future, TimeoutError
from queue import Queue
from threading import Timer, Thread

from .timing import EventMinder
from .protocol import ProtocolDelegate
from .machine import EventMachine


class RequestTimeout(TimeoutError):

    def __init__(self, request):
        self.request = request


class ThreadedEventMinder(EventMinder):

    def __init__(self):
        super().__init__()
        self._timer = None

    def reset_timer(self):
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None
        
        delay = self._next_event_delay()

        if delay is not None:
            self._timer = Timer(
                interval=delay,
                function=self.run)


class ThreadedProtocol(ProtocolDelegate):

    def __init__(self, event_parser, terminator, read, write):
        self.read_thread = Thread(target=self.read_data, args=(read,))
        self.write = write
        self.event_parser = event_parser
        self.machine = EventMachine(
            ThreadedEventMinder(),
            self,
            terminator)
        self.futures = {}
        self.events = Queue()
        self.read_thread.start()
    
    def read_data(self, read):
        while True:
            self.machine.receive_data(read())
    
    def event_received(self, event):
        self.events.put_nowait(event)
    
    def request_completed(self, request, response):
        try:
            f = self.futures.pop(request)
        except KeyError:
            pass
        else:
            f.set_result(response)

    def request_timed_out(self, request):
        try:
            f = self.futures.pop(request)
        except KeyError:
            pass
        else:
            f.set_exception(RequestTimeout(request))

    def send_request(self, request):
        self.machine.send(request, self.write)
        return self.futures.setdefault(request, Future())
    
    def get_next_event(self):
        return self.events.get()
