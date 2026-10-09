import unittest
from unittest.mock import Mock
from unittest.mock import patch
from datetime import datetime, timezone, timedelta

from bot.client import BotClient
from bot.commands import BotCommandProcessor, CommandAction
from common.irc_message import message
from server.server import IRCServer
from server.state import ClientState


class RubricAlignmentTests(unittest.TestCase):
    def test_time_replies_in_channel_with_local_timezone(self):
        bot = BotClient()
        bot.send = Mock()
        now = datetime(2026, 10, 8, 19, 0, tzinfo=timezone(timedelta(hours=8)))
        with patch('bot.commands.datetime') as clock:
            clock.now.return_value.astimezone.return_value = now
            bot.handle(message('PRIVMSG', '#hello', '!time', prefix='alice!u@host'))
        self.assertEqual(bot.send.call_args.args[0], message('PRIVMSG', '#hello', 'Bot time: 2026-10-08 19:00:00+08:00'))

    def test_slap_rejects_self_and_bot_but_preserves_absent_target_fallback(self):
        bot = BotCommandProcessor('SuperBot')
        for target in ['alice', 'ALICE', 'SuperBot']:
            reply = bot.channel_command('!slap ' + target, 'alice', {'alice', 'bob', 'SuperBot'})
            self.assertNotIn(' slaps ', reply)
        self.assertIn('alice slaps alice', bot.channel_command('!slap absent', 'alice', {'alice', 'bob', 'SuperBot'}))
        self.assertIn('alice slaps bob', bot.channel_command('!slap', 'alice', {'alice', 'bob', 'SuperBot'}))

    def test_invalid_nickname_error_serializes_and_registration_can_continue(self):
        server = IRCServer()
        client = ClientState(Mock(), ('::1', 1))
        for nickname in ['bad nick', ':bad', 'x' * 490]:
            server.handlers.handle(client, message('NICK', nickname))
            reply = client.connection.send.call_args.args[0]
            self.assertEqual(reply.command, '432')
            self.assertLessEqual(len(reply.to_bytes()), 512)
        server.handlers.handle(client, message('NICK', 'alice'))
        server.handlers.handle(client, message('USER', 'alice', '0', '*', 'Alice'))
        self.assertTrue(client.registered)

    def test_empty_private_and_channel_messages_get_412(self):
        server = IRCServer()
        client = ClientState(Mock(), ('::1', 1), nick='alice', username='alice')
        for target in ['bob', '#hello']:
            server.handlers.cmd_privmsg(client, (target, ''))
            reply = client.connection.send.call_args.args[0]
            self.assertEqual(reply.command, '412')
            reply.to_bytes()

    def test_idle_probe_after_one_minute_and_cleanup_without_pong(self):
        server = IRCServer()
        connection = Mock()
        client = ClientState(connection, ('::1', 1), last_activity=0)
        server.state.add_client(client)
        server.state.set_nick(client, 'SuperBot')
        server.state.set_nick(client, 'alice')
        server.state.join(client, '#room')
        server.monotonic = lambda: 29
        server._check_idle_clients()
        connection.send.assert_not_called()
        server.monotonic = lambda: 30
        server._check_idle_clients()
        self.assertEqual(connection.send.call_args.args[0].command, 'PING')
        server.monotonic = lambda: 61
        server._check_idle_clients()
        self.assertIsNone(server.state.find_nick('alice'))
        self.assertEqual(server.state.channel_members('#room'), [])
        connection.close.assert_called_once()

    def test_pong_keeps_idle_client_connected(self):
        server = IRCServer()
        client = ClientState(Mock(), ('::1', 1), last_activity=0)
        server.state.add_client(client)
        server.monotonic = lambda: 30
        server._check_idle_clients()
        server.handlers.handle(client, message('PONG', 'coursework.local'))
        server.monotonic = lambda: 61
        server._check_idle_clients()
        self.assertIn(client, server.state.clients)
        client.connection.close.assert_not_called()

    def test_bot_recovers_from_nickname_collision_before_join(self):
        bot = BotClient(nickname='SuperBot')
        bot.send = Mock()
        bot.handle(message('433', '*', 'SuperBot', 'Nickname in use'))
        self.assertEqual(bot.send.call_args.args[0], message('NICK', 'SuperBot_1'))
        bot.handle(message('001', 'SuperBot_1', 'Welcome'))
        self.assertEqual(bot.commands.nickname, 'SuperBot_1')
        self.assertEqual(bot.send.call_args.args[0], message('JOIN', '#hello'))

    def test_who_roundtrip_from_server_to_bot(self):
        self.assertIs(BotCommandProcessor('SuperBot').channel_command('!who', 'alice', set()), CommandAction.REQUEST_WHO)
        server = IRCServer()
        connection = Mock()
        client = ClientState(connection, ('::1', 1), nick='SuperBot', username='bot', realname='Bot')
        server.state.add_client(client)
        server.state.set_nick(client, 'SuperBot')
        server.state.join(client, '#hello')
        bot = BotClient()
        bot.send = Mock()
        bot.state.replace_names('#hello', ['SuperBot'])
        bot.handle(message('PRIVMSG', '#hello', '!who', prefix='alice!u@host'))
        self.assertEqual(bot.send.call_args.args[0], message('ISON', 'SuperBot'))
        server.handlers.cmd_ison(client, ('SuperBot',))
        for call in connection.send.call_args_list:
            bot.handle(call.args[0])
        replies = [call.args[0].params[-1] for call in bot.send.call_args_list if call.args[0].command == 'PRIVMSG']
        self.assertEqual(replies, ['WHO member: SuperBot', 'WHO complete: 1 members'])


if __name__ == '__main__':
    unittest.main()
