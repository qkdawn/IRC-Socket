"""IPv6 IRC bot client with registration, keep-alive and reconnect support."""

from __future__ import annotations

import logging
import socket
import threading

from common.irc_message import IRCMessage, message
from common.numerics import RPL_ENDOFNAMES, RPL_NAMREPLY, RPL_WELCOME
from common.protocol import irc_casefold, valid_nickname
from common.stream import IRCStreamDecoder, IRCStreamError

from .commands import BotCommandProcessor, CommandAction
from .state import BotState

logger = logging.getLogger(__name__)


class BotClient:
    def __init__(
        self,
        host: str = "fc00:1337::17",
        port: int = 6667,
        nickname: str = "SuperBot",
        channel: str = "#hello",
        reconnect_delay: float = 3.0,
    ) -> None:
        self.host, self.port, self.nickname, self.channel = (
            host,
            port,
            nickname,
            channel,
        )
        self.reconnect_delay = reconnect_delay
        self.state = BotState()
        self.commands = BotCommandProcessor(nickname)
        self.socket: socket.socket | None = None
        self.send_lock = threading.Lock()
        self.stopping = threading.Event()
        self._who_channel: str | None = None
        self._who_names: set[str] = set()
        self._who_pending = 0
        self._registered = False
        self._nick_attempt = 0

    def run(self) -> None:
        while not self.stopping.is_set():
            try:
                self.run_once()
            except (ConnectionError, OSError, IRCStreamError) as exc:
                logger.warning(
                    "Bot connection to [%s]:%s ended: %s", self.host, self.port, exc
                )
                self.close()
            except Exception:
                logger.exception("Unexpected bot protocol error")
                self.close()
                raise
            # A bounded delay avoids a tight reconnect loop when the server is
            # unavailable, while still allowing the bot to recover on its own.
            if not self.stopping.wait(self.reconnect_delay):
                continue

    def run_once(self) -> None:
        # NAMES from the previous session is no longer authoritative after a
        # reconnect; wait for the new server snapshot before handling commands.
        self.state.clear()
        self._who_channel = None
        self._who_names.clear()
        self._who_pending = 0
        self._registered = False
        self._nick_attempt = 0
        sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        self.socket = sock
        sock.settimeout(1.0)
        sock.connect((self.host, self.port))
        decoder = IRCStreamDecoder()
        self.send(message("NICK", self.nickname))
        self.send(message("USER", self.nickname, "0", "*", self.nickname))
        while not self.stopping.is_set():
            try:
                data = sock.recv(4096)
            except socket.timeout:
                continue
            if not data:
                raise ConnectionError("server closed connection")
            for incoming in decoder.feed(data):
                self.handle(incoming)

    def send(self, msg: IRCMessage) -> None:
        if self.socket is None:
            raise ConnectionError("bot is not connected")
        with self.send_lock:
            self.socket.sendall(msg.to_bounded_bytes())

    def handle(self, incoming: IRCMessage) -> None:
        command = incoming.command
        if command in {"432", "433"} and not self._registered:
            self._nick_attempt += 1
            if self._nick_attempt > 10:
                raise ConnectionError("nickname registration rejected repeatedly")
            base = self.nickname if valid_nickname(self.nickname) else "SuperBot"
            suffix = "_" + str(self._nick_attempt)
            self.nickname = base[:30 - len(suffix)] + suffix
            self.commands.nickname = self.nickname
            self.send(message("NICK", self.nickname))
            return
        if command == "PING":
            token = incoming.params[-1] if incoming.params else ""
            self.send(message("PONG", token))
            return
        if command == RPL_WELCOME:
            self._registered = True
            if incoming.params:
                self.nickname = incoming.params[0]
                self.commands.nickname = self.nickname
            # Registration completes only after the server sends 001; joining
            # earlier can be rejected by a compliant server.
            self.send(message("JOIN", self.channel))
            return
        if command == "303" and self._who_channel and len(incoming.params) >= 2:
            channel = self._who_channel
            self._who_names.update(incoming.params[-1].split())
            self._who_pending -= 1
            if self._who_pending > 0:
                return
            names = sorted(self._who_names)
            self._who_channel = None
            self._who_names.clear()
            for name in names:
                self.send(message("PRIVMSG", channel, f"WHO member: {name}"))
            self.send(message("PRIVMSG", channel, f"WHO complete: {len(names)} members"))
            return
        if command == RPL_NAMREPLY and len(incoming.params) >= 4:
            # A large channel may be split across several 353 replies. Keep
            # collecting names until 366 marks the end of this snapshot.
            channel = incoming.params[2]
            if not self.state.has_pending_names(channel):
                self.state.begin_names(channel)
            names = incoming.params[3].lstrip(":").split()
            self.state.add_names(
                channel,
                [name.lstrip("@+%~&") for name in names],
            )
            return
        if command == RPL_ENDOFNAMES and len(incoming.params) >= 2:
            self.state.finish_names(incoming.params[1])
            return
        if command == "JOIN" and incoming.prefix and incoming.params:
            nickname = incoming.prefix.split("!", 1)[0]
            channel = incoming.params[0]
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
        if command != "PRIVMSG" or len(incoming.params) < 2 or not incoming.prefix:
            return
        sender = incoming.prefix.split("!", 1)[0]
        target, text = incoming.params[0], incoming.params[1]
        if irc_casefold(target) == irc_casefold(self.nickname):
            self.send(message("PRIVMSG", sender, self.commands.private_reply()))
            return
        if irc_casefold(target) != irc_casefold(self.channel):
            return
        response = self.commands.channel_command(
            text, sender, self.state.members(target)
        )
        if response is CommandAction.REQUEST_WHO:
            if self._who_channel is None:
                self._who_channel = target
                self._who_names.clear()
                # miniircd's WHO reply has an unescaped IPv6 host parameter.
                # ISON avoids that malformed field and confirms known members online.
                names = sorted(self.state.members(target))
                batches = []
                selected = []
                for name in names:
                    candidate = message("ISON", *(selected + [name]))
                    if len(selected) >= 14 or len(candidate.to_bytes()) > 480:
                        batches.append(selected)
                        selected = []
                    selected.append(name)
                batches.append(selected or [self.nickname])
                self._who_pending = len(batches)
                for batch in batches:
                    self.send(message("ISON", *batch))
        elif response:
            self.send(message("PRIVMSG", target, response))

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
