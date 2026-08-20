"""Invariants any provider adapter must uphold. Parametrized so a second
adapter inherits the whole suite for free."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from qoffee import settings
from qoffee.core.models import FAILED_CODE, JobStatus, TrackingState
from qoffee.providers.fake import FakeProvider

T = datetime(2026, 8, 20, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture(params=["fake"])
def provider(request):
    p = FakeProvider()
    p.add("job000000000000000001", "QUEUED")
    return p


def test_fetch_returns_normalized_enum_members(provider):
    for job in provider.fetch_tracked():
        assert isinstance(job.status, JobStatus)


def test_fetch_preserves_raw_status_for_diagnostics(provider):
    assert provider.fetch_tracked()[0].raw_status == "QUEUED"


def test_unknown_raw_status_maps_to_unknown_not_an_exception(provider):
    provider.add("job000000000000000002", "TELEPORTING")
    statuses = {j.id: j.status for j in provider.fetch_tracked()}
    assert statuses["job000000000000000002"] is JobStatus.UNKNOWN


def test_set_state_then_fetch_reflects_the_new_state(provider):
    job = provider.fetch_tracked()[0]
    provider.set_state(job, TrackingState(code="R"))
    assert provider.fetch_tracked()[0].tracking.code == "R"


def test_set_state_preserves_user_tags(provider):
    provider.add(
        "job000000000000000003", "QUEUED", tags=("qoffee", "name:Mine", "my-own-tag")
    )
    job = [j for j in provider.fetch_tracked() if j.id == "job000000000000000003"][0]
    provider.set_state(job, TrackingState(code="R"))
    tags = provider.tags_of("job000000000000000003")
    assert "my-own-tag" in tags and "name:Mine" in tags


def test_resolve_removes_the_job_from_discovery(provider):
    job = provider.fetch_tracked()[0]
    provider.resolve(job)
    assert provider.fetch_tracked() == []


def test_resolve_is_idempotent(provider):
    job = provider.fetch_tracked()[0]
    provider.resolve(job)
    provider.resolve(provider.jobs[job.id])
    assert provider.fetch_tracked() == []


def test_resolve_applies_the_resolved_marker(provider):
    job = provider.fetch_tracked()[0]
    provider.resolve(job)
    assert settings.RESOLVED_TAG in provider.tags_of(job.id)


def test_failure_state_survives_a_roundtrip(provider):
    job = provider.fetch_tracked()[0]
    provider.set_state(job, TrackingState(code=FAILED_CODE, failed_at=T))
    restored = provider.fetch_tracked()[0].tracking
    assert restored.code == FAILED_CODE
    assert restored.failed_at == T
