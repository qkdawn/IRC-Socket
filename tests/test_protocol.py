import unittest

from common.irc_message import IRCMessage, IRCParseError
from common.stream import IRCStreamDecoder, IRCStreamError


class ProtocolTests(unittest.TestCase):
    def test_parse_prefix_and_trailing_parameter(self):
        msg = IRCMessage.parse(":nick!u@h PRIVMSG #room :hello world\r\n")
        self.assertEqual(msg.prefix, "nick!u@h")
        self.assertEqual(msg.command, "PRIVMSG")
        self.assertEqual(msg.params, ("#room", "hello world"))
        self.assertEqual(msg.to_bytes(), b":nick!u@h PRIVMSG #room :hello world\r\n")

    def test_trailing_parameter_preserves_a_literal_leading_colon(self):
        msg = IRCMessage.parse("PRIVMSG #room ::hello\r\n")
        self.assertEqual(msg.params, ("#room", ":hello"))
        self.assertEqual(msg.to_bytes(), b"PRIVMSG #room ::hello\r\n")

    def test_stream_handles_split_and_coalesced_lines(self):
        decoder = IRCStreamDecoder()
        self.assertEqual(decoder.feed(b"NICK bo"), [])
        messages = decoder.feed(b"t\r\nPING :one\r\n")
        self.assertEqual([m.command for m in messages], ["NICK", "PING"])
        self.assertEqual(messages[1].params, ("one",))

    def test_stream_rejects_overlong_line(self):
        with self.assertRaises(IRCStreamError):
            IRCStreamDecoder(max_line_bytes=8).feed(b"NICK too-long\r\n")

    def test_invalid_message(self):
        with self.assertRaises(IRCParseError):
            IRCMessage.parse(":")

        with self.assertRaises(IRCParseError):
            IRCMessage("PRIVMSG", ("hello",), prefix="bad prefix")

    def test_message_params_are_normalized_to_an_immutable_tuple(self):
        msg = IRCMessage("PING", ["token"])
        self.assertEqual(msg.params, ("token",))

    def test_non_trailing_parameters_cannot_change_wire_arity(self):
        with self.assertRaises(IRCParseError):
            IRCMessage("CMD", ("has space", "tail")).serialize()

    def test_unicode_nickname_is_not_accepted(self):
        from common.protocol import valid_nickname

        self.assertFalse(valid_nickname("用户"))

    def test_channel_names_follow_rfc_shape(self):
        from common.protocol import is_channel

        self.assertTrue(is_channel("#room"))
        self.assertTrue(is_channel("&local"))
        self.assertFalse(is_channel("#"))
        self.assertFalse(is_channel("#with space"))
        self.assertFalse(is_channel("#room,other"))
        self.assertFalse(is_channel("#" + "x" * 50))


if __name__ == "__main__":
    unittest.main()
