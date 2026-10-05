import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from common.irc_message import message
from server.handlers import IRCHandlers


class HandlerTests(unittest.TestCase):
    def test_unexpected_error_is_not_sent_as_unknown_command(self):
        server = SimpleNamespace(monotonic=lambda: 1.0, send=Mock())
        client = SimpleNamespace(registered=True, last_activity=0.0)
        handlers = IRCHandlers(server)

        def broken_handler(_client, _params):
            raise RuntimeError("internal failure")

        handlers.cmd_time = broken_handler
        with self.assertRaisesRegex(RuntimeError, "internal failure"):
            handlers.handle(client, message("TIME"))

        server.send.assert_not_called()


if __name__ == "__main__":
    unittest.main()
