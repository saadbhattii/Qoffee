"""Resolve configuration once, validate it completely, then never look again.

Every value comes from ``settings.py`` and may be overridden by an environment
variable of the same name, which is how the Actions workflow injects secrets.
Validation happens before the provider is contacted, so a misconfiguration
costs a fast red run rather than a slow one that does work and then discovers
it cannot report the result.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import timedelta

from . import settings
from .channels import registry


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class Config:
    ibm_token: str
    ibm_instance: str | None
    channel_names: list[str]
    required_channels: set[str]
    failure_autoclear: timedelta | None
    redact_logs: bool


def _env(name: str, default):
    raw = os.environ.get(name)
    return default if raw is None or raw.strip() == "" else raw.strip()


def _as_bool(value, name: str) -> bool:
    if isinstance(value, bool):
        return value
    lowered = str(value).strip().lower()
    if lowered in ("1", "true", "yes", "on"):
        return True
    if lowered in ("0", "false", "no", "off"):
        return False
    raise ConfigError(f"{name} must be a boolean, got {value!r}")


def _as_list(value) -> list[str]:
    if isinstance(value, (list, tuple)):
        items = list(value)
    else:
        items = str(value).split(",")
    return [item.strip().lower() for item in items if item.strip()]


def load() -> Config:
    token = _env("IBM_TOKEN", "")
    if not token:
        raise ConfigError("IBM_TOKEN is not set. Add it as a GitHub Actions secret.")

    instance = _env("IBM_CRN", None)

    channel_names = _as_list(_env("CHANNELS", settings.CHANNELS))
    if not channel_names:
        raise ConfigError(
            "No channels configured. Set CHANNELS to one or more of: "
            f"{', '.join(registry.available())}."
        )
    unknown = [n for n in channel_names if n not in registry.BUILDERS]
    if unknown:
        raise ConfigError(
            f"Unknown channel(s): {', '.join(unknown)}. "
            f"Available: {', '.join(registry.available())}."
        )
    if len(set(channel_names)) != len(channel_names):
        raise ConfigError("CHANNELS contains duplicates.")

    required_raw = _as_list(_env("REQUIRED_CHANNELS", settings.REQUIRED_CHANNELS))
    # Default: the first channel is required. Something has to be, or a run
    # could untag a job having delivered the news precisely nowhere.
    required = set(required_raw) if required_raw else {channel_names[0]}
    stray = required - set(channel_names)
    if stray:
        raise ConfigError(
            f"REQUIRED_CHANNELS names channel(s) not in CHANNELS: {', '.join(sorted(stray))}."
        )

    raw_hours = _env("FAILURE_AUTOCLEAR_HOURS", settings.FAILURE_AUTOCLEAR_HOURS)
    try:
        hours = float(raw_hours)
    except (TypeError, ValueError):
        raise ConfigError(
            f"FAILURE_AUTOCLEAR_HOURS must be a number, got {raw_hours!r}"
        ) from None
    if hours < 0:
        raise ConfigError("FAILURE_AUTOCLEAR_HOURS cannot be negative.")
    autoclear = timedelta(hours=hours) if hours > 0 else None

    redact = _as_bool(_env("REDACT_LOGS", settings.REDACT_LOGS), "REDACT_LOGS")

    return Config(
        ibm_token=token,
        ibm_instance=instance,
        channel_names=channel_names,
        required_channels=required,
        failure_autoclear=autoclear,
        redact_logs=redact,
    )