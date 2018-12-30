class ProtocolDelegate:  # pragma: no cover
    def __init__(self):
        pass

    def event_for_data(self, data, requests):
        raise NotImplementedError(
            f'{self.__class__.__name__} must implement event_for_data(bytes)')
        
    def request_timed_out(self, request):
        pass
    
    def request_completed(self, request, response):
        pass
    
    def event_received(self, event):
        pass
