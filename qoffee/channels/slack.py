"""Slack incoming-webhook channel."""

from __future__ import annotations

import requests

from ..core.models import DeliveryResult, Message
from .base import SEVERITY_MARK, chunk

# Slack truncates a text block past 3000 characters.
_BLOCK_LIMIT = 2800
_TIMEOUT = 15


class SlackChannel:
    name = "slack"

    def __init__(self, webhook_url: str, timeout: int = _TIMEOUT) -> None:
        self._url = webhook_url
        self._timeout = timeout

    def _body(self, message: Message) -> list[str]:
        lines: list[str] = []
        for section in message.sections:
            mark = SEVERITY_MARK[section.severity]
            # Slack uses single asterisks for bold, not double.
            lines.append(f"{mark} *{section.heading}*")
            for item in section.items:
                lines.append(f"\u2022 {item.label} (`{item.job_id}`) \u2014 {item.status_text}")
                if item.detail:
                    lines.append(f"```{item.detail}```")
            lines.append("")
        return chunk(lines, _BLOCK_LIMIT)

    def send(self, message: Message) -> DeliveryResult:
        for index, block in enumerate(self._body(message)):
            header = message.title if index == 0 else f"{message.title} (cont. {index + 1})"
            payload = {"text": f"*{header}*\n{block}"}
            try:
                response = requests.post(self._url, json=payload, timeout=self._timeout)
            except requests.RequestException as exc:
                return DeliveryResult(self.name, False, str(exc))
            if response.status_code >= 300:
                return DeliveryResult(
                    self.name,
                    False,
                    f"HTTP {response.status_code}: {response.text[:200]}",
                )
        return DeliveryResult(self.name, True)
