"""Logging, with redaction applied once at the handler.

Redaction lives here rather than at call sites because a call-site approach
leaks the first time anyone adds a debug line. Filtering at the handler catches
everything that reaches the log, including exception tracebacks — which for
qiskit can carry the instance CRN inside a request URL.

Identifiers are replaced with a stable short hash rather than a fixed string,
so a run log stays correlatable ("job#3f9a1c appears in both these lines")
without exposing the identifier itself.
"""

from __future__ import annotations

import hashlib
import logging
import re
import sys
import uuid

# Instance CRNs, wherever they appear — including inside URLs in tracebacks.
_CRN_RE = re.compile(r"crn:v1:[^\s\"'<>,)]+")

# IBM job IDs: long lowercase alphanumeric tokens containing both letters and
# digits. Deliberately narrow — this is a backstop for identifiers that were
# never registered, not the primary mechanism.
_JOBID_RE = re.compile(
    r"\b(?=[a-z0-9]*[a-z])(?=[a-z0-9]*\d)[a-z0-9]{18,32}\b"
)

_SENSITIVE: set[str] = set()
_RUN_ID = uuid.uuid4().hex[:8]


def register_sensitive(value: str | None) -> None:
    """Mark a literal string for redaction wherever it appears in the log."""
    if value and len(value) >= 6:
        _SENSITIVE.add(value)


def reset_sensitive() -> None:
    _SENSITIVE.clear()


def _fingerprint(value: str) -> str:
    return "job#" + hashlib.sha256(value.encode("utf-8")).hexdigest()[:6]


def redact(text: str) -> str:
    for value in sorted(_SENSITIVE, key=len, reverse=True):
        text = text.replace(value, _fingerprint(value))
    text = _CRN_RE.sub("crn:<redacted>", text)
    return _JOBID_RE.sub(lambda m: _fingerprint(m.group(0)), text)


class RedactionFilter(logging.Filter):
    def __init__(self, enabled: bool = True) -> None:
        super().__init__()
        self.enabled = enabled

    def filter(self, record: logging.LogRecord) -> bool:
        if not self.enabled:
            return True
        try:
            rendered = record.getMessage()
        except Exception:
            rendered = str(record.msg)
        record.msg = redact(rendered)
        record.args = ()
        if record.exc_info:
            # Render the traceback now so it can be redacted; the handler would
            # otherwise format it after every filter has run.
            formatter = logging.Formatter()
            record.exc_text = redact(formatter.formatException(record.exc_info))
            record.exc_info = None
        return True


class RunIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.run_id = _RUN_ID
        return True


def configure(*, verbose: bool = False, redact_logs: bool = True) -> str:
    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(run_id)s %(levelname)-7s %(name)s: %(message)s",
            datefmt="%H:%M:%S",
        )
    )
    # Order matters: run id is attached before redaction rewrites the message.
    handler.addFilter(RunIdFilter())
    handler.addFilter(RedactionFilter(enabled=redact_logs))

    root.addHandler(handler)
    root.setLevel(logging.DEBUG if verbose else logging.INFO)

    # qiskit is chatty and its own logs are a redaction surface we do not need.
    logging.getLogger("qiskit_ibm_runtime").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    return _RUN_ID
