"""Provider-neutral value objects.

Nothing in this module imports a vendor SDK, and no vendor SDK object is ever
stored on one of these types. Adapters translate at the boundary; everything
downstream — policy, rendering, notification — sees only these.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import datetime


class JobStatus(enum.Enum):
    """Normalized lifecycle state.

    Vendor vocabularies map onto this at the adapter boundary. UNKNOWN is a
    first-class member rather than an error: a provider that invents a new
    status must degrade to "leave it alone and say so", never to a crash or,
    worse, a wrong guess about whether it is terminal.
    """

    INITIALIZING = "INITIALIZING"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    DONE = "DONE"
    ERROR = "ERROR"
    CANCELLED = "CANCELLED"
    UNKNOWN = "UNKNOWN"

    @property
    def is_terminal(self) -> bool:
        return self in (JobStatus.DONE, JobStatus.ERROR, JobStatus.CANCELLED)

    @property
    def is_failure(self) -> bool:
        return self in (JobStatus.ERROR, JobStatus.CANCELLED)

    @property
    def is_active(self) -> bool:
        return self in (
            JobStatus.INITIALIZING,
            JobStatus.QUEUED,
            JobStatus.RUNNING,
        )


# Single-character codes persisted in the provider's tracking store. Kept
# short because IBM caps a tag at 24 characters.
STATE_CODES: dict[JobStatus, str] = {
    JobStatus.INITIALIZING: "I",
    JobStatus.QUEUED: "Q",
    JobStatus.RUNNING: "R",
    JobStatus.UNKNOWN: "U",
}

# Terminal failures collapse to one code; which of ERROR/CANCELLED it was is
# re-read from the provider each run, so it does not need persisting.
FAILED_CODE = "F"


@dataclass(frozen=True)
class TrackingState:
    """What Qoffee last recorded about a job, decoded from the store.

    `code` is None for a job that is tracked but has never been reported —
    which is exactly the shape of a v0.2 tag, so old jobs migrate for free.
    """

    code: str | None = None
    failed_at: datetime | None = None

    @property
    def is_reported_failure(self) -> bool:
        return self.code == FAILED_CODE


@dataclass(frozen=True)
class TrackedJob:
    """One job, as the rest of the system sees it."""

    id: str
    status: JobStatus
    raw_status: str
    tracking: TrackingState = field(default_factory=TrackingState)
    name: str | None = None
    backend: str | None = None
    provider: str = "unknown"
    submitted_at: datetime | None = None
    error_message: str | None = None
    tags: tuple[str, ...] = ()

    @property
    def label(self) -> str:
        return self.name or self.id


# --- Actions ------------------------------------------------------------
#
# Inert descriptions of intent. plan() produces them; the executor applies
# them. Keeping them data means the whole decision layer is a pure function
# and the "what would this do?" question is answerable without side effects.


@dataclass(frozen=True)
class SetState:
    job: TrackedJob
    state: TrackingState
    reason: str
    requires_delivery: bool = True


@dataclass(frozen=True)
class Resolve:
    job: TrackedJob
    reason: str
    requires_delivery: bool = True


@dataclass(frozen=True)
class Leave:
    job: TrackedJob
    reason: str
    requires_delivery: bool = False


Action = SetState | Resolve | Leave


# --- Rendered message ---------------------------------------------------
#
# Structure only. No channel syntax: Discord wants **bold**, Slack wants
# *bold*, ntfy wants neither. Serialization belongs to the channel.


class Severity(enum.Enum):
    ACTIVE = "active"
    SUCCESS = "success"
    FAILURE = "failure"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class Item:
    label: str
    job_id: str
    status_text: str
    detail: str | None = None


@dataclass(frozen=True)
class Section:
    heading: str
    severity: Severity
    items: tuple[Item, ...]


@dataclass(frozen=True)
class Message:
    title: str
    sections: tuple[Section, ...]

    @property
    def is_empty(self) -> bool:
        return not self.sections


@dataclass(frozen=True)
class Plan:
    """Output of the decision layer."""

    notify: bool
    message: Message
    actions: tuple[Action, ...]

    def deliverable_actions(self) -> tuple[Action, ...]:
        return tuple(a for a in self.actions if not isinstance(a, Leave))


@dataclass(frozen=True)
class DeliveryResult:
    channel: str
    ok: bool
    detail: str | None = None
