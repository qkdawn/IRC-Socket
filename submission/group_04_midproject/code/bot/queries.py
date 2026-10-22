"""IRC query state and response generation, independent of sockets and clocks."""

from __future__ import annotations

from common.irc_message import IRCMessage, message
from common.numerics import RPL_LIST, RPL_LISTEND, RPL_LUSERCLIENT
from common.protocol import irc_casefold, is_channel


class BotQueries:
    WHO_TIMEOUT = 30.0
    QUERY_TIMEOUT = 30.0
    MAX_LISTED_CHANNELS = 10

    def __init__(self) -> None:
        self._who_channel: str | None = None
        self._who_names: set[str] = set()
        self._who_pending = 0
        self._who_started: float | None = None
        self._who_failed = False
        self._extra_queries: dict[str, tuple[str, float]] = {}
        self._listed_channels: list[tuple[str, str]] = []
        self._listed_count = 0

    def reset(self) -> None:
        """Discard all results and deadlines from a previous connection."""
        self._reset_who()
        self._reset_extra_queries()

    def _reset_who(self) -> None:
        self._who_channel = None
        self._who_names.clear()
        self._who_pending = 0
        self._who_started = None
        self._who_failed = False

    def _reset_extra_queries(self) -> None:
        self._extra_queries.clear()
        self._listed_channels.clear()
        self._listed_count = 0

    def start_who(
        self,
        channel: str,
        names: set[str],
        nickname: str,
        server_name: str,
        now: float,
    ) -> list[IRCMessage]:
        if self._who_channel is not None:
            return []
        self._who_channel = channel
        self._who_started = now
        # miniircd's WHO reply has an unescaped IPv6 host parameter. ISON
        # confirms known members online without depending on that field.
        batches: list[list[str]] = []
        selected: list[str] = []
        for name in sorted(names):
            candidate = message("ISON", *(selected + [name]))
            reply = message(
                "303", nickname, " ".join(selected + [name]), prefix=server_name
            )
            # Budget the reply prefix as well as the request and parameter cap.
            if (
                len(selected) >= 14
                or len(candidate.to_bytes()) > 512
                or len(reply.to_bytes()) > 512
            ):
                batches.append(selected)
                selected = []
            selected.append(name)
        batches.append(selected or [nickname])
        self._who_pending = len(batches)
        return [message("ISON", *batch) for batch in batches]

    def start(self, command: str, channel: str, now: float) -> list[IRCMessage]:
        if command not in {"LIST", "LUSERS"}:
            raise ValueError("expected LIST or LUSERS")
        if command in self._extra_queries:
            return [
                message(
                    "PRIVMSG",
                    channel,
                    f"{command} query already in progress; please retry.",
                )
            ]
        self._extra_queries[command] = (channel, now)
        return [message(command)]

    def check_timeouts(self, now: float) -> None:
        if (
            self._who_started is not None
            and now - self._who_started >= self.WHO_TIMEOUT
        ):
            self._reset_who()
            # The caller reconnects so late replies cannot complete a new query.
            raise TimeoutError("ISON query timed out")
        for command, (_, started) in self._extra_queries.items():
            if now - started >= self.QUERY_TIMEOUT:
                self._reset_extra_queries()
                raise TimeoutError(f"{command} query timed out")

    def handle(self, incoming: IRCMessage, nickname: str) -> list[IRCMessage] | None:
        """Return outgoing messages, or None when this is not a query reply."""
        if (
            not incoming.params
            or irc_casefold(incoming.params[0]) != irc_casefold(nickname)
        ):
            return None
        outgoing = self._handle_extra_reply(incoming)
        if outgoing is not None:
            return outgoing
        if (
            incoming.command in {"263", "417", "421", "461"}
            and len(incoming.params) >= 2
            and incoming.params[1].upper() == "ISON"
            and self._who_channel is not None
        ):
            self._who_failed = True
            return self._finish_who_batch()
        if (
            incoming.command == "303"
            and self._who_channel is not None
            and len(incoming.params) >= 2
        ):
            self._who_names.update(incoming.params[-1].split())
            return self._finish_who_batch()
        return None

    def _finish_who_batch(self) -> list[IRCMessage]:
        self._who_pending -= 1
        if self._who_pending > 0:
            return []
        channel = self._who_channel
        assert channel is not None
        names = sorted(self._who_names)
        failed = self._who_failed
        self._reset_who()
        if failed:
            return [
                message("PRIVMSG", channel, "WHO unavailable: server rejected ISON.")
            ]
        return [
            *(message("PRIVMSG", channel, f"WHO member: {name}") for name in names),
            message("PRIVMSG", channel, f"WHO complete: {len(names)} members"),
        ]

    def _handle_extra_reply(self, incoming: IRCMessage) -> list[IRCMessage] | None:
        params = incoming.params
        if incoming.command in {"263", "421", "461"} and len(params) >= 2:
            return self._reject_extra_query(params[1].upper())
        if incoming.command == RPL_LUSERCLIENT and len(params) >= 2:
            pending = self._extra_queries.pop("LUSERS", None)
            if pending is not None:
                return [message("PRIVMSG", pending[0], "NETWORK: " + params[-1])]
            return []
        return self._handle_list_reply(incoming)

    def _reject_extra_query(self, query: str) -> list[IRCMessage] | None:
        pending = self._extra_queries.pop(query, None)
        if pending is None:
            return None
        if query == "LIST":
            self._listed_channels.clear()
            self._listed_count = 0
        return [
            message(
                "PRIVMSG", pending[0], f"{query} unavailable: server rejected {query}."
            )
        ]

    def _handle_list_reply(self, incoming: IRCMessage) -> list[IRCMessage] | None:
        params = incoming.params
        pending = self._extra_queries.get("LIST")
        if pending is None:
            return None
        if incoming.command == RPL_LIST and len(params) >= 4:
            channel, count = params[1:3]
            if (
                is_channel(channel)
                and len(count) <= 10
                and count.isascii()
                and count.isdigit()
            ):
                self._listed_count += 1
                if len(self._listed_channels) < self.MAX_LISTED_CHANNELS:
                    self._listed_channels.append((channel, count))
            return []
        if incoming.command == RPL_LISTEND and len(params) >= 2:
            return self._finish_list(pending[0])
        return None

    def _finish_list(self, destination: str) -> list[IRCMessage]:
        del self._extra_queries["LIST"]
        outgoing = [
            message("PRIVMSG", destination, f"CHANNEL: {channel} ({count} users)")
            for channel, count in self._listed_channels
        ]
        outgoing.append(
            message(
                "PRIVMSG",
                destination,
                f"CHANNELS complete: {self._listed_count} channels "
                f"(showing {len(self._listed_channels)})",
            )
        )
        self._listed_channels.clear()
        self._listed_count = 0
        return outgoing
