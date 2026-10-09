import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from common.irc_message import message
from server.handlers import IRCHandlers


class HandlerTests(unittest.TestCase):
    def test_privmsg_checks_encoded_relay_length(self):
        client = SimpleNamespace(nick="alice", prefix="alice!u@host")
        destination = object()
        server = SimpleNamespace(
            server_name="server.test", send=Mock(),
            state=SimpleNamespace(direct_target=lambda target: destination),
        )
        handlers = IRCHandlers(server)
        overhead = len(message("PRIVMSG", "bob", "", prefix=client.prefix).to_bytes()) - 1
        for text, expected in [("x" * (512 - overhead), "PRIVMSG"),
                               ("x" * (513 - overhead), "417"),
                               ("界" * 170, "417")]:
            with self.subTest(text_length=len(text)):
                server.send.reset_mock()
                handlers.cmd_privmsg(client, ("bob", text))
                reply = server.send.call_args.args[1]
                self.assertEqual(reply.command, expected)
                self.assertLessEqual(len(reply.to_bytes()), 512)

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

    def test_invalid_channel_target_returns_numeric_error(self):
        server = SimpleNamespace(server_name="server.test", send=Mock())
        client = SimpleNamespace(nick="alice", prefix="alice!u@host")
        IRCHandlers(server).cmd_privmsg(client, ("#", "hello"))

        reply = server.send.call_args.args[1]
        self.assertEqual(reply.command, "403")
        self.assertEqual(reply.params[1], "#")

    def test_names_replies_are_split_before_irc_line_limit(self):
        members = [SimpleNamespace(nick=f"user{index:03d}") for index in range(100)]
        state = SimpleNamespace(channel_members=lambda _channel: members)
        server = SimpleNamespace(server_name="server.test", state=state, send=Mock())
        client = SimpleNamespace(nick="alice")

        IRCHandlers(server).send_names(client, "#room")

        replies = [call.args[1] for call in server.send.call_args_list]
        name_replies = [reply for reply in replies if reply.command == "353"]
        self.assertGreater(len(name_replies), 1)
        self.assertTrue(all(len(reply.to_bytes()) <= 512 for reply in name_replies))
        advertised = " ".join(reply.params[-1] for reply in name_replies).split()
        self.assertEqual(advertised, [member.nick for member in members])
        self.assertEqual(replies[-1].command, "366")


if __name__ == "__main__":
    unittest.main()
