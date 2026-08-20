"""Turn a set of jobs into a structured message.

Deliberately emits no markup. Discord wants **bold**, Slack wants *bold*, ntfy
wants plain text, and a future email channel wants HTML — so the choice of
syntax belongs to the channel, not here. This module decides *what* is said
and in what order; channels decide how it looks.
"""

from __future__ import annotations

from .models import Item, JobStatus, Message, Section, Severity, TrackedJob

_MAX_ERROR_CHARS = 400


def _item(job: TrackedJob) -> Item:
    detail = None
    if job.error_message:
        detail = job.error_message.strip()
        if len(detail) > _MAX_ERROR_CHARS:
            detail = detail[: _MAX_ERROR_CHARS - 1].rstrip() + "…"

    status_text = job.status.name
    if job.status is JobStatus.UNKNOWN and job.raw_status:
        status_text = f"UNKNOWN ({job.raw_status})"
    if job.backend:
        status_text = f"{status_text} on {job.backend}"

    return Item(
        label=job.label,
        job_id=job.id,
        status_text=status_text,
        detail=detail,
    )


def render(jobs: list[TrackedJob]) -> Message:
    """Group jobs into sections, ordered so failures read last.

    Failures go at the bottom on purpose: it is the part of the message a
    person scrolling on a phone actually lands on, and it is the part that
    needs action.
    """
    active = [j for j in jobs if j.status.is_active]
    done = [j for j in jobs if j.status is JobStatus.DONE]
    unknown = [j for j in jobs if j.status is JobStatus.UNKNOWN]
    errored = [j for j in jobs if j.status is JobStatus.ERROR]
    cancelled = [j for j in jobs if j.status is JobStatus.CANCELLED]

    sections: list[Section] = []

    def add(heading: str, severity: Severity, group: list[TrackedJob]) -> None:
        if group:
            sections.append(
                Section(
                    heading=f"{heading} ({len(group)})",
                    severity=severity,
                    items=tuple(_item(j) for j in group),
                )
            )

    add("In progress", Severity.ACTIVE, active)
    add("Done", Severity.SUCCESS, done)
    add("Unrecognized status", Severity.UNKNOWN, unknown)
    # ERROR and CANCELLED are split: one means resubmit and investigate, the
    # other usually means somebody or something stopped it deliberately.
    add("Failed", Severity.FAILURE, errored)
    add("Cancelled", Severity.FAILURE, cancelled)

    total = len(jobs)
    title = f"Qoffee — {total} job{'s' if total != 1 else ''} tracked"
    return Message(title=title, sections=tuple(sections))
