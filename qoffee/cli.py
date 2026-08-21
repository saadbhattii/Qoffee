"""Entry point.

Exit codes are distinct on purpose: a red Actions run should say *which* thing
broke without opening the log.

    0  ok (including "nothing to do")
    1  configuration error
    2  provider unreachable
    3  a required notification channel failed; tags left untouched
    4  a job could not be updated and never will be; see the log
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timezone

from . import settings
from .channels import registry
from .config import ConfigError, load
from .core import engine
from .core.policy import PolicyConfig
from .logging_setup import configure, register_sensitive
from .providers.ibm import IBMProvider

log = logging.getLogger("qoffee")


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="qoffee")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="fetch, decide and render, but send nothing and mutate nothing",
    )
    parser.add_argument(
        "--check-config",
        action="store_true",
        help="validate configuration and credentials, then exit without contacting the provider",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    # Logging is configured with redaction on before anything else runs, so a
    # config error that echoes a credential cannot reach the log unfiltered.
    run_id = configure(verbose=args.verbose, redact_logs=settings.REDACT_LOGS)

    try:
        config = load()
    except ConfigError as exc:
        log.error("configuration error: %s", exc)
        return engine.EXIT_CONFIG

    if config.redact_logs != settings.REDACT_LOGS:
        configure(verbose=args.verbose, redact_logs=config.redact_logs)

    register_sensitive(config.ibm_token)
    register_sensitive(config.ibm_instance)

    try:
        channels = registry.build(config.channel_names)
    except registry.ChannelConfigError as exc:
        log.error("configuration error: %s", exc)
        return engine.EXIT_CONFIG

    log.info(
        "run %s | tag=%s | channels=%s | required=%s | autoclear=%s | redact=%s",
        run_id,
        settings.TRACKING_TAG,
        ",".join(config.channel_names),
        ",".join(sorted(config.required_channels)),
        config.failure_autoclear or "off",
        config.redact_logs,
    )

    if args.check_config:
        log.info("configuration is valid")
        return engine.EXIT_OK

    try:
        provider = IBMProvider.connect(config.ibm_token, config.ibm_instance)
    except engine.ProviderError as exc:
        log.error("provider error: %s", exc)
        return engine.EXIT_PROVIDER

    return engine.run(
        source=provider,
        store=provider,
        channels=channels,
        required_channels=config.required_channels,
        policy_config=PolicyConfig(failure_autoclear=config.failure_autoclear),
        now=datetime.now(timezone.utc),
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    sys.exit(main())