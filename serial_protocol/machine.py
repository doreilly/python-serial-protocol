from collections import OrderedDict


class EventMachine:

    def __init__(self, event_minder, delegate, terminator=b'\n'):
        self.event_minder = event_minder
        self.delegate = delegate
        self._input_buffer = bytearray()
        self._terminator = terminator
        self.waiting_requests = OrderedDict()
        self.pending_requests = OrderedDict()

    def process_incoming_data(self, data):
        event, request = self.delegate.event_for_data(
            data, self.waiting_requests.keys())

        if request:
            self._completed(request)
            self.delegate.request_completed(request, event)
        else:
            self.delegate.event_received(event)
        
        return event

    def receive_data(self, data):
        assert isinstance(data, bytes)
        # print('received: %r' % data)
        self._input_buffer += data
        completes = []

        if self._terminator in self._input_buffer:
            *completes, self._input_buffer = self._input_buffer.split(
                self._terminator)
        
        events = [
            self.process_incoming_data(bytes(complete + self._terminator))
            for complete in completes]

        return events

    def send(self, request, write=None):
        if self.waiting_requests:
            self.pending_requests[request] = write
        else:
            self._write_request(request, write)
    
    def _write_request(self, request, write):
        handle = None
        
        if request.timeout is not None:
            handle = self.event_minder.notify_after(
                delay=request.timeout,
                callable=self._timed_out,
                request=request)
        
        self.waiting_requests[request] = handle
        write(request.to_bytes())

    def _send_next_request(self):
        if self.pending_requests:
            request, write = self.pending_requests.popitem(last=False)
            self._write_request(request, write)
    
    def _completed(self, request):
        if request in self.waiting_requests:
            handle = self.waiting_requests.pop(request)
            if handle:
                self.event_minder.remove(handle)
            self._send_next_request()
    
    def _timed_out(self, request):
        if request in self.waiting_requests:
            self.waiting_requests.pop(request)
            self.delegate.request_timed_out(request)
            self._send_next_request()
