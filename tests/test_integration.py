import socket
import threading
import time
import unittest

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
