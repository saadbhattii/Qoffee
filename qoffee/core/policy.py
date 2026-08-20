"""The decision layer. Pure: no I/O, no clock reads, no globals.

Every rule Qoffee has about *when* to speak and *when* to stop tracking lives
here and nowhere else. `now` is a parameter rather than a datetime.now() call
so that time-dependent behaviour is testable without sleeping.

Two independent mechanisms, deliberately kept separate:

  * WHEN TO SPEAK is transition-driven. An active job produces a message only
    when its state actually changes, so a six-hour queue costs one message
    rather than twenty-four.

  * WHEN TO RELEASE A FAILURE is quiescence-driven. A failure is held until
    nothing else in the batch is still moving, reported one last time, then
    released. The backlog clears itself; no manual untagging required.

The join between them is the rule that quiescence is *itself* a notifiable
event. Without it, the run in which the batch finally goes quiet contains no
job-level transition, so the failures would be released silently and the final
message would never arrive.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from .models import (
    FAILED_CODE,
    STATE_CODES,
    Action,
    JobStatus,
    Leave,
    Plan,
    Resolve,
    SetState,
    TrackedJob,
    TrackingState,
)
from .render import render


@dataclass(frozen=True)
class PolicyConfig:
    # Safety net only. Quiescence is the normal way failures clear; this
    # catches the pathological case where the batch never goes quiet because
    # new jobs keep arriving. None disables it.
    failure_autoclear: timedelta | None = None


def batch_is_quiet(jobs: list[TrackedJob]) -> bool:
    """True when nothing in the batch is still moving.

    A DONE job counts as *moving*, not settled: it resolves during this run,
    and its success would otherwise sit in the same message as the failures,
    diluting exactly the message you most need to read. Holding failures one
    more run guarantees the final message contains failures and nothing else.

    UNKNOWN also counts as moving. We cannot tell whether it is terminal, so
    releasing failures alongside it would be a guess.
    """
    return not any(
        job.status.is_active
        or job.status is JobStatus.DONE
        or job.status is JobStatus.UNKNOWN
        for job in jobs
    )


def plan(jobs: list[TrackedJob], cfg: PolicyConfig, now: datetime) -> Plan:
    actions: list[Action] = []
    reportable: list[TrackedJob] = []
    notify = False

    quiet = batch_is_quiet(jobs)

    for job in jobs:
        state = job.tracking

        # --- failures ---------------------------------------------------
        if job.status.is_failure:
            if quiet:
                # Last run of the batch. Report everything that failed, then
                # release it. requires_delivery=True means a Discord outage
                # leaves the tags in place and the whole thing repeats next
                # run rather than clearing unseen.
                notify = True
                reportable.append(job)
                actions.append(
                    Resolve(
                        job,
                        reason="batch quiet; released after final report",
                        requires_delivery=True,
                    )
                )
                continue

            if not state.is_reported_failure:
                # First sighting. Speak, and pin it so later runs know it has
                # already been announced.
                notify = True
                reportable.append(job)
                actions.append(
                    SetState(
                        job,
                        TrackingState(code=FAILED_CODE, failed_at=now),
                        reason="failure reported; held until batch is quiet",
                    )
                )
                continue

            if state.failed_at is None:
                # Pinned by an older version, or by a write that lost the
                # timestamp. Backfill silently so the safety net has something
                # to measure from. Not news, so no notification.
                reportable.append(job)
                actions.append(
                    SetState(
                        job,
                        TrackingState(code=FAILED_CODE, failed_at=now),
                        reason="backfilled missing failure timestamp",
                        requires_delivery=False,
                    )
                )
                continue

            if cfg.failure_autoclear is not None and (
                now - state.failed_at >= cfg.failure_autoclear
            ):
                # Safety net for a batch that never goes quiet. Silent, and
                # excluded from the message: it is cleanup, not news.
                actions.append(
                    Resolve(
                        job,
                        reason="autoclear safety net; batch never went quiet",
                        requires_delivery=False,
                    )
                )
                continue

            # Held. Visible in every message the batch produces, but not
            # itself a reason to send one.
            reportable.append(job)
            actions.append(Leave(job, reason="failure held; batch still active"))
            continue

        # --- success ----------------------------------------------------
        if job.status is JobStatus.DONE:
            notify = True
            reportable.append(job)
            actions.append(Resolve(job, reason="completed successfully"))
            continue

        # --- active / unknown -------------------------------------------
        code = STATE_CODES.get(job.status)
        if code is None:
            # A terminal status we do not recognize. Never guess at cleanup.
            reportable.append(job)
            actions.append(Leave(job, reason=f"unrecognized status {job.raw_status!r}"))
            continue

        reportable.append(job)
        if state.code != code:
            notify = True
            actions.append(
                SetState(
                    job,
                    TrackingState(code=code),
                    reason=f"state changed to {job.status.name}",
                )
            )
        else:
            actions.append(Leave(job, reason=f"unchanged in {job.status.name}"))

    message = render(reportable) if notify else render([])
    return Plan(notify=notify, message=message, actions=tuple(actions))
