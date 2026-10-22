"""Structural contracts for command handling and client delivery."""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING, Protocol

from common.irc_message import IRCMessage

if TYPE_CHECKING:
    from .state import ClientState, IRCState


class ClientConnection(Protocol):
    def send(self, msg: IRCMessage) -> None: ...

    def close(self) -> None: ...


class HandlerServer(Protocol):
    state: IRCState
    server_name: str

    def monotonic(self) -> float: ...

    def send(self, client: ClientState, msg: IRCMessage) -> None: ...

    def send_many(self, clients: Iterable[ClientState], msg: IRCMessage) -> None: ...

    def join_channel(self, client: ClientState, channel: str) -> bool: ...

    def broadcast_user_channels(
        self, client: ClientState, msg: IRCMessage, include_self: bool = False
    ) -> None: ...

    def disconnect(
        self, client: ClientState, reason: str = "Client Quit", announce: bool = True
    ) -> None: ...
