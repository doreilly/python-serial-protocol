from sched import scheduler


class EventMinder:
    
    def __init__(self):
        self._sched = scheduler(delayfunc=self._delayfunc)
    
    def _delayfunc(self, *args):
        delay = self._next_event_delay()
        if delay is None or delay >= 0:
            self.reset_timer()

    def _next_event_delay(self):
        if self._sched.empty():
            return None
        
        t, *_ = self._sched.queue[0]
        return t - self._sched.timefunc()

    def run(self):
        self._sched.run(blocking=False)

    def reset_timer(self):
        return NotImplementedError(
            f'{self.__class__.__name__} must implement reset_timer')

    def notify_after(self, delay, callable, *args, **kwargs):
        event = self._sched.enter(
            delay=delay,
            priority=0,
            action=callable,
            argument=args,
            kwargs=kwargs)
        
        self.reset_timer()

        return event
    
    def notify_at(self, time, callable, *args, **kwargs):
        event = self._sched.enterabs(
            time=time,
            priority=0,
            action=callable,
            argument=args,
            kwargs=kwargs)
        
        self.reset_timer()

        return event
    
    def remove(self, event):
        self._sched.cancel(event)
        self.reset_timer()
