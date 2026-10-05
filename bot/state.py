"""Bot-side channel membership tracking."""

from __future__ import annotations


class BotState:
    def __init__(self) -> None:
        self.channels: dict[str, set[str]] = {}

    def joined(self, channel: str, nickname: str) -> None:
        # casefold keeps channel keys stable while preserving nickname spelling.
        members = self.channels.setdefault(channel.casefold(), set())
        if self._matching_name(members, nickname) is None:
            members.add(nickname)

    @staticmethod
    def _matching_name(members: set[str], nickname: str) -> str | None:
        nickname_key = nickname.casefold()
        return next((name for name in members if name.casefold() == nickname_key), None)

    def left(self, channel: str, nickname: str) -> None:
        members = self.channels.get(channel.casefold())
        if members:
            existing = self._matching_name(members, nickname)
            if existing is not None:
                members.discard(existing)

    def renamed(self, old: str, new: str) -> None:
        for members in self.channels.values():
            existing = self._matching_name(members, old)
            if existing is not None:
                members.discard(existing)
                members.add(new)

    def removed(self, nickname: str) -> None:
        for members in self.channels.values():
            existing = self._matching_name(members, nickname)
            if existing is not None:
                members.discard(existing)

    def members(self, channel: str) -> set[str]:
        return set(self.channels.get(channel.casefold(), set()))

    def clear(self) -> None:
        """Discard membership learned from a previous TCP connection."""
        self.channels.clear()

    def replace_names(self, channel: str, names: list[str]) -> None:
        # NAMES is authoritative for the snapshot; later events update this set.
        self.channels[channel.casefold()] = set(names)
