import unittest


from .example_machine import *


class TestMachineSansIO(unittest.TestCase):

    def setUp(self):
        self.machine = ASCIIKVS()
    
    def test_feed_simple_get(self):
        r = self.machine.feed(b'GET A\r')

        self.assertEqual(r, b'OK A A\r')
    
    def test_feed_simple_set(self):
        r = self.machine.feed(b'SET A Z\r')

        self.assertEqual(r, b'OK A Z\r')
    
    def test_feed_set_both(self):
        r1 = self.machine.feed(b'SET A Q\r')
        self.assertEqual(r1, b'OK A Q\r')

        r2 = self.machine.feed(b'SET B G\r')
        self.assertEqual(r2, b'OK B G\r')
    
    def test_simple_now(self):
        r = self.machine.broadcast()

        self.assertEqual(r, b'NOW A A B A\r')
    
    def test_now_after_sets(self):
        self.machine.feed(b'SET A F\r')
        self.machine.feed(b'SET B T\r')
        r = self.machine.broadcast()

        self.assertEqual(r, b'NOW A F B T\r')
    
    def test_non_cap_set(self):
        r = self.machine.feed(b'SET A g\r')

        self.assertEqual(r, b'NO A A\r')
    
    def test_non_available_slot(self):
        r = self.machine.feed(b'SET C C\r')

        self.assertEqual(r, b'BAD\r')
    
    def test_non_command(self):
        r = self.machine.feed(b'WHAT A\r')

        self.assertEqual(r, b'BAD\r')
