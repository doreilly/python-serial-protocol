# Serial communications protocol builder

A python library that makes machines for communicating with byte-based serial
devices with an I/O agnostic core. It assumes a common delimeter among responses
and uses an Class-based Event infrastructure for sending and matching commands.

- [x] Serial delivery of messages, with an optional timeout
- [x] Asynchronous message handling for non-Request/Response information
      (e.g. Status messages)
- [x] asyncio wrapper that provides a Future-based request/response interface
- [x] RxPY wrapper that provides an Observable interface to the protocol
      machine, and remains I/O agnostic.

# Components

## Event Minder

The event minder is a subclass of `serial_protocol.timing.EventMinder`.  This is
used to monitor timeouts of non-responsive servers.

To implement one for your platform, define the `reset_timer` method.  This
method schedule the next call to the minder's `run` method, given the set of
waiting tasks

## ProtocolDelegate

An instance of the protocol class receives callbacks upon the machine's
interactions. It has four callbacks, one is necessary for the request/response
matching to happen:

### `event_for_data(self, data: bytes, requests: Iterable[object]) -> (object, object)`

Parameters:
- `data`: The received byte sequence (including the protocol's response terminator)
- `requests`: An iterable of request command objects sent to the machine in the order
  originally provided.

Return: a tuple of `(Response, Request)` objects.  If the event is unhandled,
returning `(None, None)` is sufficient.  If there is no request to match this
message, return `(Event, None)`.

### `request_completed(self, request: object, response: object)`

Called upon a completed request.

### `request_timed_out(self, request: object)`

Called if no response is received within the specified timeout window.

### `event_received(self, event: object)`

Called when an un-requested but recognized event is received.

## Event Machine

The core logic is embedded within an `EventMachine` instance. To initialize one,
one needs to know the terminating byte pattern (e.g. b'\n' or b'\r\n'), an
EventMinder instance, and protocol delegate (as defined above),

### `send(self, request: object, write: Callable)`

Pass in an object that contains a `timeout` attribute, and a `to_bytes()` method.
If `timeout` is None, the response can come at any time.  The value of
`to_bytes()` will be written by calling `write` when pending requests are
complete.

# asyncio integration

Included in the package is the `asyncio` module that incldues an asynchronous
EventMinder instance, and an `asyncio.Protocol` class that also conforms to the
ProtocolDelegate to handle async/await-style communication with request/response
protocols.  To use it, provide a callable that works as the
`ProtocolDelegate.event_for_data` does, and a terminator.  To ease integration,
the class method `factory` can be used to pass to `asyncio` connection functions
as a protocol_factory.

```
import asyncio
from serial_protocol.asyncio import AsyncIOEventMachineProtocol

from .events import Event, Request


def event_for_data(data, requests):
    return (Event(data), list(requests)[0])


protocol_factory = AsyncIOEventMachineProtocol.factory(event_for_data, b'\n')

...

transport, protocol = await asyncio.get_event_loop().create_connection(
    protocol_factory,
    'localhost',
    12345)

response = await protocol.send_request(Request(b'Hello'))
```

# RxPY integration

Included in the package is the `rx` module that includes an Rx wrapper around
the EventMachine/EventMinder interface. I/O is still in the domain of the
hosting application. The application must also provide the Rx scheduler instance
for handling the timeouts, etc.

```
import rx
from serial_protocol.rx import RxSerialProtocol

from .events import Event, Request


def event_for_data(data, requests):
    return (Event(data), list(requests)[0])


scheduler = rx.concurrency.ThreadPoolScheduler()

protocol = RxSerialProtocol(event_for_data, scheduler)

protocol.send_request(Request(b'Hello')).subscribe(
    on_next=lambda resp: print(resp))

...
```
