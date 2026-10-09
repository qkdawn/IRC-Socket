import unittest
from unittest.mock import Mock

from bot.client import BotClient
from bot.commands import BotCommandProcessor
from bot.state import BotState
from common.irc_message import IRCMessage, IRCParseError, message
from common.protocol import irc_casefold
from server.client_session import ClientSession
from server.errors import NicknameInUseError
from server.server import IRCServer
from server.state import ClientState


class ReviewFixTests(unittest.TestCase):
    def test_part_and_quit_reasons_fit_wire_limit_without_breaking_utf8(self):
        for command in ("PART", "QUIT"):
            for reason in ("x" * 497, "\u754c" * 160 + "x" * 15):
                with self.subTest(command=command, reason=reason[:1]):
                    server = IRCServer()
                    sender_socket, peer_socket = Mock(), Mock()
                    sender = ClientSession(server, sender_socket, ("fc00:1337::19", 1))
                    peer = ClientSession(server, peer_socket, ("fc00:1337::19", 2))
                    for session, nick in ((sender, "alice"), (peer, "bob")):
                        server.state.add_client(session.client)
                        server.handlers.handle(session.client, message("NICK", nick))
                        server.handlers.handle(session.client, message("USER", "u", "0", "*", nick))
                        server.handlers.handle(session.client, message("JOIN", "#hello"))
                    peer_socket.sendall.reset_mock()
                    params = ("#hello", reason) if command == "PART" else (reason,)
                    incoming = message(command, *params)
                    self.assertLessEqual(len(incoming.to_bytes()), 512)
                    server.handlers.handle(sender.client, incoming)
                    payload = peer_socket.sendall.call_args.args[0]
                    self.assertLessEqual(len(payload), 512)
                    outgoing = IRCMessage.parse(payload.decode("utf-8"))
                    self.assertEqual(outgoing.command, command)
                    self.assertEqual(outgoing.prefix, "alice!u@fc00:1337::19")
                    self.assertTrue(reason.startswith(outgoing.params[-1]))
                    if command == "PART":
                        self.assertEqual(outgoing.params[0], "#hello")
                    self.assertNotIn(sender.client, server.state.channel_members("#hello"))

    def test_overlong_chat_is_not_silently_truncated_at_socket_boundary(self):
        session = ClientSession(IRCServer(), Mock(), ("::1", 1))
        with self.assertRaises(IRCParseError):
            session.send(message("PRIVMSG", "bob", "x" * 510))
        session.socket.sendall.assert_not_called()

    def test_overlong_routing_fields_cannot_be_truncated_as_reason(self):
        with self.assertRaises(IRCParseError):
            message("QUIT", "bye", prefix="n" * 510).to_bounded_bytes(truncate_trailing=True)

    def test_nick_change_without_channels_is_confirmed_to_client(self):
        server = IRCServer()
        client = ClientState(Mock(), ("::1", 1))
        server.state.add_client(client)
        server.handlers.handle(client, message("NICK", "alice"))
        server.handlers.handle(client, message("USER", "u", "0", "*", "Alice"))
        client.connection.send.reset_mock()
        server.handlers.handle(client, message("NICK", "bob"))
        client.connection.send.assert_called_once_with(message("NICK", "bob", prefix="alice!u@::1"))
        self.assertIs(server.state.find_nick("bob"), client)
        self.assertIsNone(server.state.find_nick("alice"))

    def test_nick_change_is_sent_once_to_self_and_shared_peer(self):
        server = IRCServer()
        clients = [ClientState(Mock(), ("::1", index)) for index in (1, 2)]
        for client, nick in zip(clients, ("alice", "bob")):
            server.state.add_client(client)
            server.state.set_nick(client, nick)
            server.state.set_user(client, "u", nick)
            for channel in ("#one", "#two"):
                server.state.join(client, channel)
        server.handlers.handle(clients[0], message("NICK", "carol"))
        for client in clients:
            client.connection.send.assert_called_once()

    def test_bot_own_rename_updates_private_routing_and_slap_exclusions(self):
        bot = BotClient(nickname="[Bot]")
        bot.send = Mock()
        bot.state.replace_names("#hello", ["[Bot]", "alice"])
        bot.handle(message("NICK", "NewBot", prefix="{bot}!u@host"))
        self.assertEqual(bot.nickname, "NewBot")
        self.assertEqual(bot.commands.nickname, "NewBot")
        bot.handle(message("PRIVMSG", "NEWBOT", "hello", prefix="alice!u@host"))
        self.assertEqual(bot.send.call_args.args[0].params[0], "alice")
        self.assertEqual(bot.commands.channel_command("!slap", "alice", bot.state.members("#hello")),
                         "No eligible channel member to slap.")

    def test_rfc1459_case_mapping_and_nickname_collision(self):
        self.assertEqual(irc_casefold("[Nick]\\^"), irc_casefold("{nick}|~"))
        server = IRCServer()
        a, b = [ClientState(Mock(), ("::1", index)) for index in (1, 2)]
        server.state.set_nick(a, "[Nick]")
        with self.assertRaises(NicknameInUseError):
            server.state.set_nick(b, "{nick}")
        self.assertIs(server.state.direct_target("{NICK}"), a)
        server.state.join(a, "#[Room]")
        self.assertEqual(server.state.channel_members("#{room}"), [a])
        self.assertTrue(server.state.part(a, "#{ROOM}")[0])
        server.state.remove(a)
        self.assertIsNone(server.state.find_nick("{nick}"))

    def test_bot_state_and_commands_use_irc_equivalent_names(self):
        state = BotState()
        state.replace_names("#[room]", ["[Bot]", "[Alice]", "{alice}", "bob"])
        self.assertEqual(len(state.members("#{ROOM}")), 3)
        command = BotCommandProcessor("[Bot]")
        self.assertIn("Choose", command.channel_command("!slap {bot}", "{alice}", state.members("#[room]")))
        self.assertIn("slaps bob", command.channel_command("!slap", "{alice}", state.members("#[room]")))
        state.renamed("{ALICE}", "carol")
        state.left("#{room}", "CAROL")
        state.removed("{bot}")
        self.assertEqual(state.members("#[room]"), {"bob"})

    def test_bot_receives_commands_on_irc_equivalent_channel(self):
        bot = BotClient(channel="#[room]")
        bot.send = Mock()
        bot.handle(message("PRIVMSG", "#{ROOM}", "!hello", prefix="alice!u@host"))
        bot.send.assert_called_once_with(message("PRIVMSG", "#{ROOM}", "Hello, alice!"))


if __name__ == "__main__":
    unittest.main()
