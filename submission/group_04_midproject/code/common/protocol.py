"""Protocol-level names and validation shared by client and server."""

IRC_COMMANDS = frozenset(
    {"NICK", "USER", "JOIN", "PART", "PRIVMSG", "NAMES", "QUIT", "PING", "PONG", "TIME", "ISON", "LIST", "LUSERS"}
)
CHANNEL_PREFIXES = ("#", "&")


def irc_casefold(name: str) -> str:
    """Apply RFC 1459 casemapping to nicknames and channel names."""
    return name.translate(str.maketrans("ABCDEFGHIJKLMNOPQRSTUVWXYZ[]\\^", "abcdefghijklmnopqrstuvwxyz{}|~"))


def is_channel(target: str) -> bool:
    """Return whether *target* is a valid channel name in this IRC subset.

    This subset accepts 2-50 characters, starting with '#' or '&', and only
    printable ASCII excluding spaces, commas, and colons. The ASCII restriction
    is a local choice; the 50-character limit follows RFC 2812. Sharing this
    check keeps the server and bot consistent about valid targets.
    """
    if not target or target[0] not in CHANNEL_PREFIXES:
        return False
    if not 2 <= len(target) <= 50:
        return False
    return all(33 <= ord(char) <= 126 and char not in ",:" for char in target)


def valid_nickname(nickname: str) -> bool:
    """Apply the compact nickname grammar supported by this server."""
    if not 1 <= len(nickname) <= 30:
        return False
    ascii_letters = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
    special = "[]\\`_^{|}"
    if not (nickname[0] in ascii_letters or nickname[0] in special):
        return False
    return all(ch in ascii_letters + "0123456789" + special + "-" for ch in nickname)


def valid_username(username: str) -> bool:
    """Apply the local 1-30 ASCII character limit for user prefix fields."""
    return 1 <= len(username) <= 30 and all(
        33 <= ord(char) <= 126 and char not in "!@:" for char in username
    )
