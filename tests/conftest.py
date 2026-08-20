from __future__ import annotations

import pytest

from qoffee.logging_setup import reset_sensitive

from .factories import T0, make_job


@pytest.fixture(autouse=True)
def _clean_redaction_registry():
    """The redaction registry is process-global; leaking it across tests would
    make assertions depend on execution order."""
    reset_sensitive()
    yield
    reset_sensitive()


@pytest.fixture
def now():
    return T0


@pytest.fixture
def job_factory():
    return make_job
