"""ntfy channel — plain text push, no account required."""

from __future__ import annotations

import requests

from ..core.models import DeliveryResult, Message, Severity
from .base import SEVERITY_MARK, chunk

_LIMIT = 3800
_TIMEOUT = 15


class NtfyChannel:
    name = "ntfy"

    def __init__(self, topic_url: str, timeout: int = _TIMEOUT) -> None:
        self._url = topic_url
        self._timeout = timeout

    def _body(self, message: Message) -> list[str]:
        lines: list[str] = []
        for section in message.sections:
            # No markup at all: ntfy renders plain text.
            lines.append(f"{SEVERITY_MARK[section.severity]} {section.heading}")
            for item in section.items:
                lines.append(f"  {item.label} [{item.job_id}] {item.status_text}")
                if item.detail:
                    lines.append(f"    {item.detail}")
            lines.append("")
        return chunk(lines, _LIMIT)

    @staticmethod
    def _priority(message: Message) -> str:
        has_failure = any(s.severity is Severity.FAILURE for s in message.sections)
        return "high" if has_failure else "default"

    def send(self, message: Message) -> DeliveryResult:
        for index, block in enumerate(self._body(message)):
            title = message.title if index == 0 else f"{message.title} (cont. {index + 1})"
            headers = {
                "Title": title.encode("ascii", "replace").decode("ascii"),
                "Priority": self._priority(message),
            }
            try:
                response = requests.post(
                    self._url,
                    data=block.encode("utf-8"),
                    headers=headers,
                    timeout=self._timeout,
                )
            except requests.RequestException as exc:
                return DeliveryResult(self.name, False, str(exc))
            if response.status_code >= 300:
                return DeliveryResult(
                    self.name,
                    False,
                    f"HTTP {response.status_code}: {response.text[:200]}",
                )
        return DeliveryResult(self.name, True)
