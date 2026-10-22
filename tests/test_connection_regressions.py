import socket
import threading
import unittest
from unittest.mock import Mock, patch

from bot.client import BotClient
from bot.cli import main as bot_main
from common.irc_message import IRCMessage, message
from server.server import IRCServer
from server.cli import main as server_main
from server.state import ClientState
from server.client_session import ClientSession
from tests.helpers import start_writer


class ConnectionRegressionTests(unittest.TestCase):
    def setUp(self):
        self.server = IRCServer()
        self.requester = self.add_client("q" * 30)

    def add_client(self, nick, *, registered=True):
        connection = Mock()
        connection.send.side_effect = lambda reply, **_kwargs: reply.to_bounded_bytes()
        client = ClientState(connection, ("::1", 1))
        self.server.state.add_client(client)
        self.server.state.set_nick(client, nick)
        if registered:
            self.server.state.set_user(client, "user", "Real Name")
        return client

    def test_ison_overflow_returns_one_error_instead_of_partial_presence(self):
        self.server.server_name = "s" * 63
        names = [f"n{index:029d}" for index in range(15)]
        for nick in names:
            self.add_client(nick)
        request = message("ISON", " ".join(names))
        self.assertEqual(len(request.to_bytes()), 472)
        full_reply = message(
            "303", self.requester.nick, " ".join(names), prefix=self.server.server_name
        )
        self.assertEqual(len(full_reply.to_bytes()), 567)

        self.server.handlers.handle(self.requester, request)

        self.requester.connection.send.assert_called_once()
        reply = self.requester.connection.send.call_args.args[0]
        self.assertEqual(reply.command, "417")
        self.assertEqual(reply.params[1], "ISON")
        self.assertIn("smaller batches", reply.params[-1])
        self.assertLessEqual(len(reply.to_bounded_bytes()), 512)
        self.server.handlers.handle(self.requester, message("PING", "still-here"))
        self.assertEqual(
            self.requester.connection.send.call_args.args[0].command, "PONG"
        )

    def test_ison_reply_accepts_512_bytes_and_rejects_513_bytes(self):
        self.server.server_name = "s" * 63
        names = [f"n{index:029d}" for index in range(13)]
        for nick in [*names, "short6", "longer7"]:
            self.add_client(nick)
        for last, size, command in (("short6", 512, "303"), ("longer7", 513, "417")):
            with self.subTest(size=size):
                selected = [*names, last]
                full_reply = message(
                    "303", self.requester.nick, " ".join(selected), prefix="s" * 63
                )
                self.assertEqual(len(full_reply.to_bytes()), size)
                self.requester.connection.send.reset_mock()
                self.server.handlers.cmd_ison(self.requester, (" ".join(selected),))
                self.requester.connection.send.assert_called_once()
                reply = self.requester.connection.send.call_args.args[0]
                self.assertEqual(reply.command, command)
                self.assertLessEqual(len(reply.to_bounded_bytes()), 512)
                if command == "303":
                    self.assertEqual(reply.params[-1].split(), selected)

    def test_ison_deduplicates_canonical_nicks_and_returns_empty_reply(self):
        self.add_client("Alice")
        self.server.handlers.cmd_ison(self.requester, ("Alice alice ALICE absent",))
        reply = self.requester.connection.send.call_args.args[0]
        self.assertEqual(reply.params[-1], "Alice")
        self.server.handlers.cmd_ison(self.requester, ("absent",))
        reply = self.requester.connection.send.call_args.args[0]
        self.assertEqual(reply.params[-1], "")

    def test_maximum_ping_token_is_preserved_without_disconnect(self):
        for token in ("x" * 505, "x " * 251 + "xx"):
            with self.subTest(length=len(token)):
                request = message("PING", token)
                self.assertLessEqual(len(request.to_bytes()), 512)
                self.server.handlers.handle(self.requester, request)
                reply = self.requester.connection.send.call_args.args[0]
                self.assertEqual(reply.command, "PONG")
                self.assertEqual(reply.params[-1], token)
                self.assertLessEqual(len(reply.to_bounded_bytes()), 512)

    def test_server_configuration_rejects_unsafe_or_overlong_prefix(self):
        for name in ("s" * 64, "bad name", ":bad", "bad\x00name", ""):
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    IRCServer(server_name=name)
        self.assertEqual(IRCServer(server_name="s" * 63).server_name, "s" * 63)

    def test_invalid_ports_are_reported_by_cli_before_socket_creation(self):
        for main in (bot_main, server_main):
            for port in (-1, 65536):
                with self.subTest(program=main.__module__, port=port):
                    with patch("socket.socket") as create_socket, patch("sys.stderr"):
                        with self.assertRaises(SystemExit) as result:
                            main(["--port", str(port)])
                    self.assertEqual(result.exception.code, 2)
                    create_socket.assert_not_called()

    def test_bot_rejects_zero_destination_port_but_server_can_bind_ephemeral_port(self):
        with self.assertRaises(ValueError):
            BotClient(port=0)
        self.assertEqual(IRCServer(port=0).port, 0)

    def test_failed_multi_join_cannot_restore_disconnected_client(self):
        sock = Mock()
        session = ClientSession(self.server, sock, ("::1", 2))
        self.server.state.add_client(session.client)
        self.server.state.set_nick(session.client, "leaving")
        self.server.state.set_user(session.client, "user", "Real")
        sock.sendall.side_effect = OSError("connection lost during JOIN")
        worker = start_writer(self, session)
        self.server.handlers.handle(session.client, message("JOIN", "#first,#second"))
        self.assertTrue(session.closed.wait(2))
        worker.join(2)
        self.assertNotIn(session.client, self.server.state.clients)
        self.assertIsNone(self.server.state.find_nick("leaving"))
        self.assertEqual(self.server.state.channel_members("#second"), [])

    def test_removed_client_cannot_write_state_after_cleanup(self):
        self.server.state.remove(self.requester)
        for operation in (
            lambda: self.server.state.set_nick(self.requester, "ghost"),
            lambda: self.server.state.set_user(self.requester, "ghost", "Ghost"),
            lambda: self.server.state.join(self.requester, "#ghost"),
        ):
            with self.subTest(operation=operation):
                with self.assertRaises(ConnectionError):
                    operation()
        self.assertIsNone(self.server.state.find_nick("ghost"))
        self.assertEqual(self.server.state.channel_members("#ghost"), [])

    def test_server_registration_deadline_ignores_keepalives_and_nickname_changes(self):
        now = [100.0]
        with patch.object(self.server, "monotonic", side_effect=lambda: now[0]):
            session = ClientSession(self.server, Mock(), ("::1", 2))
            client = session.client
            self.server.state.add_client(client)
            self.server.handlers.handle(client, message("NICK", "ReservedNick"))
            now[0] = 120.0
            for incoming in (
                message("PING", "keep-alive"),
                message("PONG", self.server.server_name),
                message("NICK", "RenamedReserved"),
            ):
                self.server.handlers.handle(client, incoming)
            self.server._check_idle_clients()
            self.assertFalse(client.disconnected)
            now[0] = 130.0
            self.server._check_idle_clients()
            self.assertTrue(client.disconnected)
            self.assertNotIn(client, self.server.state.clients)
            self.assertIsNone(self.server.state.find_nick("RenamedReserved"))
            session.socket.close.assert_called_once()
            self.server.state.set_nick(self.requester, "RenamedReserved")
            self.assertIs(self.server.state.find_nick("RenamedReserved"), self.requester)
            for elapsed in range(40, 301, 20):
                now[0] = 100.0 + elapsed
                self.server._check_idle_clients()
            session.socket.close.assert_called_once()

    def test_server_registration_deadline_covers_silent_and_user_only_connections(self):
        for user_only in (False, True):
            with self.subTest(user_only=user_only):
                now = [100.0]
                with patch.object(self.server, "monotonic", side_effect=lambda: now[0]):
                    session = ClientSession(self.server, Mock(), ("::1", 2))
                    client = session.client
                    self.server.state.add_client(client)
                    if user_only:
                        self.server.handlers.handle(
                            client, message("USER", "user", "0", "*", "Real")
                        )
                    now[0] = 129.999
                    self.server._check_idle_clients()
                    self.assertFalse(client.disconnected)
                    now[0] = 130.0
                    self.server._check_idle_clients()
                    self.assertTrue(client.disconnected)
                    self.assertNotIn(client, self.server.state.clients)
                    session.socket.close.assert_called_once()

    def test_completed_registration_is_exempt_from_registration_deadline(self):
        now = [100.0]
        with patch.object(self.server, "monotonic", side_effect=lambda: now[0]):
            session = ClientSession(self.server, Mock(), ("::1", 2))
            client = session.client
            self.server.state.add_client(client)
            self.server.handlers.handle(client, message("NICK", "Registered"))
            now[0] = 129.999
            self.server.handlers.handle(client, message("USER", "u", "0", "*", "Real"))
            for elapsed in range(40, 301, 20):
                now[0] = 100.0 + elapsed
                self.server.handlers.handle(client, message("PING", "keep-alive"))
                self.server._check_idle_clients()
            self.assertTrue(client.registered)
            self.assertFalse(client.disconnected)
            session.socket.close.assert_not_called()

    def test_join_racing_disconnect_cannot_leave_membership_behind(self):
        client = self.add_client("racing")
        barrier = threading.Barrier(2)
        errors = []

        def join():
            barrier.wait(timeout=2)
            try:
                self.server.state.join(client, "#racing")
            except ConnectionError:
                pass
            except Exception as exc:
                errors.append(exc)

        worker = threading.Thread(target=join)
        worker.start()
        barrier.wait(timeout=2)
        self.server.disconnect(client)
        worker.join(timeout=2)
        self.assertFalse(worker.is_alive())
        self.assertEqual(errors, [])
        self.assertIsNone(self.server.state.find_nick("racing"))
        self.assertEqual(self.server.state.channel_members("#racing"), [])

    def test_disconnect_during_join_delivery_cannot_resurrect_bot_membership(self):
        session = ClientSession(self.server, Mock(), ("::1", 2))
        observer = session.client
        self.server.state.add_client(observer)
        self.server.state.set_nick(observer, "SuperBot")
        self.server.state.set_user(observer, "u", "Bot")
        joining = self.add_client("bob")
        self.server.state.join(observer, "#hello")
        bot = BotClient()
        bot.state.replace_names("#hello", ["SuperBot"])
        paused = threading.Event()
        resume = threading.Event()
        delivered = threading.Event()
        received = []

        def receive(payload):
            incoming = IRCMessage.parse(payload.decode("utf-8"))
            if incoming.command == "JOIN":
                paused.set()
                if not resume.wait(2):
                    raise TimeoutError("JOIN delivery was not resumed")
            bot.handle(incoming)
            received.append(incoming.command)
            if incoming.command == "QUIT":
                delivered.set()

        session.socket.sendall.side_effect = receive
        start_writer(self, session)
        self.server.handlers.handle(joining, message("JOIN", "#hello"))
        try:
            self.assertTrue(paused.wait(2))
            self.server.disconnect(joining, "Ping timeout")
            self.assertTrue(joining.disconnected)
            joining.connection.close.assert_called_once()
        finally:
            resume.set()
        self.assertTrue(delivered.wait(2))
        self.assertEqual(bot.state.members("#hello"), {"SuperBot"})
        self.assertEqual(self.server.state.channel_members("#hello"), [observer])
        self.assertEqual(
            received,
            ["JOIN", "QUIT"],
        )

    def test_rename_disconnect_keeps_the_old_name_from_becoming_a_ghost(self):
        observer = self.add_client("SuperBot")
        renaming = self.add_client("bob")
        for client in (observer, renaming):
            self.server.state.join(client, "#hello")
        bot = BotClient()
        bot.state.replace_names("#hello", ["SuperBot", "bob"])
        observer.connection.send.side_effect = bot.handle
        paused, resume = threading.Event(), threading.Event()
        original_set_nick = self.server.state.set_nick
        errors = []

        def set_nick(client, nickname):
            old = original_set_nick(client, nickname)
            paused.set()
            if not resume.wait(2):
                raise TimeoutError("rename was not resumed")
            return old

        def rename():
            try:
                self.server.handlers.handle(renaming, message("NICK", "robert"))
            except Exception as exc:
                errors.append(exc)

        def disconnect():
            try:
                self.server.disconnect(renaming, "Ping timeout")
            except Exception as exc:
                errors.append(exc)

        with patch.object(self.server.state, "set_nick", side_effect=set_nick):
            worker = threading.Thread(target=rename)
            worker.start()
            try:
                self.assertTrue(paused.wait(2))
                closer = threading.Thread(target=disconnect)
                closer.start()
                # Synchronize the contender without relying on a scheduling delay.
                resume.set()
                closer.join(2)
            finally:
                resume.set()
                worker.join(2)
        self.assertFalse(worker.is_alive())
        self.assertFalse(closer.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(bot.state.members("#hello"), {"SuperBot"})
        self.assertEqual(
            [call.args[0].command for call in observer.connection.send.call_args_list],
            ["NICK", "QUIT"],
        )

    def test_session_closed_before_read_loop_still_cleans_state(self):
        sock = Mock()
        session = ClientSession(self.server, sock, ("::1", 2))
        self.server.state.add_client(session.client)
        self.server.state.set_nick(session.client, "closing")
        sock.settimeout.side_effect = OSError("socket already closed")
        session.run()
        self.assertNotIn(session.client, self.server.state.clients)
        self.assertIsNone(self.server.state.find_nick("closing"))
        sock.close.assert_called_once()

    def test_part_finishes_before_a_replacement_nickname_joins(self):
        observer = self.add_client("SuperBot")
        leaving = self.add_client("bob")
        for client in (observer, leaving):
            self.server.state.join(client, "#hello")
        bot = BotClient()
        bot.state.replace_names("#hello", ["SuperBot", "bob"])
        observer.connection.send.side_effect = bot.handle
        parted, resume = threading.Event(), threading.Event()
        attempting, replaced = threading.Event(), threading.Event()
        errors = []
        original_part = self.server.state.part

        def part(client, channel):
            result = original_part(client, channel)
            parted.set()
            if not resume.wait(2):
                raise TimeoutError("PART was not resumed")
            return result

        def leave():
            try:
                self.server.handlers.handle(leaving, message("PART", "#hello"))
            except Exception as exc:
                errors.append(exc)

        def replace():
            try:
                attempting.set()
                self.server.disconnect(leaving)
                replacement = self.add_client("bob")
                self.server.join_channel(replacement, "#hello")
                replaced.set()
            except Exception as exc:
                errors.append(exc)

        with patch.object(self.server.state, "part", side_effect=part):
            worker = threading.Thread(target=leave)
            closer = threading.Thread(target=replace)
            worker.start()
            try:
                self.assertTrue(parted.wait(2))
                closer.start()
                self.assertTrue(attempting.wait(2))
                # The old implementation lets the replacement finish in this gap.
                replaced.wait(0.1)
            finally:
                resume.set()
                worker.join(2)
                if closer.ident is not None:
                    closer.join(2)
        self.assertFalse(worker.is_alive())
        self.assertFalse(closer.is_alive())
        self.assertEqual(errors, [])
        self.assertTrue(replaced.is_set())
        self.assertEqual(bot.state.members("#hello"), {"SuperBot", "bob"})
        self.assertEqual(
            [call.args[0].command for call in observer.connection.send.call_args_list],
            ["PART", "JOIN"],
        )

    def test_join_send_failure_is_announced_after_join_to_healthy_peer(self):
        observer = self.add_client("SuperBot")
        joining = self.add_client("bob")
        self.server.state.join(observer, "#hello")
        bot = BotClient()
        bot.state.replace_names("#hello", ["SuperBot"])
        observer.connection.send.side_effect = bot.handle
        joining.connection.send.side_effect = OSError("connection lost during JOIN")
        original_join = self.server.state.join

        def join_with_failing_recipient_first(client, channel):
            joined, _members = original_join(client, channel)
            return joined, [joining, observer]

        with patch.object(self.server.state, "join", side_effect=join_with_failing_recipient_first):
            self.server.handlers.handle(joining, message("JOIN", "#hello"))
        self.assertEqual(
            [call.args[0].command for call in observer.connection.send.call_args_list],
            ["JOIN", "QUIT"],
        )
        self.assertEqual(bot.state.members("#hello"), {"SuperBot"})
        self.assertNotIn(joining, self.server.state.clients)
        joining.connection.close.assert_called_once()

    def test_listener_startup_failure_closes_socket(self):
        sock = Mock()
        sock.bind.side_effect = OSError("address already in use")
        with patch("server.server.socket.socket", return_value=sock):
            with self.assertRaisesRegex(OSError, "address already in use"):
                self.server.serve_forever()
        sock.close.assert_called_once()
        self.assertFalse(self.server.ready.is_set())

    def test_stopped_server_does_not_create_a_new_listener(self):
        self.server.stop()
        with patch("server.server.socket.socket") as create_socket:
            self.server.serve_forever()
        create_socket.assert_not_called()
        self.assertFalse(self.server.ready.is_set())

    def test_accepted_session_after_server_stop_is_closed_without_registration(self):
        sock = Mock()
        session = ClientSession(self.server, sock, ("::1", 2))
        self.server.stop()
        with patch("server.client_session.threading.Thread") as thread:
            session.start()
        thread.assert_not_called()
        sock.close.assert_called_once()
        self.assertNotIn(session.client, self.server.state.clients)

    def test_session_thread_start_failure_closes_socket_and_removes_state(self):
        sock = Mock()
        session = ClientSession(self.server, sock, ("::1", 2))
        with patch(
            "server.client_session.threading.Thread.start",
            side_effect=RuntimeError("cannot start thread"),
        ):
            with self.assertRaisesRegex(RuntimeError, "cannot start thread"):
                session.start()
        sock.close.assert_called_once()
        self.assertNotIn(session.client, self.server.state.clients)

    def test_channel_wide_send_failure_cleans_all_clients_without_recursion(self):
        class FailedConnection:
            def __init__(self):
                self.closed = False

            def send(self, _message):
                raise OSError("network unavailable")

            def close(self):
                self.closed = True

        server = IRCServer()
        clients = []
        for index in range(400):
            client = ClientState(FailedConnection(), ("::1", index))
            server.state.add_client(client)
            server.state.set_nick(client, f"user{index}")
            server.state.set_user(client, "user", "Real")
            server.state.join(client, "#shared")
            clients.append(client)

        server.disconnect(clients[0], "network outage")

        self.assertEqual(server.state.clients, set())
        self.assertEqual(server.state.channel_members("#shared"), [])
        self.assertTrue(all(client.connection.closed for client in clients))

    def test_disconnect_closes_socket_before_notifying_slow_peer(self):
        leaving = self.add_client("leaving")
        peer = self.add_client("peer")
        self.server.state.join(leaving, "#shared")
        self.server.state.join(peer, "#shared")

        def receive_quit(_message):
            leaving.connection.close.assert_called_once()

        peer.connection.send.side_effect = receive_quit
        self.server.disconnect(leaving)

    def test_send_failures_preserve_healthy_delivery_and_one_quit_per_departure(self):
        first = self.add_client("first")
        second = self.add_client("second")
        healthy = self.add_client("healthy")
        for client in (first, second, healthy):
            for channel in ("#one", "#two"):
                self.server.state.join(client, channel)
        first.connection.send.side_effect = OSError("first lost")
        second.connection.send.side_effect = OSError("second lost")
        chat = message("PRIVMSG", "#one", "hello", prefix="sender!u@host")

        self.server.send_many((first, second, healthy), chat)

        replies = [call.args[0] for call in healthy.connection.send.call_args_list]
        self.assertEqual(replies[0], chat)
        self.assertEqual(len(replies), 3)
        self.assertEqual(
            {reply.prefix for reply in replies[1:]}, {first.prefix, second.prefix}
        )
        self.assertTrue(all(reply.command == "QUIT" for reply in replies[1:]))
        self.assertEqual(self.server.state.clients, {self.requester, healthy})
        first.connection.close.assert_called_once()
        second.connection.close.assert_called_once()

    def test_invalid_user_is_rejected_and_can_be_retried_before_long_join(self):
        invalid_usernames = [
            "u" * 480,
            "u" * 31,
            "bad user",
            "bad@host",
            "bad!user",
            ":bad",
            "",
            "\t",
            "\x00",
            "\u7528\u6237",
        ]
        for username in invalid_usernames:
            with self.subTest(username=username):
                client = self.add_client("alice", registered=False)
                self.server.handlers.cmd_user(client, (username, "0", "*", "Real"))
                self.assertFalse(client.registered)
                self.assertIsNone(client.username)
                self.assertEqual(
                    client.connection.send.call_args.args[0].command, "461"
                )
                self.server.state.remove(client)

        client = self.add_client("alice", registered=False)
        self.server.handlers.handle(client, message("USER", "u" * 30, "0", "*", "Real"))
        self.assertTrue(client.registered)
        self.server.handlers.handle(client, message("JOIN", "#" + "r" * 49))
        replies = [call.args[0] for call in client.connection.send.call_args_list]
        self.assertTrue(any(reply.command == "JOIN" for reply in replies))
        self.assertTrue(all(len(reply.to_bounded_bytes()) <= 512 for reply in replies))

    def test_private_messages_require_registered_recipient_but_nick_stays_reserved(
        self,
    ):
        pending = self.add_client("Pending", registered=False)
        self.assertIs(self.server.state.find_nick("PENDING"), pending)
        self.assertIsNone(self.server.state.direct_target("pending"))
        self.server.handlers.handle(
            self.requester, message("PRIVMSG", "pending", "secret")
        )
        pending.connection.send.assert_not_called()
        self.assertEqual(
            self.requester.connection.send.call_args.args[0].command, "401"
        )
        self.server.handlers.cmd_ison(self.requester, ("pending",))
        self.assertEqual(
            self.requester.connection.send.call_args.args[0].params[-1], ""
        )

        self.server.handlers.handle(pending, message("USER", "user", "0", "*", "Real"))
        pending.connection.send.reset_mock()
        self.server.handlers.handle(
            self.requester, message("PRIVMSG", "PENDING", "secret")
        )
        self.assertEqual(pending.connection.send.call_args.args[0].command, "PRIVMSG")
        self.server.state.remove(pending)
        self.assertIsNone(self.server.state.direct_target("Pending"))


class BotDeadlineTests(unittest.TestCase):
    COMPLETE_WELCOME = (
        b":irc.local 001 SuperBot :Welcome\r\n"
        b":SuperBot!u@host JOIN #hello\r\n"
        b":irc.local 353 SuperBot = #hello :SuperBot alice\r\n"
        b":irc.local 366 SuperBot #hello :End of names\r\n"
    )

    def run_script(self, bot, events):
        now = [0.0]
        events = iter(events)
        sock = Mock()

        def recv(_size):
            event = next(events, None)
            if event is None:
                bot.stopping.set()
                raise socket.timeout()
            elapsed, data = event
            now[0] += elapsed
            if data is None:
                raise socket.timeout()
            return data() if callable(data) else data

        sock.recv.side_effect = recv
        with (
            patch("bot.client.socket.socket", return_value=sock),
            patch("bot.client.time.monotonic", side_effect=lambda: now[0]),
        ):
            bot.run_once()
        return sock

    def test_silent_server_hits_registration_deadline(self):
        with self.assertRaisesRegex(TimeoutError, "registration"):
            self.run_script(BotClient(), [(30, None)])

    def test_registration_deadline_is_not_extended_by_server_traffic(self):
        with self.assertRaisesRegex(TimeoutError, "registration"):
            self.run_script(BotClient(), [(15, b"PING :a\r\n"), (15, b"PING :b\r\n")])

    def test_registered_silent_server_is_probed_then_times_out(self):
        bot = BotClient()
        bot.send = Mock()
        with self.assertRaisesRegex(TimeoutError, "PONG"):
            self.run_script(
                bot,
                [(1, self.COMPLETE_WELCOME), (30, None), (30, None)],
            )
        self.assertEqual(bot.send.call_args.args[0].command, "PING")

    def test_matching_pong_keeps_quiet_healthy_connection(self):
        bot = BotClient()
        bot.send = Mock()

        def matching_pong():
            probe = bot.send.call_args.args[0]
            self.assertEqual(probe.command, "PING")
            return message(
                "PONG", "irc.local", probe.params[-1], prefix="irc.local"
            ).to_bytes()

        sock = self.run_script(
            bot,
            [
                (1, self.COMPLETE_WELCOME),
                (30, None),
                (1, matching_pong),
                (29, None),
            ],
        )
        self.assertEqual(
            [call.args[0].command for call in bot.send.call_args_list],
            ["NICK", "USER", "JOIN", "PING"],
        )
        sock.close.assert_not_called()

    def test_wrong_pong_and_other_traffic_do_not_cancel_probe_deadline(self):
        with self.assertRaisesRegex(TimeoutError, "PONG"):
            self.run_script(
                BotClient(),
                [
                    (1, self.COMPLETE_WELCOME),
                    (30, None),
                    (15, b":irc.local PONG :wrong\r\n"),
                    (15, b"PING :server\r\n"),
                ],
            )

    def test_timeout_closes_socket_and_enters_reconnect_loop(self):
        bot = BotClient(reconnect_delay=0)
        sock = Mock()
        attempts = []

        def run_once():
            attempts.append(1)
            if len(attempts) == 1:
                bot.socket = sock
                raise TimeoutError("registration timed out")
            bot.stopping.set()

        bot.run_once = run_once
        with self.assertLogs("bot.client", level="WARNING"):
            bot.run()
        self.assertEqual(len(attempts), 2)
        sock.close.assert_called_once()

    def test_invalid_configured_nickname_does_not_poison_user_registration(self):
        bot = BotClient(nickname="n" * 31)
        sock = self.run_script(bot, [(1, b":irc.local 001 SuperBot :Welcome\r\n")])
        requests = [call.args[0] for call in sock.sendall.call_args_list]
        self.assertEqual(requests[0], b"NICK SuperBot\r\n")
        self.assertEqual(requests[1], b"USER SuperBot 0 * SuperBot\r\n")
        self.assertEqual(requests[2], b"JOIN #hello\r\n")

    def test_normal_stop_does_not_log_a_connection_failure(self):
        bot = BotClient(reconnect_delay=0)

        def stopped_recv():
            bot.stop()
            raise OSError("socket closed by stop")

        bot.run_once = stopped_recv
        with self.assertNoLogs("bot.client", level="WARNING"):
            bot.run()

    def test_stop_during_socket_creation_does_not_leave_new_socket_open(self):
        bot = BotClient(reconnect_delay=0)
        sock = Mock()

        def create_socket(*_args):
            bot.stop()
            return sock

        with patch("bot.client.socket.socket", side_effect=create_socket):
            bot.run()
        sock.close.assert_called_once()
        self.assertIsNone(bot.socket)

    def test_invalid_channel_configuration_fails_before_connecting(self):
        for channel in ("#", "bad", "#has space", "#" + "x" * 50):
            with self.subTest(channel=channel):
                with self.assertRaises(ValueError):
                    BotClient(channel=channel)

    def test_who_batches_fit_the_actual_server_reply_prefix(self):
        bot = BotClient(nickname="q" * 30)
        bot.send = Mock()
        bot.handle(message("001", bot.nickname, "Welcome", prefix="s" * 63))
        names = [f"n{index:029d}" for index in range(29)]
        bot.state.replace_names("#hello", names)
        bot.send.reset_mock()
        bot.handle(message("PRIVMSG", "#hello", "!who", prefix="alice!u@host"))
        advertised = []
        for call in bot.send.call_args_list:
            query = call.args[0]
            self.assertEqual(query.command, "ISON")
            advertised.extend(query.params)
            reply = message(
                "303", bot.nickname, " ".join(query.params), prefix="s" * 63
            )
            self.assertLessEqual(len(reply.to_bounded_bytes()), 512)
        self.assertEqual(sorted(advertised), sorted(names))

    def test_who_error_clears_pending_query_for_retry(self):
        bot = BotClient()
        bot.send = Mock()
        request = message("PRIVMSG", "#hello", "!who", prefix="alice!u@host")
        bot.handle(request)
        bot.handle(message("421", "SuperBot", "ISON", "Unknown command"))
        self.assertIsNone(bot.queries._who_channel)
        bot.send.reset_mock()
        bot.handle(request)
        self.assertEqual(bot.send.call_args.args[0].command, "ISON")

    def test_who_throttle_reports_unavailable_without_connection_timeout(self):
        bot = BotClient()
        bot.send = Mock()
        bot._registered = True
        request = message("PRIVMSG", "#hello", "!who", prefix="alice!u@host")
        with patch("bot.client.time.monotonic", return_value=100):
            bot.handle(request)
        bot.send.reset_mock()
        bot.handle(message("263", bot.nickname, "ISON", "Try again later"))
        bot.send.assert_called_once_with(
            message("PRIVMSG", "#hello", "WHO unavailable: server rejected ISON.")
        )
        with patch("bot.client.time.monotonic", return_value=130):
            bot._check_timeouts(100, None)
            bot.handle(request)
        self.assertEqual(bot.send.call_args.args[0].command, "ISON")

    def test_who_error_drains_other_batches_before_a_new_query(self):
        bot = BotClient()
        bot.send = Mock()
        bot.state.replace_names("#hello", [f"member{index}" for index in range(30)])
        request = message("PRIVMSG", "#hello", "!who", prefix="alice!u@host")
        bot.handle(request)
        batches = bot.queries._who_pending
        self.assertGreater(batches, 1)
        bot.handle(message("421", "SuperBot", "ISON", "Unknown command"))
        bot.send.reset_mock()
        bot.handle(request)
        bot.send.assert_not_called()
        for _ in range(batches - 1):
            bot.handle(message("303", "SuperBot", "member0"))
        self.assertIsNone(bot.queries._who_channel)
        replies = [call.args[0].params[-1] for call in bot.send.call_args_list]
        self.assertEqual(replies, ["WHO unavailable: server rejected ISON."])
        bot.send.reset_mock()
        bot.handle(request)
        self.assertEqual(bot.send.call_args.args[0].command, "ISON")

    def test_missing_who_reply_times_out_even_with_healthy_traffic(self):
        bot = BotClient()
        bot.send = Mock()
        with self.assertRaisesRegex(TimeoutError, "ISON"):
            self.run_script(
                bot,
                [
                    (1, self.COMPLETE_WELCOME),
                    (1, b":alice!u@host PRIVMSG #hello :!who\r\n"),
                    (15, b"PING :healthy\r\n"),
                    (15, b"PING :healthy\r\n"),
                ],
            )
        self.assertIsNone(bot.queries._who_channel)

    def test_missing_names_end_times_out_and_discards_pending_commands(self):
        bot = BotClient()
        bot.send = Mock()
        with self.assertRaisesRegex(TimeoutError, "NAMES"):
            self.run_script(
                bot,
                [
                    (1, b":irc.local 001 SuperBot :Welcome\r\n"),
                    (1, b":SuperBot!u@host JOIN #hello\r\n"),
                    (1, b":alice!u@host PRIVMSG #hello :!slap bob\r\n"),
                    (14, b"PING :healthy\r\n"),
                    (15, b"PING :healthy\r\n"),
                ],
            )
        self.assertIsNone(bot._names_started)
        self.assertEqual(len(bot._pending_commands), 0)

    def test_reconnect_discards_deferred_commands_from_previous_connection(self):
        bot = BotClient()
        bot.send = Mock()
        bot.handle(message("JOIN", "#hello", prefix="SuperBot!u@host"))
        bot.handle(message("PRIVMSG", "#hello", "!slap bob", prefix="alice!u@host"))
        self.assertEqual(len(bot._pending_commands), 1)
        self.run_script(bot, [(1, self.COMPLETE_WELCOME)])
        self.assertEqual(len(bot._pending_commands), 0)
        self.assertIsNone(bot._names_started)


if __name__ == "__main__":
    unittest.main()
