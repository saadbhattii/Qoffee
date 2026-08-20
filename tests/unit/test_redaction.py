from __future__ import annotations

import logging

from qoffee.logging_setup import (
    RedactionFilter,
    redact,
    register_sensitive,
    reset_sensitive,
)


def _record(msg, *args, exc_info=None):
    return logging.LogRecord(
        "t", logging.INFO, __file__, 1, msg, args, exc_info
    )


def test_registered_token_is_replaced_with_stable_fingerprint():
    register_sensitive("d0abc123def456ghi789")
    out = redact("job d0abc123def456ghi789 finished")
    assert "d0abc123def456ghi789" not in out
    assert "job#" in out
    assert out == redact("job d0abc123def456ghi789 finished")


def test_crn_is_redacted_even_inside_a_url():
    out = redact("https://api.example.com/x?instance=crn:v1:bluemix:public:q:us-east:a/1::")
    assert "crn:v1" not in out or "crn:<redacted>" in out
    assert "bluemix" not in out


def test_unregistered_jobid_pattern_is_caught_as_backstop():
    out = redact("saw cxyz123abcdefg1234567 in the wild")
    assert "cxyz123abcdefg1234567" not in out


def test_plain_words_are_not_mangled():
    assert redact("everything completed successfully") == (
        "everything completed successfully"
    )


def test_filter_rewrites_message_and_consumes_args():
    reset_sensitive()
    register_sensitive("d0abc123def456ghi789")
    f = RedactionFilter(enabled=True)
    record = _record("job %s done", "d0abc123def456ghi789")
    assert f.filter(record) is True
    assert "d0abc123def456ghi789" not in record.getMessage()
    assert record.args == ()


def test_disabled_filter_is_a_passthrough():
    register_sensitive("d0abc123def456ghi789")
    f = RedactionFilter(enabled=False)
    record = _record("job %s done", "d0abc123def456ghi789")
    f.filter(record)
    assert "d0abc123def456ghi789" in record.getMessage()


def test_traceback_text_is_redacted():
    register_sensitive("d0abc123def456ghi789")
    try:
        raise ValueError("failed for d0abc123def456ghi789")
    except ValueError:
        import sys

        record = _record("boom", exc_info=sys.exc_info())
    RedactionFilter(enabled=True).filter(record)
    assert "d0abc123def456ghi789" not in (record.exc_text or "")
    assert record.exc_info is None
