"""Full engine, no network, no credentials.

These cover the sequences you cannot reproduce on demand against real
hardware — notably a DONE and a CANCELLED resolving in the same run, and a
delivery failure landing between the decision and the tag write.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from qoffee import settings
from qoffee.channels.fake import FakeChannel
from qoffee.core import engine
from qoffee.core.policy import PolicyConfig
from qoffee.providers.fake import FakeProvider

from ..factories import T0

NO_AUTOCLEAR = PolicyConfig(failure_autoclear=None)


def run(provider, channels, *, required=None, now=T0, cfg=NO_AUTOCLEAR, dry_run=False):
    return engine.run(
        source=provider,
        store=provider,
        channels=channels,
        required_channels=required if required is not None else {c.name for c in channels[:1]},
        policy_config=cfg,
        now=now,
        dry_run=dry_run,
    )


def test_no_tracked_jobs_is_a_clean_no_op():
    provider, channel = FakeProvider(), FakeChannel()
    assert run(provider, [channel]) == engine.EXIT_OK
    assert channel.sent == []
    assert provider.writes == []


def test_provider_failure_exits_two_and_touches_nothing():
    provider = FakeProvider(fail_on_fetch=True)
    channel = FakeChannel()
    assert run(provider, [channel]) == engine.EXIT_PROVIDER
    assert channel.sent == []


def test_happy_path_notifies_then_resolves_in_that_order():
    provider = FakeProvider()
    provider.add("job000000000000000001", "DONE", tags=("qoffee", "qoffee@R"))
    channel = FakeChannel()

    assert run(provider, [channel]) == engine.EXIT_OK
    assert len(channel.sent) == 1
    assert settings.RESOLVED_TAG in provider.tags_of("job000000000000000001")


def test_delivery_failure_leaves_every_tag_untouched():
    """The fail-safe ordering guarantee, end to end."""
    provider = FakeProvider()
    provider.add("job000000000000000001", "DONE", tags=("qoffee", "qoffee@R"))
    channel = FakeChannel(ok=False)

    assert run(provider, [channel]) == engine.EXIT_DELIVERY
    assert provider.writes == []
    assert provider.tags_of("job000000000000000001") == ("qoffee", "qoffee@R")


def test_channel_that_raises_is_treated_as_a_failure_not_a_crash():
    provider = FakeProvider()
    provider.add("job000000000000000001", "DONE", tags=("qoffee",))
    assert run(provider, [FakeChannel(raises=True)]) == engine.EXIT_DELIVERY
    assert provider.writes == []


def test_optional_channel_failure_does_not_block_resolution():
    provider = FakeProvider()
    provider.add("job000000000000000001", "DONE", tags=("qoffee",))
    required = FakeChannel(name="primary", ok=True)
    optional = FakeChannel(name="secondary", ok=False)

    code = run(provider, [required, optional], required={"primary"})
    assert code == engine.EXIT_OK
    assert settings.RESOLVED_TAG in provider.tags_of("job000000000000000001")


def test_required_channel_failure_blocks_even_when_another_succeeds():
    provider = FakeProvider()
    provider.add("job000000000000000001", "DONE", tags=("qoffee",))
    required = FakeChannel(name="primary", ok=False)
    optional = FakeChannel(name="secondary", ok=True)

    code = run(provider, [required, optional], required={"primary"})
    assert code == engine.EXIT_DELIVERY
    assert provider.writes == []


def test_done_and_cancelled_in_the_same_run_then_release_next_run():
    """The case the v0.2 README claimed was verified by hand exactly once.

    Run 1: the success clears, the cancellation is held so it does not share a
    message with a success. Run 2: batch is quiet, final failures-only message,
    backlog clears itself.
    """
    provider = FakeProvider()
    provider.add("job000000000000000001", "DONE", tags=("qoffee", "qoffee@R"))
    provider.add("job000000000000000002", "CANCELLED", tags=("qoffee", "qoffee@R"))
    channel = FakeChannel()

    assert run(provider, [channel]) == engine.EXIT_OK
    assert settings.RESOLVED_TAG in provider.tags_of("job000000000000000001")
    assert "qoffee" in provider.tags_of("job000000000000000002")

    assert run(provider, [channel], now=T0 + timedelta(minutes=15)) == engine.EXIT_OK
    assert len(channel.sent) == 2
    final = channel.sent[-1]
    assert [s.heading for s in final.sections] == ["Cancelled (1)"]
    assert settings.RESOLVED_TAG in provider.tags_of("job000000000000000002")


def test_failure_is_held_while_other_work_is_running():
    provider = FakeProvider()
    provider.add("job000000000000000002", "ERROR", tags=("qoffee", "qoffee@R"))
    provider.add("job000000000000000003", "RUNNING", tags=("qoffee", "qoffee@R"))
    channel = FakeChannel()

    assert run(provider, [channel]) == engine.EXIT_OK
    assert len(channel.sent) == 1  # the new failure

    for i in range(1, 20):
        assert run(provider, [channel], now=T0 + timedelta(hours=i)) == engine.EXIT_OK
    assert len(channel.sent) == 1, "a held failure must not re-notify every run"
    assert "qoffee" in provider.tags_of("job000000000000000002")


def test_backlog_clears_itself_when_the_last_job_finishes():
    """End to end: two failures accumulate behind a running job, then release
    together in one final failures-only message. No manual untagging."""
    provider = FakeProvider()
    provider.add("job000000000000000001", "ERROR", tags=("qoffee", "qoffee@R"))
    provider.add("job000000000000000002", "CANCELLED", tags=("qoffee", "qoffee@R"))
    provider.add("job000000000000000003", "RUNNING", tags=("qoffee", "qoffee@R"))
    channel = FakeChannel()

    run(provider, [channel])
    provider.jobs["job000000000000000003"] = provider.jobs["job000000000000000003"]

    # The running job completes and clears.
    provider.script = [{"job000000000000000003": "DONE"}]
    provider.advance()
    run(provider, [channel], now=T0 + timedelta(minutes=15))
    assert settings.RESOLVED_TAG in provider.tags_of("job000000000000000003")
    assert "qoffee" in provider.tags_of("job000000000000000001")

    # Now nothing is moving: final report, backlog released.
    run(provider, [channel], now=T0 + timedelta(minutes=30))
    final = channel.sent[-1]
    assert {s.heading for s in final.sections} == {"Failed (1)", "Cancelled (1)"}
    assert settings.RESOLVED_TAG in provider.tags_of("job000000000000000001")
    assert settings.RESOLVED_TAG in provider.tags_of("job000000000000000002")


def test_delivery_failure_on_the_final_run_keeps_the_backlog():
    """The release is gated on delivery: a Discord outage must not clear a
    backlog nobody saw."""
    provider = FakeProvider()
    provider.add("job000000000000000001", "ERROR", tags=("qoffee", "qoffee@F:1755691200"))
    dead = FakeChannel(ok=False)

    assert run(provider, [dead]) == engine.EXIT_DELIVERY
    assert provider.writes == []
    assert "qoffee" in provider.tags_of("job000000000000000001")

    live = FakeChannel()
    assert run(provider, [live], now=T0 + timedelta(minutes=15)) == engine.EXIT_OK
    assert settings.RESOLVED_TAG in provider.tags_of("job000000000000000001")


def test_queue_then_run_then_done_produces_three_messages_not_twenty():
    provider = FakeProvider()
    provider.add("job000000000000000001", "QUEUED", tags=("qoffee",))
    provider.script = [
        {"job000000000000000001": "QUEUED"},
        {"job000000000000000001": "QUEUED"},
        {"job000000000000000001": "RUNNING"},
        {"job000000000000000001": "RUNNING"},
        {"job000000000000000001": "DONE"},
    ]
    channel = FakeChannel()

    for i in range(6):
        run(provider, [channel], now=T0 + timedelta(minutes=15 * i))
        provider.advance()

    assert len(channel.sent) == 3


def test_autoclear_is_a_safety_net_for_a_batch_that_never_goes_quiet():
    provider = FakeProvider()
    provider.add("job000000000000000002", "ERROR", tags=("qoffee", "qoffee@R"))
    provider.add("job000000000000000003", "RUNNING", tags=("qoffee", "qoffee@R"))
    channel = FakeChannel()
    cfg = PolicyConfig(failure_autoclear=timedelta(hours=24))

    run(provider, [channel], cfg=cfg)
    assert len(channel.sent) == 1

    run(provider, [channel], cfg=cfg, now=T0 + timedelta(hours=25))
    assert len(channel.sent) == 1, "autoclear is cleanup, not news"
    assert settings.RESOLVED_TAG in provider.tags_of("job000000000000000002")


def test_dry_run_sends_nothing_and_writes_nothing():
    provider = FakeProvider()
    provider.add("job000000000000000001", "DONE", tags=("qoffee",))
    channel = FakeChannel()

    assert run(provider, [channel], dry_run=True) == engine.EXIT_OK
    assert channel.sent == []
    assert provider.writes == []


def test_one_job_failing_to_write_does_not_abandon_the_rest():
    provider = FakeProvider(fail_on_write={"job000000000000000001"})
    provider.add("job000000000000000001", "DONE", tags=("qoffee",))
    provider.add("job000000000000000002", "DONE", tags=("qoffee",))
    channel = FakeChannel()

    assert run(provider, [channel]) == engine.EXIT_OK
    assert settings.RESOLVED_TAG in provider.tags_of("job000000000000000002")
    assert "qoffee" in provider.tags_of("job000000000000000001")


def test_v02_tagged_job_migrates_without_intervention():
    """A bare 'qoffee' tag written by v0.2 must be picked up, not stranded."""
    provider = FakeProvider()
    provider.add("job000000000000000001", "RUNNING", tags=("qoffee",))
    channel = FakeChannel()

    assert run(provider, [channel]) == engine.EXIT_OK
    assert len(channel.sent) == 1
    assert "qoffee@R" in provider.tags_of("job000000000000000001")


def test_unknown_status_is_never_silently_resolved():
    provider = FakeProvider()
    provider.add("job000000000000000001", "TELEPORTING", tags=("qoffee",))
    channel = FakeChannel()

    assert run(provider, [channel]) == engine.EXIT_OK
    assert "qoffee" in provider.tags_of("job000000000000000001")
    assert settings.RESOLVED_TAG not in provider.tags_of("job000000000000000001")
