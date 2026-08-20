"""The decision layer. Every rule Qoffee has about when to speak lives here."""

from __future__ import annotations

from datetime import timedelta

import pytest

from qoffee.core.models import (
    FAILED_CODE,
    JobStatus,
    Leave,
    Resolve,
    SetState,
)
from qoffee.core.policy import PolicyConfig, plan

from ..factories import T0, make_job

NO_AUTOCLEAR = PolicyConfig(failure_autoclear=None)


def kinds(p):
    return [type(a).__name__ for a in p.actions]


# --- transition-only notification ---------------------------------------


def test_first_sighting_of_active_job_notifies_and_records_state():
    p = plan([make_job(status=JobStatus.QUEUED, code=None)], NO_AUTOCLEAR, T0)
    assert p.notify is True
    assert kinds(p) == ["SetState"]
    assert p.actions[0].state.code == "Q"


def test_unchanged_active_job_stays_silent():
    p = plan([make_job(status=JobStatus.QUEUED, code="Q")], NO_AUTOCLEAR, T0)
    assert p.notify is False
    assert kinds(p) == ["Leave"]


def test_queued_to_running_is_a_transition():
    p = plan([make_job(status=JobStatus.RUNNING, code="Q")], NO_AUTOCLEAR, T0)
    assert p.notify is True
    assert p.actions[0].state.code == "R"


def test_bare_v02_tag_decodes_as_never_reported_and_notifies():
    """A job tagged by v0.2 has no state suffix. It must not be stranded."""
    p = plan([make_job(status=JobStatus.RUNNING, code=None)], NO_AUTOCLEAR, T0)
    assert p.notify is True
    assert kinds(p) == ["SetState"]


# --- success ------------------------------------------------------------


def test_done_notifies_and_resolves_immediately():
    p = plan([make_job(status=JobStatus.DONE, code="R")], NO_AUTOCLEAR, T0)
    assert p.notify is True
    assert kinds(p) == ["Resolve"]
    assert p.actions[0].requires_delivery is True


# --- failure holding and quiescence release ---------------------------


@pytest.mark.parametrize("status", [JobStatus.ERROR, JobStatus.CANCELLED])
def test_first_failure_notifies_and_pins_while_batch_is_busy(status):
    p = plan(
        [
            make_job("job000000000000000001", status, code="R"),
            make_job("job000000000000000002", JobStatus.RUNNING, code="R"),
        ],
        NO_AUTOCLEAR,
        T0,
    )
    assert p.notify is True
    action = {a.job.id: a for a in p.actions}["job000000000000000001"]
    assert isinstance(action, SetState)
    assert action.state.code == FAILED_CODE
    assert action.state.failed_at == T0


def test_held_failure_stays_visible_but_does_not_re_notify():
    p = plan(
        [
            make_job(
                "job000000000000000001",
                JobStatus.ERROR,
                code=FAILED_CODE,
                failed_at=T0,
            ),
            make_job("job000000000000000002", JobStatus.QUEUED, code="Q"),
        ],
        NO_AUTOCLEAR,
        T0 + timedelta(hours=3),
    )
    assert p.notify is False
    by_id = {a.job.id: a for a in p.actions}
    assert isinstance(by_id["job000000000000000001"], Leave)


def test_success_beside_a_failure_never_clears_the_failure():
    """A DONE landing next to a failure must not release it — the final
    message has to contain failures and nothing else."""
    p = plan(
        [
            make_job("job000000000000000001", JobStatus.DONE, code="R"),
            make_job(
                "job000000000000000002",
                JobStatus.ERROR,
                code=FAILED_CODE,
                failed_at=T0,
            ),
        ],
        NO_AUTOCLEAR,
        T0,
    )
    assert p.notify is True
    by_id = {a.job.id: a for a in p.actions}
    assert isinstance(by_id["job000000000000000001"], Resolve)
    assert isinstance(by_id["job000000000000000002"], Leave)
    assert any(s.heading.startswith("Failed") for s in p.message.sections)


def test_quiet_batch_notifies_and_releases_every_failure():
    """The run where nothing is moving: final report, then the backlog clears
    itself. Quiescence is a notifiable event in its own right."""
    p = plan(
        [
            make_job(
                "job000000000000000001", JobStatus.ERROR, code=FAILED_CODE, failed_at=T0
            ),
            make_job(
                "job000000000000000002",
                JobStatus.CANCELLED,
                code=FAILED_CODE,
                failed_at=T0,
            ),
        ],
        NO_AUTOCLEAR,
        T0 + timedelta(hours=1),
    )
    assert p.notify is True
    assert kinds(p) == ["Resolve", "Resolve"]
    assert all(a.requires_delivery for a in p.actions)


def test_final_message_contains_only_failures():
    p = plan(
        [
            make_job(
                "job000000000000000001", JobStatus.ERROR, code=FAILED_CODE, failed_at=T0
            )
        ],
        NO_AUTOCLEAR,
        T0 + timedelta(hours=1),
    )
    headings = [s.heading for s in p.message.sections]
    assert headings == ["Failed (1)"]


def test_lone_first_failure_is_reported_and_released_in_one_run():
    p = plan([make_job(status=JobStatus.ERROR, code="R")], NO_AUTOCLEAR, T0)
    assert p.notify is True
    assert kinds(p) == ["Resolve"]


def test_unknown_status_holds_failures_because_it_may_not_be_terminal():
    p = plan(
        [
            make_job("job000000000000000001", JobStatus.UNKNOWN, raw_status="X", code="U"),
            make_job(
                "job000000000000000002", JobStatus.ERROR, code=FAILED_CODE, failed_at=T0
            ),
        ],
        NO_AUTOCLEAR,
        T0,
    )
    by_id = {a.job.id: a for a in p.actions}
    assert isinstance(by_id["job000000000000000002"], Leave)


def test_failure_missing_timestamp_is_backfilled_silently():
    p = plan(
        [
            make_job(
                "job000000000000000001", JobStatus.ERROR, code=FAILED_CODE, failed_at=None
            ),
            make_job("job000000000000000002", JobStatus.RUNNING, code="R"),
        ],
        NO_AUTOCLEAR,
        T0,
    )
    assert p.notify is False
    action = {a.job.id: a for a in p.actions}["job000000000000000001"]
    assert isinstance(action, SetState)
    assert action.state.failed_at == T0
    assert action.requires_delivery is False


# --- autoclear safety net ---------------------------------------------
#
# Only reachable when the batch never goes quiet, i.e. work keeps arriving.


def _never_quiet(failed_at, code=FAILED_CODE):
    return [
        make_job("job000000000000000001", JobStatus.ERROR, code=code, failed_at=failed_at),
        make_job("job000000000000000002", JobStatus.RUNNING, code="R"),
    ]


def test_autoclear_does_not_fire_before_the_window():
    cfg = PolicyConfig(failure_autoclear=timedelta(hours=24))
    p = plan(_never_quiet(T0), cfg, T0 + timedelta(hours=23))
    by_id = {a.job.id: a for a in p.actions}
    assert isinstance(by_id["job000000000000000001"], Leave)


def test_autoclear_fires_at_the_window_and_stays_silent():
    cfg = PolicyConfig(failure_autoclear=timedelta(hours=24))
    p = plan(_never_quiet(T0), cfg, T0 + timedelta(hours=24))
    assert p.notify is False
    action = {a.job.id: a for a in p.actions}["job000000000000000001"]
    assert isinstance(action, Resolve)
    assert action.requires_delivery is False
    assert p.message.is_empty


def test_autoclear_disabled_by_default_holds_failure_while_work_continues():
    p = plan(_never_quiet(T0), NO_AUTOCLEAR, T0 + timedelta(days=3650))
    by_id = {a.job.id: a for a in p.actions}
    assert isinstance(by_id["job000000000000000001"], Leave)


# --- unknown ------------------------------------------------------------


def test_unknown_status_is_surfaced_but_never_resolved():
    p = plan(
        [make_job(status=JobStatus.UNKNOWN, raw_status="TELEPORTING", code=None)],
        NO_AUTOCLEAR,
        T0,
    )
    assert p.notify is True
    assert isinstance(p.actions[0], SetState)
    assert p.actions[0].state.code == "U"


def test_unknown_status_unchanged_stays_silent():
    p = plan(
        [make_job(status=JobStatus.UNKNOWN, raw_status="TELEPORTING", code="U")],
        NO_AUTOCLEAR,
        T0,
    )
    assert p.notify is False


# --- batch --------------------------------------------------------------


def test_empty_input_produces_nothing():
    p = plan([], NO_AUTOCLEAR, T0)
    assert p.notify is False
    assert p.actions == ()


def test_one_transition_pulls_the_whole_batch_into_the_message():
    """A message shows current state of everything, not just what changed."""
    p = plan(
        [
            make_job("job000000000000000001", JobStatus.DONE, code="R"),
            make_job("job000000000000000002", JobStatus.QUEUED, code="Q"),
        ],
        NO_AUTOCLEAR,
        T0,
    )
    assert p.notify is True
    ids = {i.job_id for s in p.message.sections for i in s.items}
    assert ids == {"job000000000000000001", "job000000000000000002"}
