import unittest

from common.irc_message import IRCMessage
from server.errors import NicknameInUseError
from server.server import IRCServer
from server.state import ClientState, IRCState


class DummyConnection:
    def __init__(self):
        self.messages = []

    def send(self, _message):
        self.messages.append(_message)

    def close(self):
        return None


class StateTests(unittest.TestCase):
    def setUp(self):
        self.state = IRCState()
        self.a = ClientState(DummyConnection(), ("::1", 1))
        self.b = ClientState(DummyConnection(), ("::1", 2))
        self.state.add_client(self.a)
        self.state.add_client(self.b)
        self.state.set_nick(self.a, "alice")
        self.state.set_nick(self.b, "bob")

    def test_join_and_part(self):
        joined, members = self.state.join(self.a, "#room")
        self.assertTrue(joined)
        self.assertEqual(members, [self.a])
        self.state.join(self.b, "#room")
        parted, members = self.state.part(self.a, "#room")
        self.assertTrue(parted)
        self.assertIn(self.b, members)

    def test_channel_names_are_case_insensitive(self):
        joined, _ = self.state.join(self.a, "#Room")
        self.assertTrue(joined)
        joined, _ = self.state.join(self.a, "#room")
        self.assertFalse(joined)
        self.assertEqual(self.state.channel_members("#ROOM"), [self.a])

    def test_duplicate_nickname_is_rejected(self):
        with self.assertRaises(NicknameInUseError):
            self.state.set_nick(self.b, "ALICE")

    def test_remove_cleans_indexes(self):
        self.state.join(self.a, "#room")
        self.state.remove(self.a)
        self.assertIsNone(self.state.find_nick("alice"))
        self.assertEqual(self.state.channel_members("#room"), [])

    def test_disconnect_notifies_shared_peers_once(self):
        server = IRCServer()
        leaving_connection = DummyConnection()
        peer_connection = DummyConnection()
        leaving = ClientState(leaving_connection, ("::1", 1))
        peer = ClientState(peer_connection, ("::1", 2))
        server.state.add_client(leaving)
        server.state.add_client(peer)
        server.state.set_nick(leaving, "alice")
        server.state.set_nick(peer, "bob")
        server.state.join(leaving, "#one")
        server.state.join(peer, "#one")
        server.state.join(leaving, "#two")
        server.state.join(peer, "#two")

        server.disconnect(leaving, "bye")

        quit_messages = [
            item
            for item in peer_connection.messages
            if isinstance(item, IRCMessage) and item.command == "QUIT"
        ]
        self.assertEqual(len(quit_messages), 1)


if __name__ == "__main__":
    unittest.main()
