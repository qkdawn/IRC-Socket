import unittest

from server.state import ClientState, IRCState


class DummyConnection:
    def send(self, _message):
        pass

    def close(self):
        pass


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
        with self.assertRaises(ValueError):
            self.state.set_nick(self.b, "ALICE")

    def test_remove_cleans_indexes(self):
        self.state.join(self.a, "#room")
        self.state.remove(self.a)
        self.assertIsNone(self.state.find_nick("alice"))
        self.assertEqual(self.state.channel_members("#room"), [])


if __name__ == "__main__":
    unittest.main()
