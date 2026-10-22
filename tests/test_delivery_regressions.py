"""Socket delivery stays ordered per client without blocking other clients."""

import threading
import unittest
from unittest.mock import Mock, patch

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

    def test_list_waits_for_space_without_blocking_another_client(self):
        listing = self.session("listing")
        healthy = self.session("healthy")
        channels = [f"#channel{index:04d}" for index in range(1000)]
        for channel in channels:
            self.server.state.join(listing.client, channel)
        entered, release, _worker = self.block_writer(listing)
        self.server.send(listing.client, message("NOTICE", "listing", "first"))
        self.assertTrue(entered.wait(2))
        waiting, finished, answered = (threading.Event() for _ in range(3))
        received = []

        def receive(payload):
            incoming = IRCMessage.parse(payload.decode())
            received.append(incoming)
            if incoming.command == "323":
                finished.set()

        listing.socket.sendall.side_effect = receive
        healthy.socket.sendall.side_effect = lambda _payload: answered.set()
        start_writer(self, healthy)
        original_wait = listing.send_lock.wait

        def wait(timeout):
            waiting.set()
            return original_wait(timeout)

        errors = []

        def produce():
            try:
                self.server.handlers.handle(listing.client, message("LIST"))
            except Exception as exc:
                errors.append(exc)

        with patch.object(listing.send_lock, "wait", side_effect=wait):
            producer = threading.Thread(target=produce)
            producer.start()
            try:
                self.assertTrue(waiting.wait(2))
                self.assertLessEqual(
                    listing._outgoing.qsize(), listing.MAX_PENDING_MESSAGES
                )
                self.server.handlers.handle(healthy.client, message("PING", "independent"))
                self.assertTrue(answered.wait(2))
                self.assertFalse(listing.client.disconnected)
                self.assertFalse(release.is_set())
            finally:
                release.set()
                producer.join(2)
        self.assertFalse(producer.is_alive())
        self.assertEqual(errors, [])
        self.assertTrue(finished.wait(2))
        self.assertEqual([msg.params[1] for msg in received[:-1]], channels)
        self.assertEqual(received[-1].command, "323")
        self.assertFalse(listing.client.disconnected)

    def test_stalled_list_queue_times_out_and_releases_the_nickname(self):
        session = self.session("stalled")
        session.OUTPUT_QUEUE_TIMEOUT = 0.05
        self.server.state.join(session.client, "#hello")
        for _ in range(session.MAX_PENDING_MESSAGES):
            session.send(message("NOTICE", "stalled", "queued"))
        with patch.object(session.send_lock, "wait", wraps=session.send_lock.wait) as wait:
            self.server.handlers.handle(session.client, message("LIST"))
        self.assertTrue(wait.called)
        self.assertTrue(session.closed.is_set())
        self.assertTrue(session.client.disconnected)
        self.assertIsNone(self.server.state.find_nick("stalled"))
        self.assertEqual(self.server.state.channel_members("#hello"), [])

    def test_close_wakes_a_reply_producer_waiting_for_space(self):
        session = self.session("closing")
        for _ in range(session.MAX_PENDING_MESSAGES):
            session.send(message("NOTICE", "closing", "queued"))
        waiting = threading.Event()
        original_wait = session.send_lock.wait

        def wait(timeout):
            waiting.set()
            return original_wait(timeout)

        with patch.object(session.send_lock, "wait", side_effect=wait):
            producer = threading.Thread(
                target=self.server.send,
                args=(session.client, message("323", "closing", "End of /LIST")),
                kwargs={"wait_for_space": True},
            )
            producer.start()
            try:
                self.assertTrue(waiting.wait(2))
                self.server.disconnect(session.client)
            finally:
                session.close()
                producer.join(2)
        self.assertFalse(producer.is_alive())
        self.assertTrue(session.client.disconnected)
        self.assertEqual(session._outgoing.qsize(), 1)
        self.assertIsNone(session._outgoing.get_nowait())


if __name__ == "__main__":
    unittest.main()
