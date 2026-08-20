from __future__ import annotations

import pytest

from qoffee.channels.registry import ChannelConfigError, available, build


def test_zero_channels_is_a_startup_error():
    """A run that delivers nowhere is the worst failure this tool can have."""
    with pytest.raises(ChannelConfigError, match="No notification channels"):
        build([], env={})


def test_missing_credential_named_explicitly():
    with pytest.raises(ChannelConfigError, match="DISCORD_WEBHOOK"):
        build(["discord"], env={})


def test_non_url_credential_rejected():
    with pytest.raises(ChannelConfigError, match="does not look like a URL"):
        build(["discord"], env={"DISCORD_WEBHOOK": "hunter2"})


def test_unknown_channel_lists_the_alternatives():
    with pytest.raises(ChannelConfigError, match="Available"):
        build(["telegraph"], env={"X": "y"})


def test_builds_in_declared_order():
    channels = build(
        ["ntfy", "discord"],
        env={
            "NTFY_URL": "https://ntfy.sh/t",
            "DISCORD_WEBHOOK": "https://discord.com/api/webhooks/x",
        },
    )
    assert [c.name for c in channels] == ["ntfy", "discord"]


def test_every_registered_channel_is_buildable():
    for name in available():
        from qoffee.channels.registry import BUILDERS

        env_key, _ = BUILDERS[name]
        assert build([name], env={env_key: "https://example.invalid/x"})
