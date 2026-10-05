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

    def test_unicode_nickname_is_not_accepted(self):
        from common.protocol import valid_nickname

        self.assertFalse(valid_nickname("用户"))


if __name__ == "__main__":
    unittest.main()
