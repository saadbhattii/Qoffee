from __future__ import annotations

from datetime import timedelta

import pytest

from qoffee.config import ConfigError, load


@pytest.fixture
def base_env(monkeypatch):
    for key in (
        "IBM_TOKEN", "IBM_CRN", "CHANNELS", "REQUIRED_CHANNELS",
        "FAILURE_AUTOCLEAR_HOURS", "REDACT_LOGS",
        "DISCORD_WEBHOOK", "SLACK_WEBHOOK", "NTFY_URL",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("IBM_TOKEN", "tok")
    return monkeypatch


def test_missing_token_fails_fast(base_env):
    base_env.delenv("IBM_TOKEN")
    with pytest.raises(ConfigError, match="IBM_TOKEN"):
        load()


def test_defaults_load(base_env):
    cfg = load()
    assert cfg.channel_names == ["discord"]
    assert cfg.required_channels == {"discord"}
    assert cfg.failure_autoclear is None
    assert cfg.redact_logs is True


def test_first_channel_is_required_by_default(base_env):
    base_env.setenv("CHANNELS", "slack,discord,ntfy")
    assert load().required_channels == {"slack"}


def test_unknown_channel_rejected(base_env):
    base_env.setenv("CHANNELS", "carrier_pigeon")
    with pytest.raises(ConfigError, match="Unknown channel"):
        load()


def test_duplicate_channels_rejected(base_env):
    base_env.setenv("CHANNELS", "discord,discord")
    with pytest.raises(ConfigError, match="duplicates"):
        load()


def test_required_channel_not_in_channels_rejected(base_env):
    base_env.setenv("CHANNELS", "discord")
    base_env.setenv("REQUIRED_CHANNELS", "slack")
    with pytest.raises(ConfigError, match="not in CHANNELS"):
        load()


def test_autoclear_hours_parsed(base_env):
    base_env.setenv("FAILURE_AUTOCLEAR_HOURS", "24")
    assert load().failure_autoclear == timedelta(hours=24)


def test_autoclear_zero_disables(base_env):
    base_env.setenv("FAILURE_AUTOCLEAR_HOURS", "0")
    assert load().failure_autoclear is None


def test_negative_autoclear_rejected(base_env):
    base_env.setenv("FAILURE_AUTOCLEAR_HOURS", "-1")
    with pytest.raises(ConfigError, match="negative"):
        load()


def test_nonnumeric_autoclear_rejected(base_env):
    base_env.setenv("FAILURE_AUTOCLEAR_HOURS", "soon")
    with pytest.raises(ConfigError, match="must be a number"):
        load()


@pytest.mark.parametrize("value,expected", [("true", True), ("0", False), ("off", False)])
def test_redact_flag_parsing(base_env, value, expected):
    base_env.setenv("REDACT_LOGS", value)
    assert load().redact_logs is expected


def test_bad_bool_rejected(base_env):
    base_env.setenv("REDACT_LOGS", "maybe")
    with pytest.raises(ConfigError, match="boolean"):
        load()