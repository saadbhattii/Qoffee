"""Notification channels.

A channel knows two things: how to turn a structured ``Message`` into whatever
markup its service expects, and how to post it. It knows nothing about jobs,
tags or tracking — which is what makes adding one a self-contained change.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..core.models import Message, Severity


@runtime_checkable
class Channel(Protocol):
    name: str

    def send(self, message: Message) -> "DeliveryResultLike":
        """Deliver the message. Must return rather than raise on failure."""
        ...


class DeliveryResultLike(Protocol):
    channel: str
    ok: bool
    detail: str | None


SEVERITY_MARK: dict[Severity, str] = {
    Severity.ACTIVE: "\u23f3",   # hourglass
    Severity.SUCCESS: "\u2705",  # check
    Severity.FAILURE: "\u274c",  # cross
    Severity.UNKNOWN: "\u2753",  # question
}


def chunk(lines: list[str], limit: int) -> list[str]:
    """Pack lines into blocks no longer than `limit` characters.

    Every service caps message length, and a large batch will hit it. Splitting
    on line boundaries here means a channel never has to truncate mid-job, and
    never has a post rejected for being oversized.
    """
    blocks: list[str] = []
    current: list[str] = []
    size = 0
    for line in lines:
        addition = len(line) + 1
        if current and size + addition > limit:
            blocks.append("\n".join(current))
            current, size = [], 0
        if len(line) > limit:
            line = line[: limit - 1] + "\u2026"
            addition = len(line) + 1
        current.append(line)
        size += addition
    if current:
        blocks.append("\n".join(current))
    return blocks or [""]
