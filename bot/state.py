"""Bot-side channel membership tracking."""

from __future__ import annotations


class BotState:
    def __init__(self, nickname: str) -> None:
        self.nickname = nickname
        self.channels: dict[str, set[str]] = {}

    def joined(self, channel: str, nickname: str) -> None:
        # casefold keeps channel keys stable while preserving nickname spelling.
        self.channels.setdefault(channel.casefold(), set()).add(nickname)

    def left(self, channel: str, nickname: str) -> None:
        members = self.channels.get(channel.casefold())
        if members:
            members.discard(nickname)

    def renamed(self, old: str, new: str) -> None:
        for members in self.channels.values():
            if old in members:
                members.discard(old)
                members.add(new)

    def removed(self, nickname: str) -> None:
        for members in self.channels.values():
            members.discard(nickname)

    def members(self, channel: str) -> set[str]:
        return set(self.channels.get(channel.casefold(), set()))

    def replace_names(self, channel: str, names: list[str]) -> None:
        # NAMES is authoritative for the snapshot; later events update this set.
        self.channels[channel.casefold()] = set(names)
