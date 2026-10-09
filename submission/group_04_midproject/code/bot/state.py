"""Bot-side channel membership tracking."""

from __future__ import annotations

from common.protocol import irc_casefold


class BotState:
    def __init__(self) -> None:
        self.channels: dict[str, set[str]] = {}
        self._names_in_progress: dict[str, set[str]] = {}
        self._names_events: dict[str, list[tuple[str, tuple[str, ...]]]] = {}

    def joined(self, channel: str, nickname: str) -> None:
        self._record_event(channel, "joined", channel, nickname)
        # Keep IRC-equivalent keys stable while preserving nickname spelling.
        members = self.channels.setdefault(irc_casefold(channel), set())
        if self._matching_name(members, nickname) is None:
            members.add(nickname)

    @staticmethod
    def _matching_name(members: set[str], nickname: str) -> str | None:
        nickname_key = irc_casefold(nickname)
        return next((name for name in members if irc_casefold(name) == nickname_key), None)

    def left(self, channel: str, nickname: str) -> None:
        self._record_event(channel, "left", channel, nickname)
        members = self.channels.get(irc_casefold(channel))
        if members:
            existing = self._matching_name(members, nickname)
            if existing is not None:
                members.discard(existing)

    def renamed(self, old: str, new: str) -> None:
        for channel in self._names_in_progress:
            self._record_event(channel, "renamed", old, new)
        for members in self.channels.values():
            existing = self._matching_name(members, old)
            if existing is not None:
                members.discard(existing)
                members.add(new)

    def removed(self, nickname: str) -> None:
        for channel in self._names_in_progress:
            self._record_event(channel, "removed", nickname)
        for members in self.channels.values():
            existing = self._matching_name(members, nickname)
            if existing is not None:
                members.discard(existing)

    def members(self, channel: str) -> set[str]:
        return set(self.channels.get(irc_casefold(channel), set()))

    def clear(self) -> None:
        """Discard membership learned from a previous TCP connection."""
        self.channels.clear()
        self._names_in_progress.clear()
        self._names_events.clear()

    def _record_event(self, channel: str, event: str, *args: str) -> None:
        events = self._names_events.get(irc_casefold(channel))
        if events is not None:
            events.append((event, args))

    def begin_names(self, channel: str) -> None:
        self._names_in_progress[irc_casefold(channel)] = set()
        self._names_events[irc_casefold(channel)] = []

    def add_names(self, channel: str, names: list[str]) -> None:
        if not self.has_pending_names(channel):
            self.begin_names(channel)
        pending = self._names_in_progress[irc_casefold(channel)]
        for name in names:
            if self._matching_name(pending, name) is None:
                pending.add(name)

    def has_pending_names(self, channel: str) -> bool:
        return irc_casefold(channel) in self._names_in_progress

    def finish_names(self, channel: str) -> None:
        channel_key = irc_casefold(channel)
        if channel_key not in self._names_in_progress:
            return
        names = self._names_in_progress.pop(channel_key, set())
        self.channels[channel_key] = names
        # Apply events after the entire snapshot, including events preceding a
        # later 353 chunk that still contains an old nickname.
        events = self._names_events.pop(channel_key, [])
        for event, args in events:
            if event == "renamed":
                old, new = args
                existing = self._matching_name(names, old)
                if existing is not None:
                    names.discard(existing)
                    names.add(new)
            elif event == "removed":
                existing = self._matching_name(names, args[0])
                if existing is not None:
                    names.discard(existing)
            else:
                getattr(self, event)(*args)

    def replace_names(self, channel: str, names: list[str]) -> None:
        # NAMES is authoritative for the snapshot; later events update this set.
        self.begin_names(channel)
        self.add_names(channel, names)
        self.finish_names(channel)
