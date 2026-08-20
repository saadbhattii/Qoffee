"""In-memory channel for tests."""

from __future__ import annotations

from dataclasses import dataclass, field

from ..core.models import DeliveryResult, Message


@dataclass
class FakeChannel:
    name: str = "fake"
    ok: bool = True
    raises: bool = False
    sent: list[Message] = field(default_factory=list)

    def send(self, message: Message) -> DeliveryResult:
        if self.raises:
            raise RuntimeError("fake channel exploded")
        self.sent.append(message)
        return DeliveryResult(self.name, self.ok, None if self.ok else "fake failure")
