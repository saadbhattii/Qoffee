from __future__ import annotations

from qoffee.core.models import JobStatus, Severity
from qoffee.core.render import render

from ..factories import make_job


def test_failures_render_last_so_they_are_what_you_land_on():
    message = render(
        [
            make_job("job000000000000000001", JobStatus.ERROR),
            make_job("job000000000000000002", JobStatus.QUEUED),
            make_job("job000000000000000003", JobStatus.DONE),
        ]
    )
    severities = [s.severity for s in message.sections]
    assert severities == [Severity.ACTIVE, Severity.SUCCESS, Severity.FAILURE]


def test_error_and_cancelled_are_separate_sections():
    """Resubmit-and-investigate is a different action from someone cancelled it."""
    message = render(
        [
            make_job("job000000000000000001", JobStatus.ERROR),
            make_job("job000000000000000002", JobStatus.CANCELLED),
        ]
    )
    headings = [s.heading for s in message.sections]
    assert headings == ["Failed (1)", "Cancelled (1)"]


def test_name_tag_is_preferred_over_job_id_as_label():
    message = render([make_job(name="Bell Test 1")])
    assert message.sections[0].items[0].label == "Bell Test 1"


def test_falls_back_to_job_id_without_a_name():
    message = render([make_job("job000000000000000009")])
    assert message.sections[0].items[0].label == "job000000000000000009"


def test_long_error_message_is_truncated():
    message = render(
        [make_job(status=JobStatus.ERROR, error_message="x" * 5000)]
    )
    detail = message.sections[0].items[0].detail
    assert len(detail) <= 400
    assert detail.endswith("\u2026")


def test_unknown_status_shows_the_raw_value():
    message = render(
        [make_job(status=JobStatus.UNKNOWN, raw_status="TELEPORTING")]
    )
    assert "TELEPORTING" in message.sections[0].items[0].status_text


def test_renderer_emits_no_channel_markup():
    """Discord wants **bold**, Slack wants *bold*. Neither belongs here."""
    message = render(
        [make_job(status=JobStatus.ERROR, error_message="boom", name="N")]
    )
    blob = message.title + "".join(
        s.heading + "".join(i.label + i.status_text + (i.detail or "") for i in s.items)
        for s in message.sections
    )
    for token in ("**", "```", "`", "*"):
        assert token not in blob


def test_empty_input_is_an_empty_message():
    assert render([]).is_empty


def test_title_singular_and_plural():
    assert "1 job tracked" in render([make_job()]).title
    assert "2 jobs tracked" in render(
        [make_job("job000000000000000001"), make_job("job000000000000000002")]
    ).title
