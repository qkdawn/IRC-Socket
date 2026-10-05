"""Small, concurrent IPv6 IRC server for the coursework protocol subset."""

from __future__ import annotations

import logging
import socket
import threading
import time

from common.irc_message import message

from .client_session import ClientSession
from .handlers import IRCHandlers
from .state import ClientState, IRCState

logger = logging.getLogger(__name__)


class IRCServer:
    def __init__(
        self, host: str = "::", port: int = 6667, server_name: str = "coursework.local"
    ) -> None:
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
        # AF_INET6 is explicit: the coursework server must accept IPv6 clients
        # and bind to the unspecified address by default.
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
        try:
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

    def send(self, client: ClientState, msg) -> None:
        try:
            client.connection.send(msg)
        except (ConnectionError, OSError) as exc:
            logger.info("Unable to send to %s: %s", client.address, exc)
            self.disconnect(client, "Connection lost")

    def send_many(self, clients, msg) -> None:
        for client in list(clients):
            self.send(client, msg)

    def broadcast_user_channels(
        self, client: ClientState, msg, include_self: bool = False
    ) -> None:
        recipients = set()
        for channel in self.state.channels_for(client):
            recipients.update(self.state.channel_members(channel))
        if not include_self:
            recipients.discard(client)
        self.send_many(recipients, msg)

    def send_error_line(self, client: ClientState, detail: str) -> None:
        self.send(client, message("ERROR", detail, prefix=self.server_name))

    def disconnect(
        self, client: ClientState, reason: str = "Client Quit", announce: bool = True
    ) -> None:
        # State removal happens before notifications so concurrent commands no
        # longer consider this client a valid route or channel member.
        affected = self.state.remove(client)
        if announce and client.nick:
            quit_message = message("QUIT", reason, prefix=client.prefix)
            recipients = {
                recipient
                for _channel, channel_recipients in affected
                for recipient in channel_recipients
            }
            self.send_many(recipients, quit_message)
        client.connection.close()

    def _monitor_clients(self) -> None:
        while not self.stopping.wait(10):
            now = self.monotonic()
            with self.state.lock:
                clients = list(self.state.clients)
            for client in clients:
                if client.ping_sent is None and now - client.last_activity > 120:
                    # Start one outstanding probe. Re-sending every scan would
                    # keep moving the timeout forward and never evict dead peers.
                    # Record the probe before sendall so an immediate PONG
                    # cannot race with this assignment and get overwritten.
                    client.ping_sent = now
                    self.send(
                        client,
                        message("PING", self.server_name, prefix=self.server_name),
                    )
                if client.ping_sent is not None and now - client.ping_sent > 60:
                    self.disconnect(client, "Ping timeout")

    def stop(self) -> None:
        if self.stopping.is_set():
            return
        self.stopping.set()
        self.ready.clear()
        if self.socket:
            try:
                self.socket.close()
            except OSError as exc:
                logger.debug("Server listener close failed: %s", exc)
        with self.state.lock:
            clients = list(self.state.clients)
        for client in clients:
            self.disconnect(client, "Server shutting down", announce=False)
