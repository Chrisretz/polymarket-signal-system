"""Verificér structlog JSON/console output (Uge 2, Dag 4)."""

from __future__ import annotations

import structlog

from pss.logging_config import configure_logging, resolve_log_format


def main() -> None:
    active = configure_logging()
    log = structlog.get_logger("pss.test")

    log.info("test_event", component="logging", status="ok", count=42)
    log.warning("test_warning", hint="Dette er kun en test")

    print(f"\ntest_logging: ok (format={active}, resolved={resolve_log_format()})")


if __name__ == "__main__":
    main()
