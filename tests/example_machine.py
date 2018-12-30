"""
A simple two-way + broadcast appliance simulator.

The appliance: a tiny key-value store.  There are two slots labeled A and B.
The maximum length of the string is 1 ASCII character.

The ASCII text-based protocol is as follows:

<term> = the carriage return character (e.g. b'\x0d')
<value> = any uppercase letter
<slot> = the character 'A' or 'B'

To set a value:
    SET <slot> <value><term>

In response, the appliance will return the current state of the machine.

Successful response:
    OK <slot> <value><term>
Error response:
    NO <slot> <value><term>

To get a value:
    GET <slot><term>

Successful response:
    OK <slot> <value><term>

Occasionally the machine will broadcast its current state:
    NOW A <value> B <value><term>

If a request is ever unrecognized, the response is:
    BAD<term>
"""

import re

from serial_protocol.events import Event


class ASCIIKVS:
    
    def __init__(self):
        self.A = b'A'
        self.B = b'A'
    
    def feed(self, command):
        if command[-1] != 0x0d:
            return b'BAD\r'
        
        components = command.rstrip().split(b' ')
        action = components[0]
        slot = components[1]

        if slot not in (b'A', b'B'):
            return b'BAD\r'

        slot_name = slot.decode('ascii')

        if action == b'GET' and len(components) == 2:
            return b'OK %b %b\r' % (slot, getattr(self, slot_name))
        
        if action == b'SET' and len(components) == 3:
            value = components[2]
            
            status = b'OK'

            if not b'A' <= value <= b'Z':
                status = b'NO'
            else:
                setattr(self, slot_name, value)
    
            return b'%b %b %b\r' % (status, slot, getattr(self, slot_name))

        return b'BAD\r'
    
    def broadcast(self):
        return b'NOW A %b B %b\r' % (self.A, self.B)


class AKVSEvent(Event):
    
    def __init__(self):
        super().__init__()
        self.timeout = 0.1


class GET(AKVSEvent):
    
    def __init__(self, slot):
        super().__init__()
        self.slot = slot
    
    def to_bytes(self):
        return b'GET %b\r' % (self.slot)


class SET(AKVSEvent):

    def __init__(self, slot, value):
        super().__init__()
        self.slot = slot
        self.value = value
    
    def to_bytes(self):
        return b'SET %b %b\r' % (self.slot, self.value)


class NOWResponse(AKVSEvent):
    pattern = re.compile(br'^NOW A ([A-Z]) B ([A-Z])\r$')

    @classmethod
    def from_bytes(cls, data):
        m = cls.pattern.match(data)

        if m is None:
            raise ValueError()

        instance = cls()
        instance.A = m.group(1)
        instance.B = m.group(2)
        return instance


class OKResponse(AKVSEvent):
    pattern = re.compile(br'^OK (A|B) ([A-Z])\r$')

    @classmethod
    def from_bytes(cls, data):
        m = cls.pattern.match(data)
        
        if m is None:
            raise ValueError()
        
        instance = cls()
        instance.slot = m.group(1)
        instance.value = m.group(2)
        return instance


class NOResponse(AKVSEvent):
    pattern = re.compile(br'^NO (A|B) ([A-Z])\r$')

    @classmethod
    def from_bytes(cls, data):
        m = cls.pattern.match(data)
        
        if m is None:
            raise ValueError()
        
        instance = cls()
        instance.slot = m.group(1)
        instance.value = m.group(2)
        return instance


class BADResponse(AKVSEvent):
    pattern = re.compile(br'^BAD\r$')

    @classmethod
    def from_bytes(cls, data):
        m = cls.pattern.match(data)
        
        if m is None:
            raise ValueError()
        
        instance = cls()

        return instance


def event_from_data(data, requests):
    request = None

    for klass in (NOWResponse, OKResponse, NOResponse, BADResponse):
        try:
            instance = klass.from_bytes(data)
        except ValueError:
            continue
            
        if not isinstance(instance, NOWResponse) and len(requests):
            request = list(requests)[0]
        
        return instance, request
    else:
        raise ValueError()
