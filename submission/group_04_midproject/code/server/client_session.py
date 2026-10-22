"""One TCP client session, isolated from protocol state and dispatch."""

from __future__ import annotations

import logging
from queue import Empty, Full, Queue
import socket
import threading
import time
from typing import TYPE_CHECKING

from common.irc_message import IRCMessage
from common.stream import IRCStreamDecoder, IRCStreamError

from .state import ClientState

if TYPE_CHECKING:
    from .server import IRCServer

logger = logging.getLogger(__name__)


class ClientSession:
    MAX_PENDING_MESSAGES = 256
    OUTPUT_QUEUE_TIMEOUT = 1.0

    def __init__(self, server: IRCServer, sock: socket.socket, address: tuple) -> None:
        self.server = server
        self.socket = sock
        self.address = address
        connected_at = server.monotonic()
        self.client = ClientState(
            self, address, last_activity=connected_at, connected_at=connected_at
        )
        self.decoder = IRCStreamDecoder()
        self.send_lock = threading.Condition()
        self.closed = threading.Event()
        self._outgoing: Queue[tuple[IRCMessage, bytes] | None] = Queue(
            self.MAX_PENDING_MESSAGES
        )
        self._writer: threading.Thread | None = None
        self._error_sent = False

    def start(self) -> None:
        with self.server.state.locked():
            # Shutdown snapshots clients under the same lock, so an accepted
            # socket cannot register after that snapshot and escape cleanup.
            if self.server.stopping.is_set():
                self.close()
                return
            self.server.state.add_client(self.client)
        try:
            threading.Thread(
                target=self.run, name=f"irc-client-{self.address}", daemon=True
            ).start()
        except BaseException:
            self.server.disconnect(
                self.client, "Session startup failed", announce=False
            )
            raise

    def send(self, msg: IRCMessage) -> None:
        self._enqueue(msg, wait_for_space=False)

    def send_reply(self, msg: IRCMessage) -> None:
        self.server.state.require_unlocked()
        self._enqueue(msg, wait_for_space=True)

    def _enqueue(self, msg: IRCMessage, *, wait_for_space: bool) -> None:
        payload = msg.to_bounded_bytes(
            truncate_trailing=msg.command in {"PART", "QUIT", "ERROR"}
        )
        deadline = time.monotonic() + self.OUTPUT_QUEUE_TIMEOUT
        with self.send_lock:
            while True:
                if self.closed.is_set():
                    raise ConnectionError("session is closed")
                try:
                    self._outgoing.put_nowait((msg, payload))
                    return
                except Full as exc:
                    if not wait_for_space:
                        raise ConnectionError("client output queue is full") from exc
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise ConnectionError("client output queue did not drain") from exc
                    # Only a reply producer outside the state lock may wait.
                    self.send_lock.wait(remaining)

    def _write_loop(self) -> None:
        try:
            while not self.closed.is_set():
                item = self._outgoing.get()
                with self.send_lock:
                    self.send_lock.notify_all()
                if item is None or self.closed.is_set():
                    return
                msg, payload = item
                if msg.command == "PING":
                    # Set before sendall so a fast PONG cannot beat this update.
                    self.server.state.start_ping(self.client, self.server.monotonic())
                self.socket.sendall(payload)
                if msg.command == "ERROR":
                    with self.send_lock:
                        self._error_sent = True
                        self.send_lock.notify_all()
        except (ConnectionError, OSError) as exc:
            logger.info("IRC write failed for %s: %s", self.address, exc)
            self.server.disconnect(self.client, "Connection lost")
        except Exception:
            logger.exception("Unhandled IRC writer error from %s", self.address)
            self.server.disconnect(self.client, "Output failure")

    def run(self) -> None:
        try:
            self.socket.settimeout(1.0)
            self._writer = threading.Thread(
                target=self._write_loop, name=f"irc-writer-{self.address}", daemon=True
            )
            self._writer.start()
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
                    with self.send_lock:
                        self.send_lock.wait_for(
                            lambda: self._error_sent or self.closed.is_set(),
                            timeout=self.OUTPUT_QUEUE_TIMEOUT,
                        )
                    break
                for incoming in messages:
                    if self.closed.is_set():
                        break
                    self.server.handlers.handle(self.client, incoming)
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
            if self._writer is not None and self._writer.ident is not None:
                self._writer.join(timeout=2)

    def close(self) -> None:
        with self.send_lock:
            if self.closed.is_set():
                return
            self.closed.set()
            # Discard pending output and wake an idle writer immediately.
            while True:
                try:
                    self._outgoing.get_nowait()
                except Empty:
                    break
            self._outgoing.put_nowait(None)
            self.send_lock.notify_all()
        try:
            self.socket.shutdown(socket.SHUT_RDWR)
        except OSError as exc:
            logger.debug(
                "Socket shutdown already complete for %s: %s", self.address, exc
            )
        try:
            self.socket.close()
        except OSError as exc:
            logger.debug("Socket close failed for %s: %s", self.address, exc)
