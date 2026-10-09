import unittest

from bot.client import BotClient
from bot.commands import BotCommandProcessor
from bot.state import BotState
from common.irc_message import message


class BotTests(unittest.TestCase):
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
