import unittest
import threading
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock

from bot.client import BotClient
from bot.commands import BotCommandProcessor
from bot.state import BotState
from common.irc_message import IRCMessage, message
from server.client_session import ClientSession
from server.server import IRCServer
from tests.helpers import start_writer


class BotTests(unittest.TestCase):
    def test_long_private_facts_preserve_content_in_bounded_relay_messages(self):
        for fact in (
            "large fact " * 100,
            "\u754c\U0001f642" * 160,
            ":" + "x" * 254 + "\u754c" * 90,
        ):
            with self.subTest(fact_prefix=fact[:5]), TemporaryDirectory() as directory:
                path = Path(directory) / "facts.txt"
                path.write_text(fact, encoding="utf-8")
                bot = BotClient(nickname="b" * 30)
                bot.commands = BotCommandProcessor(bot.nickname, facts_path=path)
                bot.socket = Mock()
                target = "a" * 30
                bot.handle(
                    message("PRIVMSG", bot.nickname, "fact", prefix=target + "!u@host")
                )
                requests = [
                    IRCMessage.parse(call.args[0].decode("utf-8"))
                    for call in bot.socket.sendall.call_args_list
                ]
                self.assertGreater(len(requests), 1)

                server = IRCServer()
                sender = ClientSession(
                    server, Mock(), ("ffff:ffff:ffff:ffff:ffff:ffff:255.255.255.255", 1)
                )
                receiver = ClientSession(server, Mock(), ("::1", 2))
                for session, nickname in ((sender, bot.nickname), (receiver, target)):
                    server.state.add_client(session.client)
                    server.state.set_nick(session.client, nickname)
                    server.state.set_user(session.client, "u" * 30, "Real")
                delivered_all = threading.Event()

                def receive(_payload):
                    if receiver.socket.sendall.call_count == len(requests):
                        delivered_all.set()

                receiver.socket.sendall.side_effect = receive
                start_writer(self, receiver)
                self.addCleanup(sender.close)
                for request in requests:
                    server.handlers.handle(sender.client, request)
                self.assertTrue(delivered_all.wait(2))
                delivered = [
                    IRCMessage.parse(call.args[0].decode("utf-8"))
                    for call in receiver.socket.sendall.call_args_list
                ]
                self.assertEqual(len(delivered), len(requests))
                self.assertEqual(
                    "".join(reply.params[-1] for reply in delivered), fact.strip()
                )
                self.assertTrue(
                    all(
                        reply.command == "PRIVMSG" and reply.params[0] == target
                        for reply in delivered
                    )
                )
                self.assertTrue(
                    all(len(reply.to_bytes()) <= 512 for reply in delivered)
                )

    def test_nul_containing_facts_are_skipped_and_all_invalid_file_uses_fallback(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "facts.txt"
            path.write_text("bad\x00fact\nvalid fact\n", encoding="utf-8")
            commands = BotCommandProcessor("SuperBot", facts_path=path)
            self.assertEqual(commands.facts, ["valid fact"])
            path.write_text("bad\x00fact\n", encoding="utf-8")
            commands = BotCommandProcessor("SuperBot", facts_path=path)
            self.assertTrue(commands.private_reply())
            self.assertNotIn("\x00", commands.private_reply())

    def test_command_before_own_join_is_deferred_and_early_events_survive(self):
        bot = BotClient()
        bot.send = Mock()
        bot.handle(message("001", "SuperBot", "Welcome"))
        bot.send.reset_mock()
        bot.handle(message("PART", "#hello", prefix="bob!u@host"))
        bot.handle(message("PRIVMSG", "#hello", "!slap bob", prefix="alice!u@host"))
        bot.send.assert_not_called()
        bot.handle(message("JOIN", "#hello", prefix="SuperBot!u@host"))
        bot.handle(message("353", "SuperBot", "=", "#hello", "SuperBot alice bob"))
        bot.handle(message("366", "SuperBot", "#hello", "End of names"))
        self.assertNotIn("bob", bot.state.members("#hello"))
        self.assertIn("alice slaps alice", bot.send.call_args.args[0].params[-1])

    def test_membership_commands_wait_for_complete_names_snapshot(self):
        for command in ("!slap bob", "!who"):
            for first_chunk in (False, True):
                with self.subTest(command=command, first_chunk=first_chunk):
                    bot = BotClient()
                    bot.send = Mock()
                    bot.handle(message("JOIN", "#hello", prefix="SuperBot!u@host"))
                    if first_chunk:
                        bot.handle(
                            message("353", "SuperBot", "=", "#hello", "SuperBot alice")
                        )
                    request = message(
                        "PRIVMSG", "#hello", command, prefix="alice!u@host"
                    )

                    bot.handle(request)

                    bot.send.assert_not_called()
                    self.assertIsNone(bot.queries._who)
                    bot.handle(
                        message("353", "SuperBot", "=", "#hello", "SuperBot alice bob")
                    )
                    bot.handle(message("366", "SuperBot", "#hello", "End of names"))
                    bot.send.assert_called_once()
                    reply = bot.send.call_args.args[0]
                    if command == "!who":
                        self.assertEqual(reply.command, "ISON")
                        self.assertEqual(
                            set(reply.params), {"SuperBot", "alice", "bob"}
                        )
                    else:
                        self.assertIn("alice slaps bob", reply.params[-1])

    def test_non_membership_commands_and_keepalive_work_during_names(self):
        bot = BotClient()
        bot.send = Mock()
        bot.handle(message("JOIN", "#hello", prefix="SuperBot!u@host"))
        bot.handle(message("PRIVMSG", "#hello", "!hello", prefix="alice!u@host"))
        self.assertEqual(bot.send.call_args.args[0].params[-1], "Hello, alice!")
        bot.handle(message("PING", "probe"))
        self.assertEqual(bot.send.call_args.args[0], message("PONG", "probe"))
        bot.handle(message("PRIVMSG", "SuperBot", "fact", prefix="alice!u@host"))
        self.assertEqual(bot.send.call_args.args[0].params[0], "alice")
        self.assertTrue(bot.send.call_args.args[0].params[-1])

    def test_unrelated_names_end_does_not_release_configured_channel_commands(self):
        bot = BotClient()
        bot.send = Mock()
        bot.handle(message("JOIN", "#hello", prefix="SuperBot!u@host"))
        bot.handle(message("PRIVMSG", "#hello", "!slap bob", prefix="alice!u@host"))
        bot.handle(message("366", "SuperBot", "#other", "End of names"))
        bot.send.assert_not_called()
        self.assertEqual(len(bot._pending_commands), 1)
        bot.handle(message("353", "SuperBot", "=", "#HELLO", "SuperBot alice bob"))
        bot.handle(message("366", "SuperBot", "#HELLO", "End of names"))
        self.assertIn("alice slaps bob", bot.send.call_args.args[0].params[-1])

    def test_pending_membership_command_queue_is_bounded_and_drained(self):
        bot = BotClient()
        bot.MAX_PENDING_COMMANDS = 2
        bot.send = Mock()
        bot.handle(message("JOIN", "#hello", prefix="SuperBot!u@host"))
        request = message("PRIVMSG", "#hello", "!slap bob", prefix="alice!u@host")
        for _ in range(3):
            bot.handle(request)
        self.assertEqual(len(bot._pending_commands), 2)
        bot.send.assert_called_once()
        self.assertIn("queue is full", bot.send.call_args.args[0].params[-1])

        bot.send.reset_mock()
        bot.handle(message("353", "SuperBot", "=", "#hello", "SuperBot alice bob"))
        bot.handle(message("366", "SuperBot", "#hello", "End of names"))
        self.assertEqual(len(bot._pending_commands), 0)
        self.assertEqual(bot.send.call_count, 2)
        self.assertTrue(
            all(
                "alice slaps bob" in call.args[0].params[-1]
                for call in bot.send.call_args_list
            )
        )

    def test_empty_facts_file_uses_fallback_reply(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "facts.txt"
            path.write_text("\n\n", encoding="utf-8")
            commands = BotCommandProcessor("SuperBot", facts_path=path)
            self.assertTrue(commands.private_reply())

    def test_events_before_first_names_reply_survive_initial_snapshot(self):
        bot = BotClient()
        bot.handle(message("JOIN", "#hello", prefix="SuperBot!u@host"))
        bot.handle(message("JOIN", "#hello", prefix="alice!u@host"))
        bot.handle(message("PART", "#hello", prefix="departed!u@host"))
        bot.handle(message("353", "SuperBot", "=", "#hello", "SuperBot departed"))
        bot.handle(message("366", "SuperBot", "#hello", "End of names"))
        self.assertEqual(bot.state.members("#hello"), {"SuperBot", "alice"})

    def test_commands(self):
        bot = BotCommandProcessor("SuperBot")
        self.assertEqual(
            bot.channel_command("!hello", "alice", {"alice", "SuperBot"}),
            "Hello, alice!",
        )
        self.assertIn(
            "bob",
            bot.channel_command("!slap bob", "alice", {"alice", "bob", "SuperBot"}),
        )
        self.assertIn(
            "bob",
            bot.channel_command("!slap BOB", "alice", {"alice", "bob", "SuperBot"}),
        )
        self.assertEqual(
            bot.channel_command("!slap SUPERBOT", "alice", {"alice", "SuperBot"}),
            "Choose a channel member other than yourself or the Bot.",
        )
        self.assertEqual(
            bot.channel_command("!slap", "alice", {"alice", "SuperBot"}),
            "No eligible channel member to slap.",
        )

    def test_state_updates(self):
        state = BotState()
        state.replace_names("#room", ["bot", "alice"])
        state.renamed("alice", "bob")
        state.left("#room", "bob")
        self.assertEqual(state.members("#room"), {"bot"})

    def test_state_updates_are_case_insensitive(self):
        state = BotState()
        state.replace_names("#Room", ["bot", "Alice"])
        state.renamed("ALICE", "BOB")
        state.left("#ROOM", "bob")
        self.assertEqual(state.members("#room"), {"bot"})

    def test_state_can_be_reset_after_reconnect(self):
        state = BotState()
        state.joined("#room", "alice")
        state.clear()
        self.assertEqual(state.members("#room"), set())

    def test_names_snapshot_can_span_multiple_replies(self):
        state = BotState()
        state.begin_names("#room")
        state.add_names("#room", ["alice", "bob"])
        state.add_names("#ROOM", ["carol"])
        state.finish_names("#room")
        self.assertEqual(state.members("#room"), {"alice", "bob", "carol"})

    def test_names_snapshot_preserves_interleaved_events(self):
        state = BotState()
        state.begin_names("#room")
        state.add_names("#room", ["bot", "alice", "bob"])
        state.left("#ROOM", "ALICE")
        state.renamed("bob", "robert")
        state.removed("carol")
        state.joined("#room", "dave")
        state.add_names("#room", ["alice", "bob", "carol"])
        state.finish_names("#room")
        self.assertEqual(state.members("#room"), {"bot", "robert", "dave"})
        state.finish_names("#room")
        self.assertEqual(state.members("#room"), {"bot", "robert", "dave"})

    def test_client_commits_names_only_at_end_of_snapshot(self):
        bot = BotClient()
        bot.handle(message("353", "SuperBot", "=", "#room", "alice bob"))
        self.assertEqual(bot.state.members("#room"), set())
        bot.handle(message("353", "SuperBot", "=", "#room", "carol"))
        bot.handle(message("366", "SuperBot", "#room", "End of /NAMES list."))
        self.assertEqual(bot.state.members("#room"), {"alice", "bob", "carol"})

    def test_malformed_server_events_are_ignored(self):
        bot = BotClient()
        bot.handle(message("JOIN"))
        bot.handle(message("391"))
        self.assertEqual(bot.state.members("#hello"), set())
        self.assertIsNone(bot.socket)

    def test_unexpected_runtime_errors_are_not_hidden_by_reconnect_loop(self):
        class BrokenBot(BotClient):
            def run_once(self):
                raise RuntimeError("unexpected bot bug")

        with self.assertLogs("bot.client", level="ERROR"):
            with self.assertRaisesRegex(RuntimeError, "unexpected bot bug"):
                BrokenBot(reconnect_delay=0).run()


if __name__ == "__main__":
    unittest.main()
