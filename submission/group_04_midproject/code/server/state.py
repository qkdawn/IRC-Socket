"""Thread-safe in-memory IRC users, channels and routing state."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any

from .errors import NicknameInUseError
from common.protocol import irc_casefold


@dataclass(eq=False)
class ClientState:
    connection: Any
    address: tuple
    nick: str | None = None
    username: str | None = None
    realname: str | None = None
    channels: set[str] = field(default_factory=set)
    last_activity: float = field(default_factory=time.monotonic)
    ping_sent: float | None = None

    @property
    def registered(self) -> bool:
        return bool(self.nick and self.username)

    @property
    def prefix(self) -> str:
        nick = self.nick or "*"
        user = self.username or "unknown"
        host = self.address[0] if self.address else "unknown"
        return f"{nick}!{user}@{host}"


class IRCState:
    """Owns all mutable server state; callers must not retain internal sets."""

    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.clients: set[ClientState] = set()
        self.nicknames: dict[str, ClientState] = {}
        self.channels: dict[str, set[ClientState]] = {}

    def add_client(self, client: ClientState) -> None:
        with self.lock:
            self.clients.add(client)

    @staticmethod
    def _channel_key(channel: str) -> str:
        """IRC channel names are case-insensitive for routing and membership."""
        return irc_casefold(channel)

    def find_nick(self, nick: str) -> ClientState | None:
        with self.lock:
            return self.nicknames.get(irc_casefold(nick))

    def set_nick(self, client: ClientState, nick: str) -> str | None:
        with self.lock:
            # IRC nickname comparisons are case-insensitive, while preserving
            # the spelling the client chose for display and wire replies.
            old = client.nick
            if (
                irc_casefold(nick) in self.nicknames
                and self.nicknames[irc_casefold(nick)] is not client
            ):
                raise NicknameInUseError("nickname in use")
            if old:
                self.nicknames.pop(irc_casefold(old), None)
            client.nick = nick
            self.nicknames[irc_casefold(nick)] = client
            return old

    def set_user(self, client: ClientState, username: str, realname: str) -> None:
        with self.lock:
            client.username = username
            client.realname = realname

    def join(self, client: ClientState, channel: str) -> tuple[bool, list[ClientState]]:
        with self.lock:
            # Return a snapshot so the caller can release the state lock before
            # performing potentially blocking socket writes.
            channel_key = self._channel_key(channel)
            members = self.channels.setdefault(channel_key, set())
            if client in members:
                return False, list(members)
            members.add(client)
            client.channels.add(channel_key)
            return True, list(members)

    def part(self, client: ClientState, channel: str) -> tuple[bool, list[ClientState]]:
        with self.lock:
            channel_key = self._channel_key(channel)
            members = self.channels.get(channel_key)
            if not members or client not in members:
                return False, []
            members.remove(client)
            client.channels.discard(channel_key)
            recipients = list(members) + [client]
            if not members:
                self.channels.pop(channel_key, None)
            return True, recipients

    def channel_members(self, channel: str) -> list[ClientState]:
        with self.lock:
            return list(self.channels.get(self._channel_key(channel), set()))

    def channels_for(self, client: ClientState) -> list[str]:
        with self.lock:
            return list(client.channels)

    def direct_target(self, nick: str) -> ClientState | None:
        return self.find_nick(nick)

    def remove(self, client: ClientState) -> list[tuple[str, list[ClientState]]]:
        """Remove a client and return channels plus remaining recipients."""
        with self.lock:
            # Clean every index in one critical section so no later command can
            # route a message to a disconnected session.
            affected: list[tuple[str, list[ClientState]]] = []
            for channel in list(client.channels):
                members = self.channels.get(channel, set())
                members.discard(client)
                affected.append((channel, list(members)))
                if not members:
                    self.channels.pop(channel, None)
            client.channels.clear()
            self.clients.discard(client)
            if client.nick and self.nicknames.get(irc_casefold(client.nick)) is client:
                self.nicknames.pop(irc_casefold(client.nick), None)
            return affected
