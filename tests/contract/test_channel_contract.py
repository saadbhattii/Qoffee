"""Every channel must satisfy the same contract. Add one, it passes or it isn't done."""

from __future__ import annotations

import pytest

from qoffee.channels.discord import DiscordChannel
from qoffee.channels.ntfy import NtfyChannel
from qoffee.channels.slack import SlackChannel
from qoffee.core.models import JobStatus
from qoffee.core.render import render

from ..factories import make_job

CHANNELS = [
    lambda: DiscordChannel("https://example.invalid/hook"),
    lambda: SlackChannel("https://example.invalid/hook"),
    lambda: NtfyChannel("https://example.invalid/topic"),
]


class _Response:
    def __init__(self, status_code=204, text=""):
        self.status_code = status_code
        self.text = text


@pytest.fixture(params=CHANNELS)
def channel(request):
    return request.param()


@pytest.fixture
def big_message():
    return render(
        [
            make_job(f"job{i:018d}", JobStatus.ERROR, error_message="e" * 300)
            for i in range(60)
        ]
    )


def test_channel_declares_a_name(channel):
    assert isinstance(channel.name, str) and channel.name


def test_success_returns_ok(channel, monkeypatch):
    monkeypatch.setattr(
        f"{type(channel).__module__}.requests.post", lambda *a, **k: _Response()
    )
    result = channel.send(render([make_job()]))
    assert result.ok is True
    assert result.channel == channel.name


def test_http_error_returns_not_ok_rather_than_raising(channel, monkeypatch):
    monkeypatch.setattr(
        f"{type(channel).__module__}.requests.post",
        lambda *a, **k: _Response(500, "server on fire"),
    )
    result = channel.send(render([make_job()]))
    assert result.ok is False
    assert result.detail


def test_network_error_returns_not_ok_rather_than_raising(channel, monkeypatch):
    import requests

    def boom(*a, **k):
        raise requests.RequestException("no route to host")

    monkeypatch.setattr(f"{type(channel).__module__}.requests.post", boom)
    result = channel.send(render([make_job()]))
    assert result.ok is False


def test_large_batch_is_split_and_every_part_respects_the_limit(
    channel, big_message, monkeypatch
):
    posts = []

    def capture(*args, **kwargs):
        posts.append(kwargs)
        return _Response()

    monkeypatch.setattr(f"{type(channel).__module__}.requests.post", capture)
    assert channel.send(big_message).ok is True
    assert len(posts) > 1, "a 60-job batch must be split, not truncated"
    for post in posts:
        payload = post.get("json") or {}
        data = post.get("data")
        blob = str(payload) if payload else data.decode("utf-8")
        assert len(blob) < 6000


def test_partial_failure_midway_reports_failure(channel, big_message, monkeypatch):
    calls = {"n": 0}

    def flaky(*a, **k):
        calls["n"] += 1
        return _Response() if calls["n"] == 1 else _Response(500, "nope")

    monkeypatch.setattr(f"{type(channel).__module__}.requests.post", flaky)
    assert channel.send(big_message).ok is False
