import unittest

from bot.client import BotClient
from bot.commands import BotCommandProcessor, CommandAction
from bot.state import BotState
from common.irc_message import message


class BotTests(unittest.TestCase):
    def test_commands(self):
        bot = BotCommandProcessor("SuperBot")
        self.assertEqual(bot.channel_command("!hello", "alice", {"alice", "SuperBot"}), "Hello, alice!")
        self.assertIn("bob", bot.channel_command("!slap bob", "alice", {"alice", "bob", "SuperBot"}))
        self.assertIn("bob", bot.channel_command("!slap BOB", "alice", {"alice", "bob", "SuperBot"}))
        self.assertIn(
            "alice",
            bot.channel_command("!slap SUPERBOT", "alice", {"alice", "SuperBot"}),
        )
        self.assertEqual(bot.channel_command("!slap", "alice", {"alice", "SuperBot"}).split()[2], "alice")
        self.assertIs(
            bot.channel_command("!time", "alice", {"alice"}),
            CommandAction.REQUEST_TIME,
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

        with self.assertRaisesRegex(RuntimeError, "unexpected bot bug"):
            BrokenBot(reconnect_delay=0).run()


if __name__ == "__main__":
    unittest.main()
