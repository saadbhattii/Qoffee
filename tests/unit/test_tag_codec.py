"""Tag encoding is IBM's business, but getting it wrong strands live jobs."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from qoffee import settings
from qoffee.core.models import FAILED_CODE, TrackingState
from qoffee.providers.ibm import (
    decode_name,
    decode_state,
    encode_state,
    normalize_status,
)
from qoffee.core.models import JobStatus

T = datetime(2026, 8, 20, 12, 0, 0, tzinfo=timezone.utc)


def test_bare_tracking_tag_is_tracked_but_unreported():
    """This is the v0.2 shape. It must migrate without intervention."""
    assert decode_state(("qoffee",)) == TrackingState(code=None, failed_at=None)


def test_active_state_roundtrips():
    encoded = encode_state(TrackingState(code="R"))
    assert encoded == "qoffee@R"
    assert decode_state(("qoffee", encoded)).code == "R"


def test_failure_state_roundtrips_with_timestamp():
    encoded = encode_state(TrackingState(code=FAILED_CODE, failed_at=T))
    assert decode_state(("qoffee", encoded)) == TrackingState(
        code=FAILED_CODE, failed_at=T
    )


def test_encoded_failure_tag_fits_ibm_length_limit():
    encoded = encode_state(TrackingState(code=FAILED_CODE, failed_at=T))
    assert len(encoded) <= settings.MAX_TAG_LENGTH


def test_none_state_encodes_to_nothing():
    assert encode_state(TrackingState()) is None


def test_malformed_timestamp_degrades_to_backfill_not_crash():
    assert decode_state(("qoffee", "qoffee@F:garbage")) == TrackingState(
        code=FAILED_CODE, failed_at=None
    )


def test_failure_tag_without_timestamp_decodes():
    assert decode_state(("qoffee", "qoffee@F")).code == FAILED_CODE


def test_unrelated_tags_are_ignored():
    assert decode_state(("mine", "name:X", "other")) == TrackingState()


def test_name_decoding():
    assert decode_name(("qoffee", "name:Bell Test 1")) == "Bell Test 1"
    assert decode_name(("qoffee",)) is None
    assert decode_name(("name:",)) is None


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("DONE", JobStatus.DONE),
        ("done", JobStatus.DONE),
        ("ERROR", JobStatus.ERROR),
        ("CANCELLED", JobStatus.CANCELLED),
        ("QUEUED", JobStatus.QUEUED),
        ("RUNNING", JobStatus.RUNNING),
        ("INITIALIZING", JobStatus.INITIALIZING),
        ("VALIDATING", JobStatus.INITIALIZING),
        ("TELEPORTING", JobStatus.UNKNOWN),
        ("", JobStatus.UNKNOWN),
        (None, JobStatus.UNKNOWN),
    ],
)
def test_status_normalization(raw, expected):
    assert normalize_status(raw) is expected


def test_unknown_status_never_reports_as_terminal():
    """A status we do not recognize must not be guessed into a cleanup."""
    assert normalize_status("SOMETHING_NEW").is_terminal is False
