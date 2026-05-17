"""Send én test-Telegram i signal-format (uden DB)."""

from __future__ import annotations

import asyncio
import sys

from pss.notifications.signal_alerts import format_signal_message, notify_new_signals
from pss.notifications.telegram import TelegramNotConfiguredError
from pss.strategies.base import Signal


async def main() -> None:
    demo = Signal.build(
        market_id=0,
        condition_id="test",
        strategy="base_rate_fade",
        side="BUY_NO",
        market_price=0.30,
        fair_value_estimate=0.50,
        confidence=0.6,
        suggested_size_usd=250.0,
        metadata={
            "question": "PSS test — Telegram signal-format",
            "base_rate_category": "fed_hold",
            "yes_price": 0.70,
        },
    )
    try:
        print(format_signal_message(demo, signal_id=0))
        print("---")
        await notify_new_signals([(demo, 0)])
    except TelegramNotConfiguredError as exc:
        print(exc, file=sys.stderr)
        raise SystemExit(1) from exc
    print("notify_test_signal: ok")


if __name__ == "__main__":
    asyncio.run(main())
