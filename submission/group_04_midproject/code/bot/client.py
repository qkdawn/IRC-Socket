"""IPv6 IRC bot client with registration, keep-alive and reconnect support."""

from __future__ import annotations

import logging
from collections import deque
from collections.abc import Callable
from functools import partial
import socket
import threading
import time

from common.irc_message import IRCMessage, message
from common.numerics import (
    RPL_ENDOFNAMES,
    RPL_NAMREPLY,
    RPL_WELCOME,
)
from common.protocol import irc_casefold, is_channel, valid_nickname
from common.stream import IRCStreamDecoder, IRCStreamError

from .commands import BotCommandProcessor, CommandAction
from .queries import BotQueries
from .state import BotState

logger = logging.getLogger(__name__)


class BotClient:
    REGISTRATION_TIMEOUT = 30.0
    IDLE_TIMEOUT = 30.0
    PONG_TIMEOUT = 30.0
    NAMES_TIMEOUT = 30.0
    MAX_PENDING_COMMANDS = 100
    TEXT_CHUNK_BYTES = 256

    def __init__(
        self,
        host: str = "fc00:1337::17",
        port: int = 6667,
        nickname: str = "SuperBot",
        channel: str = "#hello",
        reconnect_delay: float = 3.0,
    ) -> None:
        if not 1 <= port <= 65535:
            raise ValueError("port must be between 1 and 65535")
        self.host, self.port, self.nickname, self.channel = (
            host,
            port,
            nickname if valid_nickname(nickname) else "SuperBot",
            channel,
        )
        if not is_channel(self.channel):
            raise ValueError("channel must be a valid IRC channel name")
        self.reconnect_delay = reconnect_delay
        self.state = BotState()
        self.commands = BotCommandProcessor(self.nickname)
        self.queries = BotQueries()
        self._action_handlers: dict[CommandAction, Callable[[IRCMessage], None]] = {
            CommandAction.WAIT_FOR_NAMES: self._defer_command,
            CommandAction.REQUEST_WHO: self._request_who,
            CommandAction.REQUEST_CHANNELS: partial(self._request_query, "LIST"),
            CommandAction.REQUEST_NETWORK: partial(self._request_query, "LUSERS"),
        }
        self.socket: socket.socket | None = None
        self.send_lock = threading.Lock()
        self.stopping = threading.Event()
        self._registered = False
        self._server_name = "s" * 63
        self._nick_attempt = 0
        self._names_started: float | None = None
        self._pending_commands: deque[IRCMessage] = deque()

    def run(self) -> None:
        while not self.stopping.is_set():
            try:
                self.run_once()
            except (ConnectionError, OSError, IRCStreamError) as exc:
                if not self.stopping.is_set():
                    logger.warning(
                        "Bot connection to [%s]:%s ended: %s", self.host, self.port, exc
                    )
            except Exception:
                logger.exception("Unexpected bot protocol error")
                raise
            finally:
                self.close()
            # A bounded delay avoids a tight reconnect loop when the server is
            # unavailable, while still allowing the bot to recover on its own.
            if not self.stopping.wait(self.reconnect_delay):
                continue

    def run_once(self) -> None:
        # Discard stale membership after reconnecting. JOIN events and the new
        # NAMES snapshot rebuild it; commands may arrive before NAMES completes.
        self.state.clear()
        self.queries.reset()
        self._names_started = None
        self._pending_commands.clear()
        self._registered = False
        self._nick_attempt = 0
        sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        self.socket = sock
        if self.stopping.is_set():
            return
        sock.settimeout(1.0)
        sock.connect((self.host, self.port))
        started = last_received = time.monotonic()
        ping_sent: float | None = None
        ping_token: str | None = None
        decoder = IRCStreamDecoder()
        self.send(message("NICK", self.nickname))
        self.send(message("USER", self.nickname, "0", "*", self.nickname))
        while not self.stopping.is_set():
            self._check_timeouts(started, ping_sent)
            now = time.monotonic()
            if (
                self._registered
                and ping_sent is None
                and now - last_received >= self.IDLE_TIMEOUT
            ):
                ping_token = f"bot-{now:.9f}"
                ping_sent = now
                self.send(message("PING", ping_token))
            try:
                data = sock.recv(4096)
            except socket.timeout:
                continue
            if not data:
                raise ConnectionError("server closed connection")
            self._check_timeouts(started, ping_sent)
            for incoming in decoder.feed(data):
                last_received = time.monotonic()
                if (
                    incoming.command == "PONG"
                    and incoming.params
                    and incoming.params[-1] == ping_token
                ):
                    ping_sent = None
                    ping_token = None
                self.handle(incoming)

    def _begin_names(self, channel: str) -> None:
        if not self.state.has_pending_names(channel):
            self.state.begin_names(channel)
            if irc_casefold(channel) == irc_casefold(self.channel):
                self._names_started = time.monotonic()

    def _check_timeouts(self, started: float, ping_sent: float | None) -> None:
        now = time.monotonic()
        if not self._registered and now - started >= self.REGISTRATION_TIMEOUT:
            raise TimeoutError("IRC registration timed out")
        if ping_sent is not None and now - ping_sent >= self.PONG_TIMEOUT:
            raise TimeoutError("server did not answer PING with matching PONG")
        if (
            self._names_started is not None
            and now - self._names_started >= self.NAMES_TIMEOUT
        ):
            self._names_started = None
            self._pending_commands.clear()
            raise TimeoutError("NAMES snapshot timed out")
        self.queries.check_timeouts(now)

    def send(self, msg: IRCMessage) -> None:
        with self.send_lock:
            sock = self.socket
            if sock is None:
                raise ConnectionError("bot is not connected")
            sock.sendall(msg.to_bounded_bytes())

    def handle(self, incoming: IRCMessage) -> None:
        command = incoming.command
        outgoing = self.queries.handle(incoming, self.nickname)
        if outgoing is not None:
            self._send_query_messages(outgoing)
            return
        if command in {"432", "433"} and not self._registered:
            self._nick_attempt += 1
            if self._nick_attempt > 10:
                raise ConnectionError("nickname registration rejected repeatedly")
            base = self.nickname if valid_nickname(self.nickname) else "SuperBot"
            suffix = "_" + str(self._nick_attempt)
            self.nickname = base[: 30 - len(suffix)] + suffix
            self.commands.nickname = self.nickname
            self.send(message("NICK", self.nickname))
            return
        if command == "PING":
            token = incoming.params[-1] if incoming.params else ""
            self.send(message("PONG", token))
            return
        if command == RPL_WELCOME:
            self._registered = True
            if incoming.prefix:
                self._server_name = incoming.prefix
            if incoming.params:
                self.nickname = incoming.params[0]
                self.commands.nickname = self.nickname
            # Registration completes only after the server sends 001; joining
            # earlier can be rejected by a compliant server.
            self._begin_names(self.channel)
            self.send(message("JOIN", self.channel))
            return
        if command == "PRIVMSG":
            self._handle_privmsg(incoming)
            return
        self._handle_channel_event(incoming)

    def _handle_channel_event(self, incoming: IRCMessage) -> None:
        command = incoming.command
        if command == RPL_NAMREPLY and len(incoming.params) >= 4:
            # A large channel may be split across several 353 replies. Keep
            # collecting names until 366 marks the end of this snapshot.
            channel = incoming.params[2]
            self._begin_names(channel)
            names = incoming.params[3].lstrip(":").split()
            self.state.add_names(
                channel,
                [name.lstrip("@+%~&") for name in names],
            )
            return
        if command == RPL_ENDOFNAMES and len(incoming.params) >= 2:
            channel = incoming.params[1]
            self.state.finish_names(channel)
            if irc_casefold(channel) == irc_casefold(self.channel):
                self._names_started = None
                pending = list(self._pending_commands)
                self._pending_commands.clear()
                for request in pending:
                    self.handle(request)
            return
        if command == "JOIN" and incoming.prefix and incoming.params:
            nickname = incoming.prefix.split("!", 1)[0]
            channel = incoming.params[0]
            if irc_casefold(nickname) == irc_casefold(self.nickname):
                self._begin_names(channel)
            self.state.joined(channel, nickname)
            return
        if command == "PART" and incoming.prefix and incoming.params:
            self.state.left(incoming.params[0], incoming.prefix.split("!", 1)[0])
            return
        if command == "QUIT" and incoming.prefix:
            self.state.removed(incoming.prefix.split("!", 1)[0])
            return
        if command == "NICK" and incoming.prefix and incoming.params:
            old = incoming.prefix.split("!", 1)[0]
            new = incoming.params[0]
            self.state.renamed(old, new)
            if irc_casefold(old) == irc_casefold(self.nickname):
                self.nickname = new
                self.commands.nickname = new
            return

    def _handle_privmsg(self, incoming: IRCMessage) -> None:
        if len(incoming.params) < 2 or not incoming.prefix:
            return
        sender = incoming.prefix.split("!", 1)[0]
        target, text = incoming.params[0], incoming.params[1]
        if irc_casefold(target) == irc_casefold(self.nickname):
            self._send_text(sender, self.commands.private_reply())
            return
        if irc_casefold(target) != irc_casefold(self.channel):
            return
        response = self.commands.channel_command(
            text,
            sender,
            self.state.members(target),
            members_complete=not self.state.has_pending_names(target),
        )
        if isinstance(response, CommandAction):
            self._action_handlers[response](incoming)
        elif response:
            self.send(message("PRIVMSG", target, response))

    def _defer_command(self, incoming: IRCMessage) -> None:
        if len(self._pending_commands) < self.MAX_PENDING_COMMANDS:
            self._pending_commands.append(incoming)
            return
        self.send(
            message(
                "PRIVMSG",
                incoming.params[0],
                "Channel roster is loading and the command queue is full; please retry.",
            )
        )

    def _request_who(self, incoming: IRCMessage) -> None:
        channel = incoming.params[0]
        self._send_query_messages(
            self.queries.start_who(
                channel, self.state.members(channel), self.nickname,
                self._server_name, time.monotonic(),
            )
        )

    def _request_query(self, command: str, incoming: IRCMessage) -> None:
        self._send_query_messages(
            self.queries.start(command, incoming.params[0], time.monotonic())
        )

    def _send_query_messages(self, outgoing: list[IRCMessage]) -> None:
        for reply in outgoing:
            if reply.command == "PRIVMSG":
                self._send_text(reply.params[0], reply.params[1])
            else:
                self.send(reply)

    def _send_text(self, target: str, text: str) -> None:
        payload = text.encode("utf-8")
        offset = 0
        # Reserve space for nickname, username and IPv6 host fields added by
        # the server. Split only at complete code points and retain all text.
        while offset < len(payload):
            text = payload[offset : offset + self.TEXT_CHUNK_BYTES].decode(
                "utf-8", errors="ignore"
            )
            self.send(message("PRIVMSG", target, text))
            offset += len(text.encode("utf-8"))

    def close(self) -> None:
        sock, self.socket = self.socket, None
        if sock:
            try:
                sock.close()
            except OSError as exc:
                logger.debug("Bot socket close failed: %s", exc)

    def stop(self) -> None:
        self.stopping.set()
        self.close()
