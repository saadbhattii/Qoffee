"""Builds channels from configuration.

Credentials never live in configuration files — a channel is named in
settings, and its secret is read from the environment. This module is where
"you asked for slack but there is no SLACK_WEBHOOK" becomes a startup error
rather than a silent no-op discovered three hours later.
"""

from __future__ import annotations

import os

from .base import Channel
from .discord import DiscordChannel
from .ntfy import NtfyChannel
from .slack import SlackChannel


class ChannelConfigError(ValueError):
    pass


# name -> (env var holding the credential, constructor)
BUILDERS = {
    "discord": ("DISCORD_WEBHOOK", DiscordChannel),
    "slack": ("SLACK_WEBHOOK", SlackChannel),
    "ntfy": ("NTFY_URL", NtfyChannel),
}


def available() -> list[str]:
    return sorted(BUILDERS)


def build(names: list[str], env: dict[str, str] | None = None) -> list[Channel]:
    """Construct every named channel, or raise explaining exactly what is missing."""
    environ = env if env is not None else dict(os.environ)

    if not names:
        raise ChannelConfigError(
            "No notification channels configured. Set CHANNELS in "
            "qoffee/settings.py (or the CHANNELS env var) to one or more of: "
            f"{', '.join(available())}."
        )

    channels: list[Channel] = []
    for name in names:
        entry = BUILDERS.get(name)
        if entry is None:
            raise ChannelConfigError(
                f"Unknown channel {name!r}. Available: {', '.join(available())}."
            )
        env_key, factory = entry
        credential = (environ.get(env_key) or "").strip()
        if not credential:
            raise ChannelConfigError(
                f"Channel {name!r} is enabled but {env_key} is empty. Add it as a "
                "GitHub Actions secret."
            )
        if not credential.startswith(("http://", "https://")):
            raise ChannelConfigError(
                f"{env_key} does not look like a URL. Check the secret value."
            )
        channels.append(factory(credential))
    return channels
