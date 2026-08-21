"""IBM Quantum adapter.

The only module in the package that imports qiskit, knows what a tag is, or
knows IBM's status vocabulary. Everything it hands upward is a plain
``TrackedJob``.

Tag scheme
----------
Two tags carry Qoffee's state, both derived from ``settings.TRACKING_TAG``:

    qoffee              discovery. Present for the whole life of tracking.
    qoffee@R            state. Single letter for active states; ``F:<epoch>``
                        for a reported failure, so the autoclear window has
                        something to measure from.

Discovery is a separate tag from state because IBM's ``job_tags`` filter is an
exact match, not a prefix match — folding state into the discovery tag would
make the jobs unfindable the moment their state changed.

A bare ``qoffee`` with no state tag is exactly what a v0.2 job looks like, and
decodes to "tracked, never reported". Old jobs migrate for free.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from .. import settings
from ..core.engine import PermanentWriteError, ProviderError
from ..core.models import FAILED_CODE, JobStatus, TrackedJob, TrackingState

log = logging.getLogger(__name__)

# IBM's vocabulary -> ours. VALIDATING is folded into INITIALIZING: it is a
# pre-queue state and the distinction is not actionable for a watcher.
_STATUS_MAP: dict[str, JobStatus] = {
    "INITIALIZING": JobStatus.INITIALIZING,
    "VALIDATING": JobStatus.INITIALIZING,
    "QUEUED": JobStatus.QUEUED,
    "RUNNING": JobStatus.RUNNING,
    "DONE": JobStatus.DONE,
    "ERROR": JobStatus.ERROR,
    "CANCELLED": JobStatus.CANCELLED,
}


def normalize_status(raw: str | None) -> JobStatus:
    if raw is None:
        return JobStatus.UNKNOWN
    return _STATUS_MAP.get(str(raw).strip().upper(), JobStatus.UNKNOWN)


def _state_prefix() -> str:
    return f"{settings.TRACKING_TAG}{settings.STATE_SEPARATOR}"


def encode_state(state: TrackingState) -> str | None:
    """Render a tracking state as a tag, or None if there is nothing to store."""
    if state.code is None:
        return None
    if state.code == FAILED_CODE:
        stamp = state.failed_at or datetime.now(timezone.utc)
        return f"{_state_prefix()}{FAILED_CODE}:{int(stamp.timestamp())}"
    return f"{_state_prefix()}{state.code}"


def decode_state(tags: tuple[str, ...]) -> TrackingState:
    """Read tracking state out of a job's tags.

    Tolerant by design: a malformed or truncated state tag decodes to "tracked,
    never reported" rather than raising. The cost of that is one duplicate
    notification; the cost of raising would be a run that reports nothing.
    """
    prefix = _state_prefix()
    for tag in tags:
        if not tag.startswith(prefix):
            continue
        body = tag[len(prefix) :]
        if not body:
            return TrackingState()
        if body.startswith(f"{FAILED_CODE}:"):
            raw = body[len(FAILED_CODE) + 1 :]
            try:
                stamp = datetime.fromtimestamp(int(raw), tz=timezone.utc)
            except (ValueError, OverflowError, OSError):
                log.warning("unparseable failure timestamp in tag; backfilling")
                return TrackingState(code=FAILED_CODE, failed_at=None)
            return TrackingState(code=FAILED_CODE, failed_at=stamp)
        if body == FAILED_CODE:
            return TrackingState(code=FAILED_CODE, failed_at=None)
        return TrackingState(code=body[0])
    return TrackingState()


def decode_name(tags: tuple[str, ...]) -> str | None:
    for tag in tags:
        if tag.startswith(settings.NAME_TAG_PREFIX):
            label = tag[len(settings.NAME_TAG_PREFIX) :].strip()
            return label or None
    return None


def _strip_qoffee_tags(tags: tuple[str, ...]) -> list[str]:
    """Remove every tag Qoffee owns, preserving the user's own.

    RESOLVED_TAG is stripped too. Without that, re-tracking a finished job
    leaves ``qoffeed`` behind forever, and since IBM allows only five tags per
    job that silently burns a slot the user does not know is scarce.
    """
    prefix = _state_prefix()
    owned = {settings.TRACKING_TAG, settings.RESOLVED_TAG}
    return [t for t in tags if t not in owned and not t.startswith(prefix)]


class IBMProvider:
    """Implements both JobSource and TrackingStore against IBM Quantum."""

    name = "ibm"

    def __init__(self, service) -> None:
        self._service = service

    @classmethod
    def connect(cls, token: str, instance: str | None) -> "IBMProvider":
        try:
            from qiskit_ibm_runtime import QiskitRuntimeService
        except ImportError as exc:  # pragma: no cover - environment problem
            raise ProviderError("qiskit-ibm-runtime is not installed") from exc

        kwargs = {"channel": "ibm_quantum_platform", "token": token}
        if instance:
            kwargs["instance"] = instance
        try:
            service = QiskitRuntimeService(**kwargs)
        except Exception as exc:
            raise ProviderError(f"could not connect to IBM Quantum: {exc}") from exc
        return cls(service)

    # --- JobSource ------------------------------------------------------

    def fetch_tracked(self) -> list[TrackedJob]:
        try:
            # limit=None is load-bearing. The default is 10, which silently
            # hides the 11th tracked job — it would never be reported and
            # never untagged.
            raw_jobs = self._service.jobs(
                job_tags=[settings.TRACKING_TAG],
                pending=None,
                limit=None,
            )
        except Exception as exc:
            raise ProviderError(f"could not list jobs: {exc}") from exc

        return [self._to_tracked(job) for job in raw_jobs]

    def _to_tracked(self, job) -> TrackedJob:
        tags = tuple(job.tags or ())

        raw_status = self._safe(lambda: str(job.status()), default="")
        backend = self._safe(lambda: job.backend().name, default=None)
        created = self._safe(
            lambda: (job.metrics() or {}).get("timestamps", {}).get("created"),
            default=None,
        )
        submitted_at = None
        if created:
            try:
                submitted_at = datetime.fromisoformat(
                    str(created).replace("Z", "+00:00")
                )
            except ValueError:
                submitted_at = None

        status = normalize_status(raw_status)
        error_message = None
        if status is JobStatus.ERROR:
            error_message = self._safe(lambda: job.error_message(), default=None)

        return TrackedJob(
            id=job.job_id(),
            status=status,
            raw_status=raw_status,
            tracking=decode_state(tags),
            name=decode_name(tags),
            backend=backend,
            provider=self.name,
            submitted_at=submitted_at,
            error_message=error_message,
            tags=tags,
        )

    @staticmethod
    def _safe(fn, default):
        """Best-effort metadata read.

        A job that failed hard may not expose a backend or metrics at all, and
        losing an optional field must never cost us the notification.
        """
        try:
            return fn()
        except Exception:
            return default

    # --- TrackingStore --------------------------------------------------

    def set_state(self, job: TrackedJob, state: TrackingState) -> None:
        tags = _strip_qoffee_tags(job.tags)
        tags.append(settings.TRACKING_TAG)
        encoded = encode_state(state)
        if encoded:
            tags.append(encoded)
        self._write_tags(job, tags)

    def resolve(self, job: TrackedJob) -> None:
        tags = _strip_qoffee_tags(job.tags)
        if settings.RESOLVED_TAG:
            tags.append(settings.RESOLVED_TAG)
        self._write_tags(job, tags)

    def _write_tags(self, job: TrackedJob, tags: list[str]) -> None:
        for tag in tags:
            if len(tag) > settings.MAX_TAG_LENGTH:
                raise PermanentWriteError(
                    f"tag {tag!r} exceeds IBM's {settings.MAX_TAG_LENGTH}-character limit."
                )
        if len(tags) > settings.MAX_TAGS_PER_JOB:
            raise PermanentWriteError(
                f"job {job.id} would carry {len(tags)} tags; IBM allows "
                f"{settings.MAX_TAGS_PER_JOB}. Remove a tag from the job to keep tracking it."
            )
        # update_tags overwrites the whole list rather than appending, which is
        # why the user's own tags are carried through explicitly above.
        self._raw_job(job.id).update_tags(tags)

    def _raw_job(self, job_id: str):
        try:
            return self._service.job(job_id)
        except Exception as exc:
            raise ProviderError(f"could not retrieve job {job_id}: {exc}") from exc