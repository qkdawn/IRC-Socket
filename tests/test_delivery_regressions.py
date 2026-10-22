"""Socket delivery stays ordered per client without blocking other clients."""

import threading
import unittest
from unittest.mock import Mock

from common.irc_message import IRCMessage, message
from server.client_session import ClientSession
from server.server import IRCServer
from tests.helpers import start_writer


class DeliveryRegressionTests(unittest.TestCase):
    def setUp(self):
        self.server = IRCServer()
        self.now = 0.0
        self.server.monotonic = lambda: self.now
        self.addCleanup(self.server.stop)

    def session(self, nick):
        session = ClientSession(self.server, Mock(), ("::1", 1))
        self.server.state.add_client(session.client)
        self.server.state.set_nick(session.client, nick)
        self.server.state.set_user(session.client, "u", nick)
        return session

    def block_writer(self, session):
        entered, release = threading.Event(), threading.Event()

        def write(_payload):
            entered.set()
            if not release.wait(2):
                raise TimeoutError("blocked writer was not released")

        session.socket.sendall.side_effect = write
        session.socket.shutdown.side_effect = lambda *_args: release.set()
        worker = start_writer(self, session)
        self.addCleanup(release.set)
        return entered, release, worker

    def test_slow_broadcast_recipient_does_not_block_other_users(self):
        slow = self.session("slow")
        healthy = self.session("healthy")
        entered, release, _worker = self.block_writer(slow)
        received = []
        answered = threading.Event()

        def write(payload):
            incoming = IRCMessage.parse(payload.decode())
            received.append(incoming.command)
            if incoming.command == "PONG":
                answered.set()

        healthy.socket.sendall.side_effect = write
        start_writer(self, healthy)
        self.server.send_many(
            [slow.client, healthy.client], message("PRIVMSG", "#hello", "hello")
        )
        self.assertTrue(entered.wait(2))
        self.server.handlers.handle(healthy.client, message("PING", "independent"))
        self.assertTrue(answered.wait(2))
        self.assertFalse(release.is_set())
        self.assertEqual(received, ["PRIVMSG", "PONG"])
        self.assertFalse(healthy.client.disconnected)

    def test_queued_ping_has_no_deadline_until_its_writer_starts(self):
        session = self.session("slow")
        entered, release, _worker = self.block_writer(session)
        self.server.send(session.client, message("NOTICE", "slow", "first"))
        self.assertTrue(entered.wait(2))
        self.now = 30.0
        self.server._check_idle_clients()
        self.assertTrue(session.client.ping_queued)
        self.assertIsNone(session.client.ping_sent)
        self.assertEqual(session._outgoing.qsize(), 1)
        self.now = 61.0
        self.server._check_idle_clients()
        self.assertFalse(session.client.disconnected)
        self.assertIsNone(session.client.ping_sent)
        self.assertEqual(session._outgoing.qsize(), 1)
        probe_written = threading.Event()
        session.socket.sendall.side_effect = lambda _payload: probe_written.set()
        release.set()
        self.assertTrue(probe_written.wait(2))
        self.assertEqual(session.client.ping_sent, 61.0)
        self.assertFalse(session.client.ping_queued)
        self.now = 90.999
        self.server._check_idle_clients()
        self.assertFalse(session.client.disconnected)
        self.now = 91.0
        self.server._check_idle_clients()
        self.assertTrue(session.client.disconnected)

    def test_fast_pong_cannot_arrive_before_the_probe_is_recorded(self):
        session = self.session("healthy")
        answered = threading.Event()

        def write(payload):
            self.assertEqual(IRCMessage.parse(payload.decode()).command, "PING")
            self.server.handlers.handle(
                session.client, message("PONG", self.server.server_name)
            )
            answered.set()

        session.socket.sendall.side_effect = write
        start_writer(self, session)
        self.now = 30.0
        self.server._check_idle_clients()
        self.assertTrue(answered.wait(2))
        self.assertIsNone(session.client.ping_sent)
        self.assertFalse(session.client.ping_queued)
        self.assertFalse(session.client.disconnected)

    def test_full_output_queue_disconnects_only_the_slow_client(self):
        slow = self.session("slow")
        healthy = self.session("healthy")
        for session in (slow, healthy):
            self.server.state.join(session.client, "#hello")
        entered, _release, worker = self.block_writer(slow)
        answered = threading.Event()
        healthy.socket.sendall.side_effect = lambda payload: (
            answered.set() if IRCMessage.parse(payload.decode()).command == "PONG" else None
        )
        start_writer(self, healthy)
        notice = message("NOTICE", "slow", "queued")
        self.server.send(slow.client, notice)
        self.assertTrue(entered.wait(2))
        for _ in range(slow.MAX_PENDING_MESSAGES):
            self.server.send(slow.client, notice)
        self.assertEqual(slow._outgoing.qsize(), slow.MAX_PENDING_MESSAGES)
        self.server.send(slow.client, notice)
        worker.join(2)
        self.assertFalse(worker.is_alive())
        self.assertTrue(slow.client.disconnected)
        self.assertIsNone(self.server.state.find_nick("slow"))
        self.assertEqual(self.server.state.channel_members("#hello"), [healthy.client])
        self.assertLessEqual(slow._outgoing.qsize(), 1)
        self.server.handlers.handle(healthy.client, message("PING", "still-here"))
        self.assertTrue(answered.wait(2))
        self.assertFalse(healthy.client.disconnected)

    def test_close_wakes_an_idle_writer_and_rejects_later_output(self):
        session = self.session("closing")
        worker = start_writer(self, session)
        self.server.disconnect(session.client)
        worker.join(2)
        self.assertFalse(worker.is_alive())
        with self.assertRaises(ConnectionError):
            session.send(message("NOTICE", "closing", "late"))
        session.socket.sendall.assert_not_called()


if __name__ == "__main__":
    unittest.main()
