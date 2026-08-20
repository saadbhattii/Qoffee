from __future__ import annotations

import pytest

from qoffee.cli import main
from qoffee.core import engine


@pytest.fixture
def clean_env(monkeypatch):
    for key in (
        "IBM_TOKEN", "IBM_CRN", "CHANNELS", "REQUIRED_CHANNELS",
        "FAILURE_AUTOCLEAR_HOURS", "REDACT_LOGS", "TRACKING_TAG",
        "DISCORD_WEBHOOK", "SLACK_WEBHOOK", "NTFY_URL",
    ):
        monkeypatch.delenv(key, raising=False)
    return monkeypatch


def test_missing_token_exits_config(clean_env):
    assert main([]) == engine.EXIT_CONFIG


def test_missing_webhook_exits_config_before_contacting_provider(clean_env):
    clean_env.setenv("IBM_TOKEN", "tok")
    assert main([]) == engine.EXIT_CONFIG


def test_check_config_succeeds_without_touching_the_provider(clean_env):
    clean_env.setenv("IBM_TOKEN", "tok")
    clean_env.setenv("DISCORD_WEBHOOK", "https://discord.com/api/webhooks/x")
    assert main(["--check-config"]) == engine.EXIT_OK


def test_token_is_never_echoed_to_the_log(clean_env, capsys):
    secret = "supersecrettoken1234567890"
    clean_env.setenv("IBM_TOKEN", secret)
    clean_env.setenv("DISCORD_WEBHOOK", "https://discord.com/api/webhooks/x")
    main(["--check-config"])
    assert secret not in capsys.readouterr().out
