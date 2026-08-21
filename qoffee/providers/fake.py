"""In-memory provider for tests.

Exists so the entire engine can be exercised with no network, no credentials
and no mocking library — including the interleavings that are impossible to
reproduce on demand against real hardware, like a DONE and a CANCELLED job
resolving in the same run.

Drive it with a script: a list of frames, one per run, each mapping job id to
the raw status the provider should report on that run.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from ..core.models import TrackedJob, TrackingState
from ..providers.ibm import (
    _strip_qoffee_tags,
    decode_name,
    decode_state,
    encode_state,
)
from .. import settings


@dataclass
class FakeProvider:
    """Implements both JobSource and TrackingStore over a dict."""

    name: str = "fake"
    jobs: dict[str, TrackedJob] = field(default_factory=dict)
    script: list[dict[str, str]] = field(default_factory=list)
    fail_on_fetch: bool = False
    fail_on_write: set[str] = field(default_factory=set)
    permanent_fail_on_write: set[str] = field(default_factory=set)
    writes: list[tuple[str, str, tuple[str, ...]]] = field(default_factory=list)
    _frame: int = 0

    # --- test helpers ---------------------------------------------------

    def add(
        self,
        job_id: str,
        raw_status: str,
        *,
        tags: tuple[str, ...] = (settings.TRACKING_TAG,),
        backend: str | None = "ibm_fake",
        error_message: str | None = None,
    ) -> None:
        from ..providers.ibm import normalize_status

        self.jobs[job_id] = TrackedJob(
            id=job_id,
            status=normalize_status(raw_status),
            raw_status=raw_status,
            tracking=decode_state(tags),
            name=decode_name(tags),
            backend=backend,
            provider=self.name,
            error_message=error_message,
            tags=tags,
        )

    def advance(self) -> None:
        """Apply the next frame of the script to the job set."""
        if self._frame >= len(self.script):
            return
        from ..providers.ibm import normalize_status

        for job_id, raw in self.script[self._frame].items():
            job = self.jobs.get(job_id)
            if job is None:
                continue
            self.jobs[job_id] = replace(
                job, status=normalize_status(raw), raw_status=raw
            )
        self._frame += 1

    def tags_of(self, job_id: str) -> tuple[str, ...]:
        return self.jobs[job_id].tags

    # --- JobSource ------------------------------------------------------

    def fetch_tracked(self) -> list[TrackedJob]:
        if self.fail_on_fetch:
            from ..core.engine import ProviderError

            raise ProviderError("fake fetch failure")
        return [
            j for j in self.jobs.values() if settings.TRACKING_TAG in j.tags
        ]

    # --- TrackingStore --------------------------------------------------

    def set_state(self, job: TrackedJob, state: TrackingState) -> None:
        self._guard(job.id)
        # Shared with the real adapter on purpose: a test double that
        # reimplements the logic it is standing in for stops being a contract.
        tags = _strip_qoffee_tags(job.tags)
        tags.append(settings.TRACKING_TAG)
        encoded = encode_state(state)
        if encoded:
            tags.append(encoded)
        self._commit(job.id, "set_state", tuple(tags))

    def resolve(self, job: TrackedJob) -> None:
        self._guard(job.id)
        tags = _strip_qoffee_tags(job.tags)
        if settings.RESOLVED_TAG:
            tags.append(settings.RESOLVED_TAG)
        self._commit(job.id, "resolve", tuple(tags))

    def _guard(self, job_id: str) -> None:
        from ..core.engine import PermanentWriteError, ProviderError

        # Permanent first: it subclasses ProviderError, so order matters.
        if job_id in self.permanent_fail_on_write:
            raise PermanentWriteError(f"fake permanent rejection for {job_id}.")
        if job_id in self.fail_on_write:
            raise ProviderError(f"fake write failure for {job_id}")

    def _commit(self, job_id: str, op: str, tags: tuple[str, ...]) -> None:
        self.writes.append((job_id, op, tags))
        current = self.jobs[job_id]
        self.jobs[job_id] = replace(
            current, tags=tags, tracking=decode_state(tags)
        )