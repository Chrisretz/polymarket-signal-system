"""Pre-trade tjekliste (STRATEGY.md §9.2) → decisions_journal."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import structlog
from sqlalchemy import select

from pss.config import settings
from pss.db.models import DecisionJournal, Market, Signal as SignalRow
from pss.db.session import AsyncSessionLocal

logger = structlog.get_logger(__name__)

ENTRY_TYPE_PRE_TRADE = "PRE_TRADE"


@dataclass(frozen=True, slots=True)
class PreTradeField:
    """Ét tjekliste-spørgsmål mappet til DB-kolonne."""

    key: str
    prompt: str
    db_column: str


# STRATEGY.md §9.2 — rækkefølge fast
PRE_TRADE_FIELDS: tuple[PreTradeField, ...] = (
    PreTradeField("strategy", "1. Strategi", "strategy"),
    PreTradeField("thesis", "2. Edge-tese (én sætning)", "thesis"),
    PreTradeField(
        "base_rate_estimate",
        "3a. Base rate (0–1, fx 0.72)",
        "base_rate_estimate",
    ),
    PreTradeField(
        "my_probability_estimate",
        "3b. Din sandsynlighed (0–1)",
        "my_probability_estimate",
    ),
    PreTradeField(
        "expected_edge_pct",
        "4. Forventet edge efter friktion (decimal, fx 0.12 = 12pp)",
        "expected_edge_pct",
    ),
    PreTradeField(
        "position_size_usd",
        "5. Position size USD",
        "position_size_usd",
    ),
    PreTradeField("exit_criteria", "6. Exit-kriterium (pris/tid/event)", "exit_criteria"),
    PreTradeField(
        "invalidation_scenarios",
        "7. Hvornår lukker du før planlagt exit?",
        "invalidation_scenarios",
    ),
    PreTradeField(
        "strongest_counter_argument",
        "8. Stærkeste modargument",
        "strongest_counter_argument",
    ),
    PreTradeField(
        "potential_biases",
        "9. Mulige biases",
        "potential_biases",
    ),
    PreTradeField(
        "max_loss_impact",
        "10. PnL-impact hvis maks tab (USD + % bankroll)",
        "max_loss_impact",
    ),
)


@dataclass(slots=True)
class PreTradeAnswers:
    """Svar til pre-trade — alle felter påkrævet."""

    strategy: str
    thesis: str
    base_rate_estimate: float
    my_probability_estimate: float
    expected_edge_pct: float
    position_size_usd: float
    exit_criteria: str
    invalidation_scenarios: str
    strongest_counter_argument: str
    potential_biases: str
    max_loss_impact: str

    def validate(self) -> list[str]:
        errors: list[str] = []
        for field in PRE_TRADE_FIELDS:
            value = getattr(self, field.key)
            if isinstance(value, str) and not value.strip():
                errors.append(f"{field.prompt}: tom")
            elif field.key in ("base_rate_estimate", "my_probability_estimate"):
                if not 0.0 <= float(value) <= 1.0:
                    errors.append(f"{field.prompt}: skal være mellem 0 og 1")
            elif field.key == "expected_edge_pct" and float(value) <= 0:
                errors.append(f"{field.prompt}: skal være > 0")
            elif field.key == "position_size_usd" and float(value) <= 0:
                errors.append(f"{field.prompt}: skal være > 0")
        return errors

    def to_journal_kwargs(self) -> dict[str, Any]:
        return {
            "entry_type": ENTRY_TYPE_PRE_TRADE,
            "strategy": self.strategy.strip(),
            "thesis": self.thesis.strip(),
            "base_rate_estimate": self.base_rate_estimate,
            "my_probability_estimate": self.my_probability_estimate,
            "expected_edge_pct": self.expected_edge_pct,
            "position_size_usd": self.position_size_usd,
            "exit_criteria": self.exit_criteria.strip(),
            "invalidation_scenarios": self.invalidation_scenarios.strip(),
            "strongest_counter_argument": self.strongest_counter_argument.strip(),
            "potential_biases": self.potential_biases.strip(),
            "max_loss_impact": self.max_loss_impact.strip(),
        }


def defaults_from_signal(
    signal: SignalRow,
    *,
    market_question: str | None = None,
) -> dict[str, str]:
    """Foreslåede svar til CLI (bruger kan trykke Enter)."""
    meta = signal.signal_metadata or {}
    br = meta.get("base_rate_probability")
    category = meta.get("base_rate_category", "")
    deviation = meta.get("deviation_pp")
    size = float(signal.suggested_size_usd)
    bankroll = float(settings.bankroll_usd)
    max_loss_usd = size
    max_loss_pct = (size / bankroll * 100) if bankroll > 0 else 0.0

    exit_parts: list[str] = []
    if signal.exit_price_target is not None:
        exit_parts.append(f"pris-mål={float(signal.exit_price_target):.3f}")
    if signal.exit_date_target is not None:
        exit_parts.append(f"senest={signal.exit_date_target.date().isoformat()}")
    if signal.exit_conditions:
        exit_parts.append(str(signal.exit_conditions))

    thesis = (
        f"Fade {signal.side} mod base rate ({category}): marked "
        f"{float(signal.market_price):.2f} vs fair {float(signal.fair_value_estimate):.2f}."
    )
    if deviation is not None:
        thesis += f" Afvigelse {float(deviation):+.1%}pp."

    return {
        "strategy": signal.strategy,
        "thesis": thesis,
        "base_rate_estimate": f"{float(br):.4f}" if br is not None else f"{float(signal.fair_value_estimate):.4f}",
        "my_probability_estimate": f"{float(signal.fair_value_estimate):.4f}",
        "expected_edge_pct": f"{float(signal.edge_pct):.4f}",
        "position_size_usd": f"{size:.2f}",
        "exit_criteria": "; ".join(exit_parts) or "Konvergens mod base rate",
        "invalidation_scenarios": (
            "Nyhed der ændrer fundamental sandsynlighed; likviditet under $5k; "
            "oracle/dispute-risiko."
        ),
        "strongest_counter_argument": (
            f"Markedet kan have information jeg mangler om: {(market_question or '')[:80]}"
        ),
        "potential_biases": "Confirmation bias, mean-reversion overconfidence.",
        "max_loss_impact": f"${max_loss_usd:.0f} (~{max_loss_pct:.1f}% af bankroll ${bankroll:,.0f})",
    }


async def load_signal_for_journal(signal_id: int) -> tuple[SignalRow, Market] | None:
    async with AsyncSessionLocal() as session:
        row = (
            await session.execute(
                select(SignalRow, Market)
                .join(Market, Market.id == SignalRow.market_id)
                .where(SignalRow.id == signal_id),
            )
        ).one_or_none()
        if row is None:
            return None
        sig, market = row
        return sig, market


async def save_pre_trade_journal(
    signal_id: int,
    answers: PreTradeAnswers,
    *,
    accept: bool,
) -> tuple[int, str]:
    """
    Gem PRE_TRADE og opdatér signal-status.

    Returns:
        (journal_id, new_signal_status)
    """
    errors = answers.validate()
    if errors:
        msg = "; ".join(errors)
        raise ValueError(msg)

    async with AsyncSessionLocal() as session:
        sig = await session.get(SignalRow, signal_id)
        if sig is None:
            raise ValueError(f"Signal {signal_id} findes ikke")
        if sig.status != "NEW":
            raise ValueError(f"Signal {signal_id} har status {sig.status!r} (forventet NEW)")

        journal = DecisionJournal(
            position_id=None,
            market_id=sig.market_id,
            **answers.to_journal_kwargs(),
        )
        session.add(journal)
        await session.flush()

        sig.status = "ACCEPTED" if accept else "REJECTED"
        if not accept:
            sig.rejected_reason = "pre_trade_rejected"

        await session.commit()
        journal_id = journal.id
        status = sig.status

    logger.info(
        "pre_trade_saved",
        signal_id=signal_id,
        journal_id=journal_id,
        signal_status=status,
    )
    return journal_id, status


__all__ = [
    "ENTRY_TYPE_PRE_TRADE",
    "PRE_TRADE_FIELDS",
    "PreTradeAnswers",
    "PreTradeField",
    "defaults_from_signal",
    "load_signal_for_journal",
    "save_pre_trade_journal",
]
