"""Opt-in smoke tests against the real IBM API.

Not part of the feedback loop. These exist to catch upstream API drift — a
renamed method, a changed status string — and are wired to manual dispatch
only. Run with: pytest -m live
"""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.live

TOKEN = os.environ.get("IBM_TOKEN")


@pytest.fixture(scope="module")
def provider():
    if not TOKEN:
        pytest.skip("IBM_TOKEN not set")
    from qoffee.providers.ibm import IBMProvider

    return IBMProvider.connect(TOKEN, os.environ.get("IBM_CRN"))


def test_fetch_tracked_returns_without_error(provider):
    jobs = provider.fetch_tracked()
    assert isinstance(jobs, list)


def test_every_returned_status_is_recognized(provider):
    """Fails loudly if IBM introduces a status we do not map."""
    from qoffee.core.models import JobStatus

    unmapped = [
        j.raw_status for j in provider.fetch_tracked() if j.status is JobStatus.UNKNOWN
    ]
    assert not unmapped, f"unmapped IBM statuses: {sorted(set(unmapped))}"
