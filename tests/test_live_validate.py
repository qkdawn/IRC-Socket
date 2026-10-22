import unittest
from unittest.mock import Mock
from unittest.mock import patch

from scripts.live_validate import LiveDecoder, connect, wait_for


class LiveValidationTests(unittest.TestCase):
    def test_connect_failure_closes_socket(self):
        sock = Mock()
        sock.connect.side_effect = TimeoutError("connect timed out")
        with patch("scripts.live_validate.socket.socket", return_value=sock):
            with self.assertRaises(TimeoutError):
                connect("::1", 6667, "alice")
        sock.settimeout.assert_called_once_with(5.0)
        sock.close.assert_called_once()

    def test_registration_failure_closes_socket(self):
        sock = Mock()
        with (
            patch("scripts.live_validate.socket.socket", return_value=sock),
            patch("scripts.live_validate.wait_for", side_effect=TimeoutError("registration")),
        ):
            with self.assertRaisesRegex(TimeoutError, "registration"):
                connect("::1", 6667, "alice")
        sock.close.assert_called_once()

    def test_wait_retains_coalesced_messages_for_next_call(self):
        sock = Mock()
        sock.recv.return_value = b":server 001 alice :Welcome\r\n:alice JOIN #room\r\n"
        decoder = LiveDecoder()
        wait_for(sock, decoder, lambda msg: msg.command == "001")
        joined = wait_for(sock, decoder, lambda msg: msg.command == "JOIN")
        self.assertEqual(joined.params, ("#room",))
        sock.recv.assert_called_once()
