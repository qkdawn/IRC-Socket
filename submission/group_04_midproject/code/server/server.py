"""Small, concurrent IPv6 IRC server for a practical protocol subset."""

from __future__ import annotations

import logging
from collections import deque
import socket
import threading
import time
from collections.abc import Iterable

from common.irc_message import IRCMessage, message

from .client_session import ClientSession
from .handlers import IRCHandlers
from .state import ClientState, IRCState

logger = logging.getLogger(__name__)


class IRCServer:
    REGISTRATION_TIMEOUT = 30.0
    IDLE_TIMEOUT = 30.0
    PONG_TIMEOUT = 30.0

    def __init__(
        self, host: str = "::", port: int = 6667, server_name: str = "irc.local"
    ) -> None:
        if not 0 <= port <= 65535:
            raise ValueError("port must be between 0 and 65535")
        if (
            not 1 <= len(server_name) <= 63
            or not server_name.isascii()
            or any(not 33 <= ord(char) <= 126 or char == ":" for char in server_name)
        ):
            raise ValueError(
                "server_name must be 1-63 printable ASCII characters without spaces or ':'"
            )
        self.host = host
        self.port = port
        self.server_name = server_name
        self.state = IRCState()
        self.handlers = IRCHandlers(self)
        self.socket: socket.socket | None = None
        self.ready = threading.Event()
        self.stopping = threading.Event()
        self._monitor: threading.Thread | None = None

    @staticmethod
    def monotonic() -> float:
        return time.monotonic()

    def serve_forever(self) -> None:
        # AF_INET6 is explicit so this server accepts IPv6 clients
        # and bind to the unspecified address by default.
        try:
            # Publish the listener and readiness atomically with shutdown.
            with self.state.lock:
                if self.stopping.is_set():
                    return
                self.socket = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
                self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                self.socket.bind((self.host, self.port))
                self.socket.listen(100)
                self.socket.settimeout(1.0)
                self.ready.set()
                self._monitor = threading.Thread(
                    target=self._monitor_clients, name="irc-monitor", daemon=True
                )
                self._monitor.start()
            while not self.stopping.is_set():
                try:
                    sock, address = self.socket.accept()
                except socket.timeout:
                    continue
                except OSError:
                    if self.stopping.is_set():
                        break
                    raise
                ClientSession(self, sock, address).start()
        finally:
            self.stop()

    def send(self, client: ClientState, msg: IRCMessage) -> None:
        self.send_many((client,), msg)

    def send_many(self, clients: Iterable[ClientState], msg: IRCMessage) -> None:
        # Connection.send only enqueues; socket writes belong to each session.
        pending = deque([(list(clients), msg)])
        with self.state.lock:
            while pending:
                recipients, outgoing = pending.popleft()
                for client in recipients:
                    if client.disconnected:
                        continue
                    try:
                        client.connection.send(outgoing)
                    except (ConnectionError, OSError) as exc:
                        logger.info("Unable to send to %s: %s", client.address, exc)
                        peers = self._close_client(client)
                        if client.nick and peers:
                            pending.append(
                                (
                                    list(peers),
                                    message("QUIT", "Connection lost", prefix=client.prefix),
                                )
                            )

    def join_channel(self, client: ClientState, channel: str) -> bool:
        with self.state.lock:
            joined, members = self.state.join(client, channel)
            if joined:
                self.send_many(members, message("JOIN", channel, prefix=client.prefix))
        return joined

    def set_nickname(self, client: ClientState, nick: str) -> str | None:
        with self.state.lock:
            old_prefix = client.prefix
            old = self.state.set_nick(client, nick)
            if old and old != nick:
                recipients = {client}
                for channel in self.state.channels_for(client):
                    recipients.update(self.state.channel_members(channel))
                self.send_many(recipients, message("NICK", nick, prefix=old_prefix))
            return old

    def send_error_line(self, client: ClientState, detail: str) -> None:
        self.send(client, message("ERROR", detail, prefix=self.server_name))

    def disconnect(
        self, client: ClientState, reason: str = "Client Quit", announce: bool = True
    ) -> None:
        with self.state.lock:
            recipients = self._close_client(client)
            if announce and client.nick and recipients:
                self.send_many(recipients, message("QUIT", reason, prefix=client.prefix))

    def _close_client(self, client: ClientState) -> set[ClientState]:
        # Remove routes and close before any potentially blocking peer writes.
        affected = self.state.remove(client)
        client.connection.close()
        return {
            recipient
            for _channel, channel_recipients in affected
            for recipient in channel_recipients
        }

    def _monitor_clients(self) -> None:
        while not self.stopping.wait(1):
            self._check_idle_clients()

    def _check_idle_clients(self) -> None:
        now = self.monotonic()
        with self.state.lock:
            clients = list(self.state.clients)
        for client in clients:
            with self.state.lock:
                if client.disconnected:
                    continue
                if (
                    not client.registered
                    and now - client.connected_at >= self.REGISTRATION_TIMEOUT
                ):
                    # Keep expiration and removal atomic with NICK/USER updates.
                    self.disconnect(client, "Registration timeout", announce=False)
                    continue
                send_probe = (
                    client.ping_sent is None
                    and not client.ping_queued
                    and now - client.last_activity >= self.IDLE_TIMEOUT
                )
                if send_probe:
                    client.ping_queued = True
                timed_out = (
                    client.ping_sent is not None
                    and now - client.ping_sent >= self.PONG_TIMEOUT
                )
            if send_probe:
                self.send(
                    client, message("PING", self.server_name, prefix=self.server_name)
                )
            if timed_out:
                self.disconnect(client, "Ping timeout")

    def stop(self) -> None:
        with self.state.lock:
            if self.stopping.is_set():
                return
            self.stopping.set()
            self.ready.clear()
            clients = list(self.state.clients)
        if self.socket:
            try:
                self.socket.close()
            except OSError as exc:
                logger.debug("Server listener close failed: %s", exc)
        for client in clients:
            self.disconnect(client, "Server shutting down", announce=False)
