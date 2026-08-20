"""Provider seams.

Two protocols, not one, because discovery and state-mutation are not the same
capability and a future provider may implement them by different mechanisms.
IBM happens to satisfy both with job tags; nothing here says "tag", and that is
on purpose — the encoding is an adapter's private business.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..core.models import TrackedJob, TrackingState


@runtime_checkable
class JobSource(Protocol):
    """Discovers the jobs Qoffee is responsible for and their current state."""

    name: str

    def fetch_tracked(self) -> list[TrackedJob]:
        """Return every tracked job, with status and tracking state decoded.

        Must return all of them — no silent pagination cap. Must raise
        ProviderError (not return an empty list) if the service is
        unreachable, so that "nothing tracked" and "could not ask" stay
        distinguishable.
        """
        ...


@runtime_checkable
class TrackingStore(Protocol):
    """Persists what Qoffee knows, in whatever form the provider allows."""

    name: str

    def set_state(self, job: TrackedJob, state: TrackingState) -> None:
        """Record a new tracking state, preserving the user's own metadata."""
        ...

    def resolve(self, job: TrackedJob) -> None:
        """Stop tracking this job. Must be idempotent."""
        ...
