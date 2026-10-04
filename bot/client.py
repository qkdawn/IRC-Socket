"""IPv6 IRC bot client with registration, keep-alive and reconnect support."""

from __future__ import annotations

import socket
import threading
import time

from common.irc_message import IRCMessage, message
from common.numerics import RPL_NAMREPLY, RPL_TIME, RPL_WELCOME
from common.stream import IRCStreamDecoder, IRCStreamError
from .commands import BotCommandProcessor
from .state import BotState


class BotClient:
    def __init__(self, host: str = "fc00:1337::17", port: int = 6667, nickname: str = "SuperBot", channel: str = "#hello", reconnect_delay: float = 3.0) -> None:
        self.host, self.port, self.nickname, self.channel = host, port, nickname, channel
        self.reconnect_delay = reconnect_delay
        self.state = BotState(nickname)
        self.commands = BotCommandProcessor(nickname)
        self.socket: socket.socket | None = None
        self.send_lock = threading.Lock()
        self.stopping = threading.Event()
        self._time_channel: str | None = None

    def run(self) -> None:
        while not self.stopping.is_set():
            try:
                self.run_once()
            except (ConnectionError, OSError, IRCStreamError):
                self.close()
            # A bounded delay avoids a tight reconnect loop when the server is
            # unavailable, while still allowing the bot to recover on its own.
            if not self.stopping.wait(self.reconnect_delay):
                continue

    def run_once(self) -> None:
        sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        sock.settimeout(1.0)
        sock.connect((self.host, self.port))
        self.socket = sock
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
            self.socket.sendall(msg.to_bytes())

    def handle(self, incoming: IRCMessage) -> None:
        command = incoming.command
        if command == "PING":
            token = incoming.params[-1] if incoming.params else ""
            self.send(message("PONG", token))
            return
        if command == RPL_WELCOME:
            # Registration completes only after the server sends 001; joining
            # earlier can be rejected by a compliant server.
            self.send(message("JOIN", self.channel))
            return
        if command == RPL_NAMREPLY and len(incoming.params) >= 4:
            # NAMES is the initial snapshot; JOIN/PART/QUIT/NICK update it as
            # live events arrive after the snapshot.
            names = incoming.params[3].lstrip(":").split()
            self.state.replace_names(incoming.params[2], [name.lstrip("@+%~&") for name in names])
            return
        if command == RPL_TIME and self._time_channel:
            self.send(message("PRIVMSG", self._time_channel, incoming.params[-1]))
            self._time_channel = None
            return
        if command == "JOIN" and incoming.prefix:
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
            self.state.renamed(incoming.prefix.split("!", 1)[0], incoming.params[0])
            return
        if command != "PRIVMSG" or len(incoming.params) < 2 or not incoming.prefix:
            return
        sender = incoming.prefix.split("!", 1)[0]
        target, text = incoming.params[0], incoming.params[1]
        if target.casefold() == self.nickname.casefold():
            self.send(message("PRIVMSG", sender, self.commands.private_reply()))
            return
        if target.casefold() != self.channel.casefold():
            return
        response = self.commands.channel_command(text, sender, self.state.members(target))
        if response == "__REQUEST_TIME__":
            # TIME is a server query, so defer the channel reply until its 391
            # numeric arrives rather than inventing a local timestamp.
            self._time_channel = target
            self.send(message("TIME"))
        elif response:
            self.send(message("PRIVMSG", target, response))

    def close(self) -> None:
        sock, self.socket = self.socket, None
        if sock:
            try:
                sock.close()
            except OSError:
                pass

    def stop(self) -> None:
        self.stopping.set()
        self.close()
