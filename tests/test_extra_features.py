"""Extra Bot commands use distinct IRC queries and bounded reply handling."""

import unittest
from unittest.mock import Mock, patch

from bot.client import BotClient
from bot.commands import BotCommandProcessor, CommandAction
from common.irc_message import message
from server.server import IRCServer
from server.handlers import IRCHandlers
from server.state import ClientState


class ExtraBotFeatureTests(unittest.TestCase):
    def setUp(self):
        self.bot = BotClient()
        self.bot.send = Mock()

    def request(self, text):
        self.bot.handle(message("PRIVMSG", "#hello", text, prefix="alice!u@host"))

    def replies(self):
        return [
            call.args[0].params[-1]
            for call in self.bot.send.call_args_list
            if call.args[0].command == "PRIVMSG"
        ]

    def test_decisions_have_distinct_actions_and_reject_arguments(self):
        processor = BotCommandProcessor("SuperBot")
        for text, expected in (
            ("!channels", CommandAction.REQUEST_CHANNELS),
            ("!network", CommandAction.REQUEST_NETWORK),
        ):
            with self.subTest(text=text):
                self.assertIs(
                    processor.channel_command(text, "alice", set()), expected
                )
                self.assertEqual(
                    processor.channel_command(text + " extra", "alice", set()),
                    "Usage: " + text,
                )

    def test_channels_sends_list_and_waits_for_terminator(self):
        self.request("!channels")
        self.bot.send.assert_called_once_with(message("LIST"))
        for channel, count in (("#hello", "2"), ("#other", "5")):
            self.bot.handle(message("322", "SuperBot", channel, count, "Topic"))
        self.assertEqual(self.replies(), [])
        self.bot.handle(message("323", "SuperBot", "End of LIST"))
        self.assertEqual(
            self.replies(),
            [
                "CHANNEL: #hello (2 users)",
                "CHANNEL: #other (5 users)",
                "CHANNELS complete: 2 channels (showing 2)",
            ],
        )
        self.assertEqual(self.bot.queries._extra_queries, {})

    def test_empty_list_is_a_successful_result(self):
        self.request("!channels")
        self.bot.handle(message("323", "SuperBot", "End of LIST"))
        self.assertEqual(self.replies(), ["CHANNELS complete: 0 channels (showing 0)"])

    def test_large_list_bounds_storage_and_output(self):
        self.request("!channels")
        for index in range(1000):
            self.bot.handle(message("322", "SuperBot", f"#room{index}", "2", ""))
        self.assertEqual(len(self.bot.queries._listed_channels), 10)
        self.bot.handle(message("323", "SuperBot", "End of LIST"))
        self.assertEqual(len(self.replies()), 11)
        self.assertEqual(self.replies()[-1], "CHANNELS complete: 1000 channels (showing 10)")
        self.assertEqual(self.bot.queries._listed_channels, [])

    def test_unsolicited_and_misaddressed_replies_do_not_broadcast(self):
        replies = [
            message("251", "SuperBot", "Registration statistics"),
            message("322", "SuperBot", "#hello", "2", ""),
            message("323", "SuperBot", "End of LIST"),
        ]
        for reply in replies:
            self.bot.handle(reply)
        self.bot.send.assert_not_called()
        self.request("!channels")
        self.request("!network")
        self.bot.send.reset_mock()
        for reply in replies:
            self.bot.handle(message(reply.command, "other", *reply.params[1:]))
        self.bot.send.assert_not_called()
        self.assertEqual(set(self.bot.queries._extra_queries), {"LIST", "LUSERS"})

    def test_invalid_list_entries_are_ignored(self):
        self.request("!channels")
        for params in (
            ("SuperBot",),
            ("SuperBot", "#hello", "2"),
            ("SuperBot", "bad channel", "2", ""),
            ("SuperBot", "#hello", "-1", ""),
            ("SuperBot", "#hello", "x", ""),
            ("SuperBot", "#hello", "9" * 100, ""),
        ):
            with self.subTest(params=params):
                self.bot.handle(message("322", *params))
        self.assertEqual(self.bot.queries._listed_count, 0)

    def test_network_uses_lusers_without_waiting_for_channel_roster(self):
        self.bot.state.begin_names("#hello")
        self.request("!network")
        self.bot.send.assert_called_once_with(message("LUSERS"))
        self.bot.handle(message("251", "superbot", "There are 3 users on 1 server"))
        self.assertEqual(self.replies(), ["NETWORK: There are 3 users on 1 server"])

    def test_queries_can_interleave_without_mixing_replies(self):
        self.request("!channels")
        self.request("!network")
        self.bot.handle(message("322", "SuperBot", "#hello", "2", ""))
        self.bot.handle(message("251", "SuperBot", "There are 3 users"))
        self.bot.handle(message("323", "SuperBot", "End of LIST"))
        self.assertEqual(
            self.replies(),
            [
                "NETWORK: There are 3 users",
                "CHANNEL: #hello (2 users)",
                "CHANNELS complete: 1 channels (showing 1)",
            ],
        )

    def test_repeated_query_reports_busy_and_does_not_reset_deadline(self):
        with patch("bot.client.time.monotonic", return_value=100):
            self.request("!channels")
        self.request("!channels")
        self.assertEqual(self.bot.queries._extra_queries["LIST"][1], 100)
        self.assertEqual(
            [call.args[0].command for call in self.bot.send.call_args_list],
            ["LIST", "PRIVMSG"],
        )
        self.assertIn("already in progress", self.replies()[-1])

    def test_errors_clear_query_and_partial_results_for_retry(self):
        for command, query in (("!channels", "LIST"), ("!network", "LUSERS")):
            for numeric in ("263", "421", "461"):
                with self.subTest(command=command, numeric=numeric):
                    self.bot.send.reset_mock()
                    self.request(command)
                    self.bot.handle(message("322", "SuperBot", "#stale", "2", ""))
                    self.bot.handle(message(numeric, "SuperBot", query, "Rejected"))
                    self.assertEqual(self.replies(), [f"{query} unavailable: server rejected {query}."])
                    self.assertEqual(self.bot.queries._listed_channels, [])
                    self.assertEqual(self.bot.queries._extra_queries, {})
                    self.request(command)
                    self.assertEqual(self.bot.send.call_args.args[0], message(query))
                    self.bot.queries.reset()

    def test_queries_have_deadlines_even_if_ping_is_answered(self):
        self.bot._registered = True
        for command, query in (("!channels", "LIST"), ("!network", "LUSERS")):
            with self.subTest(command=command):
                with patch("bot.client.time.monotonic", return_value=100):
                    self.request(command)
                self.bot.handle(message("PING", "healthy"))
                with patch("bot.client.time.monotonic", return_value=130):
                    with self.assertRaisesRegex(TimeoutError, query):
                        self.bot._check_timeouts(100, None)
                self.assertEqual(self.bot.queries._extra_queries, {})

    def test_reconnect_discards_pending_queries_and_partial_list(self):
        self.request("!channels")
        self.request("!network")
        self.bot.handle(message("322", "SuperBot", "#stale", "2", ""))
        self.bot.stopping.set()
        with patch("bot.client.socket.socket", return_value=Mock()):
            self.bot.run_once()
        self.bot.close()
        self.assertEqual(self.bot.queries._extra_queries, {})
        self.assertEqual(self.bot.queries._listed_channels, [])
        self.assertEqual(self.bot.queries._listed_count, 0)

    def test_long_network_reply_is_split_without_losing_unicode(self):
        self.request("!network")
        text = "\u754c\U0001f642 " * 60
        self.bot.handle(message("251", "SuperBot", text))
        self.assertEqual("".join(self.replies()), "NETWORK: " + text)
        for call in self.bot.send.call_args_list:
            reply = call.args[0]
            self.assertLessEqual(len(reply.to_bounded_bytes()), 512)


class ExtraServerCommandTests(unittest.TestCase):
    def setUp(self):
        self.server = IRCServer()
        self.client = ClientState(Mock(), ("::1", 1), nick="alice", username="user")
        self.server.state.add_client(self.client)

    def test_list_returns_sorted_channel_counts_and_end_marker(self):
        self.server.state.join(self.client, "#Zoo")
        self.server.state.join(self.client, "#alpha")
        self.server.handlers.handle(self.client, message("LIST"))
        replies = [call.args[0] for call in self.client.connection.send_reply.call_args_list]
        self.assertEqual([reply.command for reply in replies], ["322", "322", "323"])
        self.assertEqual([reply.params[1] for reply in replies[:-1]], ["#alpha", "#zoo"])
        self.assertTrue(all(reply.params[2] == "1" for reply in replies[:-1]))

    def test_list_filter_is_case_insensitive_and_omits_absent_channels(self):
        self.server.state.join(self.client, "#room")
        self.server.state.join(self.client, "#other")
        self.server.handlers.handle(self.client, message("LIST", "#ROOM,#missing"))
        replies = [call.args[0] for call in self.client.connection.send_reply.call_args_list]
        self.assertEqual([reply.command for reply in replies], ["322", "323"])
        self.assertEqual(replies[0].params[1], "#room")

    def test_empty_list_terminates(self):
        self.server.handlers.handle(self.client, message("LIST"))
        self.client.connection.send_reply.assert_called_once()
        self.assertEqual(self.client.connection.send_reply.call_args.args[0].command, "323")

    def test_handlers_need_only_state_operations_not_storage_or_locks(self):
        state = Mock(spec=["list_channels", "registered_user_count", "acknowledge_ping"])
        state.list_channels.return_value = [("#room", 2)]
        state.registered_user_count.return_value = 3
        server = Mock(state=state, server_name="irc.test")
        handlers = IRCHandlers(server)
        handlers.cmd_list(self.client, ("#ROOM,#missing",))
        handlers.cmd_lusers(self.client, ())
        handlers.cmd_pong(self.client, ("irc.test",))
        state.list_channels.assert_called_once_with(["#ROOM", "#missing"])
        state.registered_user_count.assert_called_once_with()
        state.acknowledge_ping.assert_called_once_with(self.client)
        self.assertEqual(
            [
                call.args[1].command for call in server.method_calls
                if call[0] in {"send", "send_reply"}
            ],
            ["322", "323", "251"],
        )

    def test_lusers_counts_only_registered_clients(self):
        self.server.state.add_client(ClientState(Mock(), ("::1", 2), nick="pending"))
        self.server.handlers.handle(self.client, message("LUSERS"))
        reply = self.client.connection.send.call_args.args[0]
        self.assertEqual(reply.command, "251")
        self.assertEqual(reply.params[-1], "There are 1 users and 0 services on 1 server")

    def test_extra_queries_require_registration(self):
        pending = ClientState(Mock(), ("::1", 2), nick="pending")
        for query in ("LIST", "LUSERS"):
            with self.subTest(query=query):
                self.server.handlers.handle(pending, message(query))
                self.assertEqual(pending.connection.send.call_args.args[0].command, "451")

    def test_replies_fit_maximum_supported_prefix_fields(self):
        self.server.server_name = "s" * 63
        self.client.nick = "n" * 30
        self.server.state.join(self.client, "#" + "c" * 49)
        for query in ("LIST", "LUSERS"):
            self.server.handlers.handle(self.client, message(query))
        for call in self.client.connection.method_calls:
            if call[0] in {"send", "send_reply"}:
                self.assertLessEqual(len(call.args[0].to_bounded_bytes()), 512)
