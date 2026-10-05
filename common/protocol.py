"""Protocol-level names and validation shared by client and server."""

IRC_COMMANDS = frozenset(
    {"NICK", "USER", "JOIN", "PART", "PRIVMSG", "NAMES", "QUIT", "PING", "PONG", "TIME"}
)
CHANNEL_PREFIXES = ("#", "&")


def is_channel(target: str) -> bool:
    """Return whether *target* is a valid channel name in this IRC subset.

    RFC 2812 limits channel names to 50 characters and reserves spaces,
    commas, colons, and control characters because they have wire-level
    meaning.  Keeping this check in the shared protocol module prevents the
    server and bot from quietly disagreeing about valid targets.
    """
    if not target or target[0] not in CHANNEL_PREFIXES:
        return False
    if not 2 <= len(target) <= 50:
        return False
    return all(33 <= ord(char) <= 126 and char not in ",:" for char in target)


def valid_nickname(nickname: str) -> bool:
    """Apply the compact nickname grammar needed by the coursework server."""
    if not 1 <= len(nickname) <= 30:
        return False
    ascii_letters = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
    special = "[]\\`_^{|}"
    if not (nickname[0] in ascii_letters or nickname[0] in special):
        return False
    return all(ch in ascii_letters + "0123456789" + special + "-" for ch in nickname)
