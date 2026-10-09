import unittest
from unittest.mock import Mock

from scripts.live_validate import LiveDecoder, wait_for


class LiveValidationTests(unittest.TestCase):
    def test_wait_retains_coalesced_messages_for_next_call(self):
        sock = Mock()
        sock.recv.return_value = b":server 001 alice :Welcome\r\n:alice JOIN #room\r\n"
        decoder = LiveDecoder()
        wait_for(sock, decoder, lambda msg: msg.command == "001")
        joined = wait_for(sock, decoder, lambda msg: msg.command == "JOIN")
        self.assertEqual(joined.params, ("#room",))
        sock.recv.assert_called_once()
