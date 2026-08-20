"""Orchestration: fetch -> plan -> notify -> apply.

The ordering here is the safety property the whole tool rests on. A job is
never untagged unless the notification about it was confirmed delivered. If
delivery fails, every tag is left exactly as it was and the same news is
reported again next run.

The cost of that choice is at-least-once delivery: if the process dies between
a successful send and the tag write, the next run reports the same thing again.
That is deliberate. A duplicate message is an annoyance; a dropped failure is
the bug this tool exists to prevent.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import datetime

from ..channels.base import Channel
from ..logging_setup import register_sensitive
from .models import DeliveryResult, Leave, Plan, Resolve, SetState, TrackedJob
from .policy import PolicyConfig, plan

log = logging.getLogger(__name__)

EXIT_OK = 0
EXIT_CONFIG = 1
EXIT_PROVIDER = 2
EXIT_DELIVERY = 3


class ProviderError(RuntimeError):
    """Raised by an adapter when the upstream service could not be reached."""


def _log_plan(p: Plan) -> None:
    """Emit the full plan before anything is applied.

    When something behaves unexpectedly at 2am, "why is this job still
    tracked?" is the question, and this is the answer.
    """
    log.info("plan: notify=%s actions=%d", p.notify, len(p.actions))
    for action in p.actions:
        verb = type(action).__name__.lower()
        log.info("  %-9s %s — %s", verb, action.job.id, action.reason)


def _dispatch(
    channels: Sequence[Channel],
    required: set[str],
    message,
) -> bool:
    """Send to every channel. Return True only if all required ones confirmed.

    Optional channels are allowed to fail without wedging tracking; a required
    one failing means nothing gets untagged this run.
    """
    satisfied = True
    for channel in channels:
        try:
            result = channel.send(message)
        except Exception as exc:  # a channel must never take the process down
            log.exception("channel %s raised", channel.name)
            result = DeliveryResult(channel.name, False, str(exc))

        if result.ok:
            log.info("delivered via %s", channel.name)
        else:
            level = logging.ERROR if channel.name in required else logging.WARNING
            log.log(
                level,
                "delivery failed via %s (%s): %s",
                channel.name,
                "required" if channel.name in required else "optional",
                result.detail,
            )
            if channel.name in required:
                satisfied = False

    return satisfied


def _apply(store, actions, *, delivered: bool) -> None:
    for action in actions:
        if isinstance(action, Leave):
            continue
        if action.requires_delivery and not delivered:
            continue
        try:
            if isinstance(action, Resolve):
                store.resolve(action.job)
                log.info("resolved %s (%s)", action.job.id, action.reason)
            elif isinstance(action, SetState):
                store.set_state(action.job, action.state)
                log.info(
                    "state %s -> %s (%s)",
                    action.job.id,
                    action.state.code,
                    action.reason,
                )
        except Exception:
            # One job's tag write failing must not abandon the rest. The job
            # stays in its previous state and is re-evaluated next run.
            log.exception("failed to apply %s to %s", type(action).__name__, action.job.id)


def run(
    *,
    source,
    store,
    channels: Sequence[Channel],
    required_channels: set[str],
    policy_config: PolicyConfig,
    now: datetime,
    dry_run: bool = False,
) -> int:
    try:
        jobs: list[TrackedJob] = source.fetch_tracked()
    except ProviderError:
        log.exception("could not reach provider")
        return EXIT_PROVIDER
    except Exception:
        log.exception("unexpected provider failure")
        return EXIT_PROVIDER

    for job in jobs:
        register_sensitive(job.id)

    if not jobs:
        log.info("nothing tagged; no work to do")
        return EXIT_OK

    log.info("found %d tracked job(s)", len(jobs))

    p = plan(jobs, policy_config, now)
    _log_plan(p)

    if dry_run:
        log.info("dry run: no notification sent, no tags mutated")
        if p.notify:
            for section in p.message.sections:
                log.info("  [%s]", section.heading)
                for item in section.items:
                    log.info("    %s — %s", item.label, item.status_text)
        return EXIT_OK

    delivered = True
    if p.notify:
        delivered = _dispatch(channels, required_channels, p.message)
    else:
        log.info("no state changes; staying quiet")

    _apply(store, p.actions, delivered=delivered)

    if p.notify and not delivered:
        log.error("required channel(s) failed; tags left unchanged for retry")
        return EXIT_DELIVERY

    return EXIT_OK
