"""Protocol-level names and validation shared by client and server."""

IRC_COMMANDS = frozenset(
    {"NICK", "USER", "JOIN", "PART", "PRIVMSG", "NAMES", "QUIT", "PING", "PONG", "TIME"}
)
CHANNEL_PREFIXES = ("#", "&")


def is_channel(target: str) -> bool:
    """Return whether an IRC target uses a supported channel prefix."""
    return bool(target) and target.startswith(CHANNEL_PREFIXES)


def valid_nickname(nickname: str) -> bool:
    """Apply the compact nickname grammar needed by the coursework server."""
    if not 1 <= len(nickname) <= 30:
        return False
    if not (nickname[0].isalpha() or nickname[0] in "[]\\`_^{|}"):
        return False
    return all(ch.isalnum() or ch in "[]\\`_^{|}-" for ch in nickname)
