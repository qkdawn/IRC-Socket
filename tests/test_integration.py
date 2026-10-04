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
        deadline = time.time() + 2
        while self.server.socket is None and time.time() < deadline:
            time.sleep(0.01)
        self.port = self.server.socket.getsockname()[1]

    def tearDown(self):
        self.server.stop()
        self.thread.join(timeout=2)

    def connect(self, nick):
        sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        sock.settimeout(2)
        sock.connect(("::1", self.port))
        sock.sendall(f"NICK {nick}\r\nUSER {nick} 0 * :{nick}\r\n".encode())
        return sock

    def read_messages(self, sock):
        decoder = IRCStreamDecoder()
        return decoder.feed(sock.recv(4096))

    def test_two_clients_channel_and_private_routing(self):
        alice = self.connect("alice")
        bob = self.connect("bob")
        try:
            self.read_messages(alice)
            self.read_messages(bob)
            alice.sendall(b"JOIN #room\r\n")
            bob.sendall(b"JOIN #room\r\n")
            time.sleep(0.05)
            alice.sendall(b"PRIVMSG #room :hello\r\n")
            time.sleep(0.05)
            messages = self.read_messages(bob)
            self.assertTrue(any(m.command == "PRIVMSG" and m.params[-1] == "hello" for m in messages))
            alice.sendall(b"PRIVMSG bob :secret\r\n")
            messages = self.read_messages(bob)
            self.assertTrue(any(m.params[-1] == "secret" for m in messages))
        finally:
            alice.close()
            bob.close()


if __name__ == "__main__":
    unittest.main()
