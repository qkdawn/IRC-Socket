"""IRC command dispatch, validation and response routing."""

from __future__ import annotations

from datetime import datetime, timezone
import logging

from common.irc_message import IRCMessage, message
from common import numerics
from common.protocol import is_channel, valid_nickname

logger = logging.getLogger(__name__)


class IRCHandlers:
    def __init__(self, server) -> None:
        self.server = server

    def handle(self, client, incoming: IRCMessage) -> None:
        client.last_activity = self.server.monotonic()
        command = incoming.command
        if command not in {"NICK", "USER", "QUIT", "PING", "PONG"} and not client.registered:
            self.error(client, numerics.ERR_NOTREGISTERED, command)
            return
        # Keep each command in its own method so protocol parsing stays out of
        # socket code and individual IRC behaviors can be tested independently.
        handler = getattr(self, f"cmd_{command.lower()}", None)
        if handler is None:
            self.error(client, numerics.ERR_UNKNOWNCOMMAND, command, ":Unknown command")
            return
        # Expected input errors are handled by each command and become IRC
        # numerics. Unexpected programming errors are allowed to reach the
        # session boundary, where they are logged with their traceback.
        handler(client, incoming.params)

    def error(self, client, numeric: str, *params: str) -> None:
        target = client.nick or "*"
        self.server.send(client, message(numeric, target, *params, prefix=self.server.server_name))

    def cmd_nick(self, client, params: tuple[str, ...]) -> None:
        if not params or not params[0]:
            self.error(client, numerics.ERR_NONICKNAMEGIVEN, ":No nickname given")
            return
        nick = params[0]
        if not valid_nickname(nick):
            self.error(client, numerics.ERR_ERRONEUSNICKNAME, nick, ":Erroneous nickname")
            return
        old_prefix = client.prefix
        try:
            old = self.server.state.set_nick(client, nick)
        except ValueError:
            self.error(client, numerics.ERR_NICKNAMEINUSE, nick, ":Nickname is already in use")
            return
        if old and old != nick:
            # Other clients identify the old nickname from the message prefix;
            # the new nickname is carried as the NICK command parameter.
            self.server.broadcast_user_channels(client, message("NICK", nick, prefix=old_prefix), include_self=True)
        if client.registered and old is None:
            self.welcome(client)

    def cmd_user(self, client, params: tuple[str, ...]) -> None:
        if client.username is not None:
            self.error(client, numerics.ERR_ALREADYREGISTERED, ":You may not reregister")
            return
        if len(params) < 4:
            self.error(client, numerics.ERR_NEEDMOREPARAMS, "USER", ":Not enough parameters")
            return
        self.server.state.set_user(client, params[0], params[3])
        if client.registered:
            self.welcome(client)

    def welcome(self, client) -> None:
        nick = client.nick or "*"
        prefix = self.server.server_name
        replies = (
            message(numerics.RPL_WELCOME, nick,
                    f":Welcome to {self.server.server_name}", prefix=prefix),
            message(numerics.RPL_YOURHOST, nick,
                    f":Your host is {self.server.server_name}", prefix=prefix),
            message(numerics.RPL_CREATED, nick,
                    ":This server was created for coursework", prefix=prefix),
            message(numerics.RPL_MYINFO, nick, self.server.server_name,
                    "irc-mini", "io", "", prefix=prefix),
        )
        for reply in replies:
            self.server.send(client, reply)

    def cmd_join(self, client, params: tuple[str, ...]) -> None:
        if not params or not params[0]:
            self.error(client, numerics.ERR_NEEDMOREPARAMS, "JOIN", ":Not enough parameters")
            return
        for channel in params[0].split(","):
            if not is_channel(channel):
                self.error(client, numerics.ERR_NOSUCHCHANNEL, channel, ":No such channel")
                continue
            joined, members = self.server.state.join(client, channel)
            if not joined:
                continue
            # JOIN is echoed to the joining client as well as existing members;
            # NAMES then supplies the initial roster for clients joining late.
            self.server.send_many(members, message("JOIN", channel, prefix=client.prefix))
            self.send_names(client, channel)

    def cmd_part(self, client, params: tuple[str, ...]) -> None:
        if not params or not params[0]:
            self.error(client, numerics.ERR_NEEDMOREPARAMS, "PART", ":Not enough parameters")
            return
        reason = params[1] if len(params) > 1 else "Leaving"
        for channel in params[0].split(","):
            parted, members = self.server.state.part(client, channel)
            if not parted:
                self.error(client, numerics.ERR_NOTONCHANNEL, channel, ":You are not on that channel")
                continue
            self.server.send_many(members, message("PART", channel, reason, prefix=client.prefix))

    def cmd_names(self, client, params: tuple[str, ...]) -> None:
        channels = (
            params[0].split(",")
            if params and params[0]
            else self.server.state.channels_for(client)
        )
        for channel in channels:
            self.send_names(client, channel)

    def send_names(self, client, channel: str) -> None:
        names = " ".join(
            sorted(member.nick or "*"
                   for member in self.server.state.channel_members(channel))
        )
        nick = client.nick or "*"
        prefix = self.server.server_name
        self.server.send(
            client,
            message(numerics.RPL_NAMREPLY, nick, "=", channel,
                    f":{names}", prefix=prefix),
        )
        self.server.send(
            client,
            message(numerics.RPL_ENDOFNAMES, nick, channel,
                    ":End of /NAMES list.", prefix=prefix),
        )

    def cmd_privmsg(self, client, params: tuple[str, ...]) -> None:
        if len(params) < 2:
            self.error(client, numerics.ERR_NEEDMOREPARAMS, "PRIVMSG", ":Not enough parameters")
            return
        target, text = params[0], params[1]
        outgoing = message("PRIVMSG", target, text, prefix=client.prefix)
        if is_channel(target):
            members = self.server.state.channel_members(target)
            if client not in members:
                self.error(client, numerics.ERR_CANNOTSENDTOCHAN, target, ":Cannot send to channel")
                return
            # IRC channel messages are delivered to peers, not echoed back to
            # the sender; the client already knows what it submitted.
            self.server.send_many((member for member in members if member is not client), outgoing)
            return
        destination = self.server.state.direct_target(target)
        if destination is None:
            self.error(client, numerics.ERR_NOSUCHNICK, target, ":No such nick")
            return
        self.server.send(destination, outgoing)

    def cmd_ping(self, client, params: tuple[str, ...]) -> None:
        token = params[0] if params else self.server.server_name
        self.server.send(
            client,
            message("PONG", self.server.server_name, token,
                    prefix=self.server.server_name),
        )

    def cmd_pong(self, client, params: tuple[str, ...]) -> None:
        client.ping_sent = None

    def cmd_time(self, client, params: tuple[str, ...]) -> None:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        self.server.send(
            client,
            message(numerics.RPL_TIME, client.nick or "*",
                    self.server.server_name, f":{now}",
                    prefix=self.server.server_name),
        )

    def cmd_quit(self, client, params: tuple[str, ...]) -> None:
        reason = params[0] if params else "Client Quit"
        self.server.disconnect(client, reason)
