import socket
import threading
import time
import unittest

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

    def connect(self, nick):
        sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        sock.settimeout(2)
        sock.connect(("::1", self.port))
        sock.sendall(f"NICK {nick}\r\nUSER {nick} 0 * :{nick}\r\n".encode())
        self.decoders[sock] = IRCStreamDecoder()
        self.pending[sock] = []
        return sock

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
