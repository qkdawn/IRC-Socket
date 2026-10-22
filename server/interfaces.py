"""Structural contracts for command handling and client delivery."""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING, Protocol

from common.irc_message import IRCMessage

if TYPE_CHECKING:
    from .state import ClientState, IRCState


class ClientConnection(Protocol):
    """Enqueue bounded output; optional queue waits require no state lock."""

    def send(self, msg: IRCMessage, *, wait_for_space: bool = False) -> None: ...

    def close(self) -> None: ...


class HandlerServer(Protocol):
    state: IRCState
    server_name: str

    def monotonic(self) -> float: ...

    def send(
        self, client: ClientState, msg: IRCMessage, *, wait_for_space: bool = False
    ) -> None: ...

    def send_many(self, clients: Iterable[ClientState], msg: IRCMessage) -> None: ...

    def join_channel(self, client: ClientState, channel: str) -> bool: ...

    def part_channel(self, client: ClientState, channel: str, reason: str) -> bool: ...

    def set_nickname(self, client: ClientState, nick: str) -> str | None: ...

    def disconnect(
        self, client: ClientState, reason: str = "Client Quit", announce: bool = True
    ) -> None: ...
