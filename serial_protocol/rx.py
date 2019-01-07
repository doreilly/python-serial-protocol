from datetime import timedelta

from rx.subjects import Subject, ReplaySubject

from .machine import EventMachine
from .timing import EventMinder
from .protocol import ProtocolDelegate


class RxTimeoutError(Exception):
    pass


class RxEventMinder(EventMinder):

    def __init__(self, scheduler):
        self.scheduler = scheduler
        super().__init__(timefunc=self._timefunc)
        self.current_disposable = None
    
    def _timefunc(self):
        return self.scheduler.now.timestamp()

    def reset_timer(self):
        if self.current_disposable is not None:
            self.current_disposable.dispose()
            self.current_disposable = None
        
        delay = self._next_event_delay()

        if delay is not None:
            self.current_disposable = self.scheduler.schedule_relative(
                timedelta(seconds=delay),
                lambda *args: self.run())


class RxSerialProtocol(ProtocolDelegate):

    def __init__(self, event_parser, scheduler, terminator=b'\n'):
        self.event_parser = event_parser
        minder = RxEventMinder(scheduler)
        self.machine = EventMachine(minder, self, terminator)
        self.events = Subject()
        self.requests = {}
    
    # delegate interface

    def event_received(self, event):
        self.events.on_next(event)
    
    def request_timed_out(self, request):
        self.requests.pop(request).on_error(RxTimeoutError())
    
    def request_completed(self, request, response):
        observer = self.requests.pop(request)
        observer.on_next(response)
        observer.on_completed()
    
    def event_for_data(self, data, requests):
        return self.event_parser(data, requests)
    
    # external interface

    def send_request(self, request, write):
        obs = self.requests.setdefault(request, ReplaySubject())
        self.machine.send(request, write)
        return obs

    def received_data(self, data):
        self.machine.receive_data(data)
