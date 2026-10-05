"""One TCP client session, isolated from protocol state and dispatch."""

from __future__ import annotations

import logging
import socket
import threading

from common.irc_message import IRCMessage
from common.stream import IRCStreamDecoder, IRCStreamError

from .state import ClientState

logger = logging.getLogger(__name__)


class ClientSession:
    def __init__(self, server, sock: socket.socket, address: tuple) -> None:
        self.server = server
        self.socket = sock
        self.address = address
        self.client = ClientState(self, address)
        self.decoder = IRCStreamDecoder()
        self.send_lock = threading.Lock()
        self.closed = threading.Event()

    def start(self) -> None:
        self.server.state.add_client(self.client)
        threading.Thread(target=self.run, name=f"irc-client-{self.address}", daemon=True).start()

    def send(self, msg: IRCMessage) -> None:
        payload = msg.to_bytes()
        with self.send_lock:
            if not self.closed.is_set():
                self.socket.sendall(payload)

    def run(self) -> None:
        self.socket.settimeout(1.0)
        try:
            while not self.closed.is_set() and not self.server.stopping.is_set():
                try:
                    # A timeout lets the thread notice server shutdown without
                    # using a busy loop or blocking forever on a dead peer.
                    data = self.socket.recv(4096)
                except socket.timeout:
                    continue
                if not data:
                    break
                try:
                    # One recv may contain half a message or many messages;
                    # framing is deliberately delegated to the shared decoder.
                    messages = self.decoder.feed(data)
                except IRCStreamError as exc:
                    logger.warning("Malformed IRC input from %s: %s", self.address, exc)
                    self.server.send_error_line(self.client, "Malformed IRC line")
                    break
                for incoming in messages:
                    self.server.handlers.handle(self.client, incoming)
                    if self.closed.is_set():
                        break
        except (ConnectionError, OSError) as exc:
            logger.info("IRC client disconnected: %s (%s)", self.address, exc)
        except Exception:
            # An unexpected bug must be visible during VM testing, while the
            # finally block still guarantees state and socket cleanup.
            logger.exception("Unhandled IRC session error from %s", self.address)
        finally:
            # All exits, including malformed input and TCP resets, pass through
            # the same cleanup path so channel membership cannot become stale.
            self.server.disconnect(self.client, "Connection closed", announce=True)

    def close(self) -> None:
        if self.closed.is_set():
            return
        self.closed.set()
        try:
            self.socket.shutdown(socket.SHUT_RDWR)
        except OSError as exc:
            logger.debug("Socket shutdown already complete for %s: %s", self.address, exc)
        try:
            self.socket.close()
        except OSError as exc:
            logger.debug("Socket close failed for %s: %s", self.address, exc)
