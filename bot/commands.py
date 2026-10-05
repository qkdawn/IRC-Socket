"""Pure Bot command decisions, kept independent from sockets."""

from __future__ import annotations

import random
from enum import Enum, auto
from pathlib import Path


class CommandAction(Enum):
    REQUEST_TIME = auto()


class BotCommandProcessor:
    def __init__(self, nickname: str, facts_path: Path | None = None, rng=None) -> None:
        self.nickname = nickname
        self.rng = rng or random.Random()
        facts_path = facts_path or Path(__file__).with_name("data") / "facts.txt"
        try:
            self.facts = [
                line.strip()
                for line in facts_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
        except OSError:
            self.facts = [
                "The network is made of packets, and packets travel one hop at a time."
            ]

    def channel_command(
        self, text: str, sender: str, channel_members: set[str]
    ) -> str | CommandAction | None:
        if not text.startswith("!"):
            return None
        command, _, argument = text[1:].partition(" ")
        command = command.casefold()
        if command == "hello":
            return f"Hello, {sender}!"
        if command == "slap":
            target = argument.strip() if argument.strip() else ""
            folded_members = {name.casefold(): name for name in channel_members}
            bot_key = self.nickname.casefold()
            sender_key = sender.casefold()
            eligible = {
                name
                for key, name in folded_members.items()
                if key not in {bot_key, sender_key}
            }
            # The no-argument form excludes both the bot and requester. An
            # explicit absent target falls back to the requester as required.
            target_key = target.casefold()
            if target and target_key in folded_members and target_key != bot_key:
                chosen = folded_members[target_key]
            elif target:
                chosen = sender
            elif eligible:
                chosen = self.rng.choice(sorted(eligible))
            else:
                chosen = sender
            return f"{sender} slaps {chosen} around a bit with a large trout!"
        if command == "time":
            return CommandAction.REQUEST_TIME
        return None

    def private_reply(self) -> str:
        return self.rng.choice(self.facts)
