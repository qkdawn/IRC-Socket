import socket
import threading
import time
import unittest
from unittest.mock import patch

from bot.client import BotClient
from common.stream import IRCStreamDecoder
from server.server import IRCServer


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.server = IRCServer("::1", 0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        if not self.server.ready.wait(2):
            self.fail("server did not start listening within two seconds")
        if self.server.socket is None:
            self.fail("server did not expose its listening socket")
        self.port = self.server.socket.getsockname()[1]
        self.decoders = {}
        self.pending = {}

    def tearDown(self):
        self.server.stop()
        self.thread.join(timeout=2)

    def connect(self, nick, *, register=True):
        sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        sock.settimeout(2)
        sock.connect(("::1", self.port))
        sock.sendall(f"NICK {nick}\r\n".encode())
        if register:
            sock.sendall(f"USER {nick} 0 * :{nick}\r\n".encode())
        self.addCleanup(sock.close)
        self.decoders[sock] = IRCStreamDecoder()
        self.pending[sock] = []
        return sock

    def test_large_list_is_complete_and_keeps_a_reading_client_connected(self):
        requester = self.connect("query")
        self.wait_for(requester, lambda incoming: incoming.command == "004")
        client = self.server.state.find_nick("query")
        expected = {f"#channel{index:04d}" for index in range(1000)}
        for channel in expected:
            self.server.state.join(client, channel)
        requester.sendall(b"LIST\r\n")
        self.wait_for(requester, lambda incoming: incoming.command == "323")
        entries = [msg for msg in self.pending[requester] if msg.command == "322"]
        self.assertEqual(len(entries), 1000)
        self.assertEqual({msg.params[1] for msg in entries}, expected)
        self.assertTrue(all(msg.params[2] == "1" for msg in entries))
        requester.sendall(b"PING :after-list\r\n")
        self.wait_for(requester, lambda incoming: incoming.command == "PONG")
        self.assertFalse(client.disconnected)

    def test_100_channel_join_and_part_complete_without_disconnect(self):
        for attempt in range(3):
            with self.subTest(attempt=attempt):
                requester = self.connect(f"joining{attempt}")
                self.wait_for(requester, lambda incoming: incoming.command == "004")
                self.pending[requester].clear()
                channels = [f"#{index}" for index in range(100)]
                request = ("JOIN " + ",".join(channels) + "\r\n").encode()
                self.assertEqual(len(request), 396)
                requester.sendall(request)
                for channel in channels:
                    end = self.wait_for(requester, lambda incoming: incoming.command == "366")
                    self.assertEqual(end.params[1], channel)
                replies = self.pending[requester]
                self.assertEqual(sum(msg.command == "JOIN" for msg in replies), 100)
                self.assertEqual(sum(msg.command == "353" for msg in replies), 100)
                self.pending[requester].clear()
                requester.sendall(("PART " + ",".join(channels) + "\r\n").encode())
                for channel in channels:
                    reply = self.wait_for(requester, lambda incoming: incoming.command == "PART")
                    self.assertEqual(reply.params[0], channel)
                requester.sendall(b"PING :after-join-part\r\n")
                self.wait_for(requester, lambda incoming: incoming.command == "PONG")
                client = self.server.state.find_nick(f"joining{attempt}")
                self.assertIsNotNone(client)
                self.assertFalse(client.disconnected)
                self.assertEqual(self.server.state.channels_for(client), [])

    def test_large_names_response_finishes_without_disconnect(self):
        requester = self.connect("query")
        self.wait_for(requester, lambda incoming: incoming.command == "004")
        client = self.server.state.find_nick("query")
        expected = {f"#channel{index:04d}" for index in range(1000)}
        for channel in expected:
            self.server.state.join(client, channel)
        requester.sendall(b"NAMES\r\n")
        completed = set()
        for _ in expected:
            reply = self.wait_for(requester, lambda incoming: incoming.command == "366")
            completed.add(reply.params[1])
        self.assertEqual(completed, expected)
        entries = [msg for msg in self.pending[requester] if msg.command == "353"]
        self.assertEqual(len(entries), 1000)
        self.assertEqual({msg.params[2] for msg in entries}, expected)
        self.assertTrue(all(msg.params[-1] == "query" for msg in entries))
        requester.sendall(b"PING :after-names\r\n")
        self.wait_for(requester, lambda incoming: incoming.command == "PONG")
        self.assertFalse(client.disconnected)

    def test_pipelined_ping_requests_are_paced_for_a_reading_client(self):
        requester = self.connect("pipelined")
        self.wait_for(requester, lambda incoming: incoming.command == "004")
        requester.sendall(b"".join(f"PING :probe-{index}\r\n".encode() for index in range(600)))
        for index in range(600):
            reply = self.wait_for(requester, lambda incoming: incoming.command == "PONG")
            self.assertEqual(reply.params[-1], f"probe-{index}")
        self.assertFalse(self.server.state.find_nick("pipelined").disconnected)

    def test_malformed_input_receives_error_before_connection_closes(self):
        requester = self.connect("malformed")
        self.wait_for(requester, lambda incoming: incoming.command == "004")
        requester.sendall(b"PING :bad\x00token\r\n")
        reply = self.wait_for(requester, lambda incoming: incoming.command == "ERROR")
        self.assertEqual(reply.params[-1], "Malformed IRC line")
        self.assertEqual(requester.recv(4096), b"")

    def test_long_ison_request_keeps_client_connected(self):
        requester = self.connect("q" * 30)
        nick = "n" + "x" * 29
        online = self.connect(nick)
        self.wait_for(requester, lambda incoming: incoming.command == "001")
        self.wait_for(online, lambda incoming: incoming.command == "001")
        request = ("ISON :" + " ".join([nick] * 15) + "\r\n").encode()
        self.assertEqual(len(request), 472)
        requester.sendall(request)
        reply = self.wait_for(requester, lambda incoming: incoming.command == "303")
        self.assertEqual(reply.params[-1], nick)
        requester.sendall(b"PING :still-here\r\n")
        self.wait_for(requester, lambda incoming: incoming.command == "PONG")

    def test_ison_overflow_is_explicit_and_smaller_batches_return_every_online_user(self):
        self.server.server_name = "s" * 63
        nickname = "q" * 30
        requester = self.connect(nickname)
        self.wait_for(requester, lambda incoming: incoming.command == "001")
        names = [f"n{index:029d}" for index in range(15)]
        for name in names:
            online = self.connect(name)
            self.wait_for(online, lambda incoming: incoming.command == "001")
        request = ("ISON :" + " ".join(names) + "\r\n").encode()
        self.assertEqual(len(request), 472)
        requester.sendall(request)
        reply = self.wait_for(
            requester, lambda incoming: incoming.command in {"303", "417"}
        )
        self.assertEqual(reply.command, "417")
        self.assertEqual(reply.params[:2], (nickname, "ISON"))
        self.assertIn("smaller batches", reply.params[-1])
        self.assertLessEqual(len(reply.to_bounded_bytes()), 512)
        requester.sendall(b"PING :after-overflow\r\n")
        self.wait_for(requester, lambda incoming: incoming.command == "PONG")
        self.assertFalse(
            any(incoming.command in {"303", "417"} for incoming in self.pending[requester])
        )
        found = []
        for batch in (names[:13], names[13:]):
            requester.sendall(("ISON :" + " ".join(batch) + "\r\n").encode())
            reply = self.wait_for(
                requester, lambda incoming: incoming.command in {"303", "417"}
            )
            self.assertEqual(reply.command, "303")
            self.assertLessEqual(len(reply.to_bounded_bytes()), 512)
            found.extend(reply.params[-1].split())
        self.assertEqual(found, names)

    def test_registration_timeout_closes_socket_and_releases_reserved_nickname(self):
        connected_at = self.server.monotonic()
        pending = self.connect("ReservedNick", register=False)
        pending.sendall(b"PING :keep-alive\r\n")
        self.wait_for(pending, lambda incoming: incoming.command == "PONG")
        self.assertIsNotNone(self.server.state.find_nick("ReservedNick"))
        with patch.object(
            self.server, "monotonic", return_value=connected_at + 31
        ):
            self.server._check_idle_clients()
        self.assertEqual(pending.recv(4096), b"")
        self.assertIsNone(self.server.state.find_nick("ReservedNick"))
        replacement = self.connect("ReservedNick")
        welcome = self.wait_for(replacement, lambda incoming: incoming.command == "001")
        self.assertEqual(welcome.params[0], "ReservedNick")

    def test_long_user_is_rejected_then_registration_and_join_succeed(self):
        client = self.connect("alice", register=False)
        request = b"USER " + b"u" * 480 + b" 0 * :Real\r\n"
        self.assertEqual(len(request), 497)
        client.sendall(request)
        self.wait_for(client, lambda incoming: incoming.command == "461")
        channel = "#" + "r" * 49
        client.sendall(("USER user 0 * :Real\r\nJOIN " + channel + "\r\n").encode())
        self.wait_for(client, lambda incoming: incoming.command == "001")
        self.wait_for(client, lambda incoming: incoming.command == "JOIN")
        client.sendall(b"PING :still-here\r\n")
        self.wait_for(client, lambda incoming: incoming.command == "PONG")

    def test_full_length_ping_and_whitespace_chat_preserve_content(self):
        alice = self.connect("alice")
        bob = self.connect("bob")
        self.wait_for(alice, lambda incoming: incoming.command == "001")
        self.wait_for(bob, lambda incoming: incoming.command == "001")
        token = b"x" * 504
        alice.sendall(b"PING :" + token + b"\r\n")
        pong = self.wait_for(alice, lambda incoming: incoming.command == "PONG")
        self.assertEqual(pong.params[-1].encode(), token)
        alice.sendall(b"PRIVMSG bob :hello\tworld\r\n")
        reply = self.wait_for(bob, lambda incoming: incoming.command == "PRIVMSG")
        self.assertEqual(reply.params, ("bob", "hello\tworld"))
        alice.sendall(b"PING :still-here\r\n")
        self.wait_for(alice, lambda incoming: incoming.command == "PONG")

    def test_bot_registers_tracks_members_and_answers_commands(self):
        alice = self.connect("alice")
        self.wait_for(alice, lambda incoming: incoming.command == "001")
        alice.sendall(b"JOIN #hello\r\n")
        self.wait_for(alice, lambda incoming: incoming.command == "366")
        alice.sendall(b"JOIN #discovery\r\n")
        self.wait_for(
            alice,
            lambda incoming: incoming.command == "366"
            and incoming.params[1] == "#discovery",
        )
        bot = BotClient(host="::1", port=self.port, nickname="n" * 31)
        errors = []

        def run_bot():
            try:
                bot.run()
            except Exception as exc:
                errors.append(exc)

        worker = threading.Thread(target=run_bot, daemon=True)
        worker.start()
        try:
            self.wait_for(
                alice,
                lambda incoming: incoming.command == "JOIN"
                and incoming.prefix.startswith("SuperBot!"),
            )
            alice.sendall(b"PRIVMSG #hello :!who\r\n")
            result = self.wait_for(
                alice,
                lambda incoming: incoming.command == "PRIVMSG"
                and incoming.params[-1].startswith("WHO complete:"),
            )
            self.assertEqual(result.params[-1], "WHO complete: 2 members")
            alice.sendall(b"PRIVMSG #hello :!channels\r\n")
            self.wait_for(
                alice,
                lambda incoming: incoming.command == "PRIVMSG"
                and incoming.params[-1] == "CHANNEL: #discovery (1 users)",
            )
            self.wait_for(
                alice,
                lambda incoming: incoming.command == "PRIVMSG"
                and incoming.params[-1] == "CHANNEL: #hello (2 users)",
            )
            self.wait_for(
                alice,
                lambda incoming: incoming.command == "PRIVMSG"
                and incoming.params[-1] == "CHANNELS complete: 2 channels (showing 2)",
            )
            alice.sendall(b"PRIVMSG #hello :!network\r\n")
            self.wait_for(
                alice,
                lambda incoming: incoming.command == "PRIVMSG"
                and incoming.params[-1] == "NETWORK: There are 2 users and 0 services on 1 server",
            )
            alice.sendall(b"PRIVMSG SuperBot :hello\r\n")
            fact = self.wait_for(
                alice,
                lambda incoming: incoming.command == "PRIVMSG"
                and incoming.params[0] == "alice",
            )
            self.assertTrue(fact.params[-1])
            long_fact = "A Unicode fact: \u754c\U0001f642 " * 60
            long_fact = long_fact.strip()
            bot.commands.facts = [long_fact]
            alice.sendall(b"PRIVMSG SuperBot :Tell me the long fact\r\n")
            received = ""
            while len(received) < len(long_fact):
                part = self.wait_for(
                    alice,
                    lambda incoming: incoming.command == "PRIVMSG"
                    and incoming.params[0] == "alice",
                )
                received += part.params[-1]
            self.assertEqual(received, long_fact)
            alice.sendall(b"PRIVMSG #hello :!hello\r\n")
            greeting = self.wait_for(
                alice,
                lambda incoming: incoming.command == "PRIVMSG"
                and incoming.params[-1] == "Hello, alice!",
            )
            self.assertEqual(greeting.params[0], "#hello")
        finally:
            bot.stop()
            worker.join(2)
        self.assertFalse(worker.is_alive())
        self.assertEqual(errors, [])

    def test_nick_only_client_cannot_receive_private_message(self):
        alice = self.connect("alice")
        pending = self.connect("pending", register=False)
        self.wait_for(alice, lambda incoming: incoming.command == "001")
        pending.sendall(b"PING :nick-reserved\r\n")
        self.wait_for(pending, lambda incoming: incoming.command == "PONG")
        alice.sendall(b"PRIVMSG pending :before-registration\r\n")
        self.wait_for(alice, lambda incoming: incoming.command == "401")
        pending.sendall(b"USER user 0 * :Real\r\n")
        self.wait_for(pending, lambda incoming: incoming.command == "001")
        self.assertFalse(
            any(incoming.command == "PRIVMSG" for incoming in self.pending[pending])
        )
        alice.sendall(b"PRIVMSG pending :after-registration\r\n")
        reply = self.wait_for(pending, lambda incoming: incoming.command == "PRIVMSG")
        self.assertEqual(reply.params[-1], "after-registration")

    def wait_for(self, sock, predicate):
        """Wait for one decoded IRC message while retaining other messages."""
        deadline = time.time() + 2
        while time.time() < deadline:
            for index, incoming in enumerate(self.pending[sock]):
                if predicate(incoming):
                    return self.pending[sock].pop(index)
            data = sock.recv(4096)
            if not data:
                break
            self.pending[sock].extend(self.decoders[sock].feed(data))
        self.fail("timed out waiting for an expected IRC message")

    def test_two_clients_channel_and_private_routing(self):
        alice = self.connect("alice")
        bob = self.connect("bob")
        try:
            self.wait_for(alice, lambda message: message.command == "001")
            self.wait_for(bob, lambda message: message.command == "001")
            alice.sendall(b"JOIN #Room\r\n")
            bob.sendall(b"JOIN #room\r\n")
            self.wait_for(alice, lambda message: message.command == "JOIN")
            self.wait_for(bob, lambda message: message.command == "JOIN")
            alice.sendall(b"PRIVMSG #ROOM :hello\r\n")
            self.wait_for(
                bob,
                lambda message: message.command == "PRIVMSG"
                and message.params[-1] == "hello",
            )
            alice.sendall(b"PRIVMSG bob :secret\r\n")
            self.wait_for(
                bob,
                lambda message: message.command == "PRIVMSG"
                and message.params[-1] == "secret",
            )
        finally:
            alice.close()
            bob.close()


if __name__ == "__main__":
    unittest.main()
