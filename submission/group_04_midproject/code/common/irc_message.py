"""RFC 2812 style IRC message parsing and serialization."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


class IRCParseError(ValueError):
    """Raised when an IRC line cannot be represented as an IRC message."""


@dataclass(frozen=True)
class IRCMessage:
    """A single IRC message without its CRLF terminator."""

    command: str
    params: tuple[str, ...] = ()
    prefix: Optional[str] = None

    def __post_init__(self) -> None:
        command = self.command.strip()
        if not command or any(ch.isspace() for ch in command):
            raise IRCParseError("command must be a non-empty token")
        object.__setattr__(self, "command", command.upper())
        object.__setattr__(self, "params", tuple(self.params))
        if self.prefix is not None and (
            not self.prefix or any(ch.isspace() or ch in "\r\n" for ch in self.prefix)
        ):
            raise IRCParseError("prefix must be a non-empty token")
        if len(self.params) > 15:
            raise IRCParseError("IRC messages have at most 15 parameters")
        for param in self.params:
            if "\r" in param or "\n" in param:
                raise IRCParseError("parameters cannot contain CR or LF")

    @classmethod
    def parse(cls, line: str) -> "IRCMessage":
        """Parse one IRC line, keeping a colon-prefixed trailing field intact."""
        line = line.rstrip("\r\n")
        if not line:
            raise IRCParseError("empty IRC line")

        prefix = None
        if line.startswith(":"):
            try:
                prefix, line = line[1:].split(" ", 1)
            except ValueError as exc:
                raise IRCParseError("prefix is missing a command") from exc
            if not prefix:
                raise IRCParseError("empty prefix")

        line = line.lstrip(" ")
        if not line:
            raise IRCParseError("command is missing")
        if " :" in line:
            head, trailing = line.split(" :", 1)
            parts = head.split()
            parts.append(trailing)
        else:
            parts = line.split()
        if not parts:
            raise IRCParseError("command is missing")
        return cls(parts[0], tuple(parts[1:]), prefix)

    def serialize(self) -> str:
        """Return the wire representation without CRLF.

        Only the final parameter can contain spaces, so it is emitted as the
        IRC trailing field when needed. Keeping CRLF in ``to_bytes`` makes the
        message boundary explicit at the socket layer.
        """
        pieces = []
        if self.prefix is not None:
            pieces.append(f":{self.prefix}")
        pieces.append(self.command)
        if self.params:
            for index, param in enumerate(self.params):
                is_last = index == len(self.params) - 1
                if not is_last and (
                    not param
                    or any(ch.isspace() for ch in param)
                    or param.startswith(":")
                ):
                    raise IRCParseError(
                        "only the final parameter may contain spaces or start with ':'"
                    )
                if is_last and (not param or " " in param or param.startswith(":")):
                    # The leading colon here is the wire delimiter. Preserve a
                    # second colon when the logical value itself starts with one.
                    pieces.append(":" + param)
                else:
                    pieces.append(param)
        return " ".join(pieces)

    def to_bytes(self) -> bytes:
        return (self.serialize() + "\r\n").encode("utf-8")

    def to_bounded_bytes(
        self, max_line_bytes: int = 512, *, truncate_trailing: bool = False
    ) -> bytes:
        """Bound outgoing lines, optionally shortening a human-readable reason."""
        payload = self.to_bytes()
        if len(payload) <= max_line_bytes:
            return payload
        if not truncate_trailing or not self.params:
            raise IRCParseError("outgoing IRC line exceeds maximum length")
        empty = IRCMessage(self.command, (*self.params[:-1], ""), self.prefix)
        available = max_line_bytes - len(empty.to_bytes())
        if available < 0:
            raise IRCParseError("IRC routing fields exceed maximum length")
        # Cutting bytes can split a UTF-8 code point; discard only that tail.
        trailing = self.params[-1].encode("utf-8")[:available].decode("utf-8", errors="ignore")
        bounded = IRCMessage(self.command, (*self.params[:-1], trailing), self.prefix)
        return bounded.to_bytes()


def message(command: str, *params: str, prefix: Optional[str] = None) -> IRCMessage:
    return IRCMessage(command, tuple(params), prefix)
