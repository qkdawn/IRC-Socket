import unittest

from bot.commands import BotCommandProcessor
from bot.state import BotState


class BotTests(unittest.TestCase):
    def test_commands(self):
        bot = BotCommandProcessor("SuperBot")
        self.assertEqual(bot.channel_command("!hello", "alice", {"alice", "SuperBot"}), "Hello, alice!")
        self.assertIn("bob", bot.channel_command("!slap bob", "alice", {"alice", "bob", "SuperBot"}))
        self.assertIn("bob", bot.channel_command("!slap BOB", "alice", {"alice", "bob", "SuperBot"}))
        self.assertEqual(bot.channel_command("!slap", "alice", {"alice", "SuperBot"}).split()[2], "alice")
        self.assertEqual(bot.channel_command("!time", "alice", {"alice"}), "__REQUEST_TIME__")

    def test_state_updates(self):
        state = BotState("bot")
        state.replace_names("#room", ["bot", "alice"])
        state.renamed("alice", "bob")
        state.left("#room", "bob")
        self.assertEqual(state.members("#room"), {"bot"})


if __name__ == "__main__":
    unittest.main()
