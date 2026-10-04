"""TCP stream framing for IRC's CRLF-delimited messages."""

from __future__ import annotations

from .irc_message import IRCMessage, IRCParseError


class IRCStreamError(ValueError):
    """Raised for malformed or over-sized IRC stream data."""


class IRCStreamDecoder:
    """Incrementally converts arbitrary TCP chunks into IRC messages."""

    def __init__(self, max_line_bytes: int = 512) -> None:
        self.max_line_bytes = max_line_bytes
        self._buffer = bytearray()

    def feed(self, data: bytes) -> list[IRCMessage]:
        if not isinstance(data, (bytes, bytearray, memoryview)):
            raise TypeError("data must be bytes-like")
        self._buffer.extend(data)
        messages: list[IRCMessage] = []
        while True:
            # TCP preserves byte order but not application write boundaries;
            # decode every complete CRLF line and retain any unfinished tail.
            delimiter = self._buffer.find(b"\r\n")
            if delimiter < 0:
                if len(self._buffer) > self.max_line_bytes:
                    self._buffer.clear()
                    raise IRCStreamError("IRC line exceeds maximum length")
                break
            raw = bytes(self._buffer[:delimiter])
            del self._buffer[: delimiter + 2]
            if len(raw) + 2 > self.max_line_bytes:
                raise IRCStreamError("IRC line exceeds maximum length")
            try:
                messages.append(IRCMessage.parse(raw.decode("utf-8")))
            except (UnicodeDecodeError, IRCParseError) as exc:
                raise IRCStreamError(str(exc)) from exc
        return messages

    @property
    def buffered_bytes(self) -> bytes:
        return bytes(self._buffer)
