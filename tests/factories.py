from __future__ import annotations

from datetime import datetime, timezone

from qoffee.core.models import JobStatus, TrackedJob, TrackingState

T0 = datetime(2026, 8, 20, 12, 0, 0, tzinfo=timezone.utc)


def make_job(
    job_id: str = "job000000000000000001",
    status: JobStatus = JobStatus.QUEUED,
    *,
    raw_status: str | None = None,
    code: str | None = None,
    failed_at: datetime | None = None,
    name: str | None = None,
    backend: str | None = "ibm_test",
    error_message: str | None = None,
    tags: tuple[str, ...] = ("qoffee",),
) -> TrackedJob:
    return TrackedJob(
        id=job_id,
        status=status,
        raw_status=raw_status if raw_status is not None else status.name,
        tracking=TrackingState(code=code, failed_at=failed_at),
        name=name,
        backend=backend,
        provider="test",
        error_message=error_message,
        tags=tags,
    )
