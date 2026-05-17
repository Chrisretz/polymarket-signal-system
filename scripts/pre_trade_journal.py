"""Interaktiv pre-trade journal for et NEW-signal."""

from __future__ import annotations

import argparse
import asyncio
import sys

from sqlalchemy import select

from pss.db.models import Market, Signal as SignalRow
from pss.db.session import AsyncSessionLocal
from pss.journal.pre_trade import (
    PRE_TRADE_FIELDS,
    PreTradeAnswers,
    defaults_from_signal,
    load_signal_for_journal,
    save_pre_trade_journal,
)


def _prompt(field_key: str, label: str, default: str) -> str:
    hint = f" [{default}]" if default else ""
    raw = input(f"{label}{hint}: ").strip()
    return raw if raw else default


def _parse_float(raw: str, *, field: str) -> float:
    try:
        return float(raw.replace(",", "."))
    except ValueError as exc:
        msg = f"Ugyldigt tal for {field}: {raw!r}"
        raise ValueError(msg) from exc


async def _list_new_signals() -> list[tuple[SignalRow, str]]:
    async with AsyncSessionLocal() as session:
        rows = (
            await session.execute(
                select(SignalRow, Market.question)
                .join(Market, Market.id == SignalRow.market_id)
                .where(SignalRow.status == "NEW")
                .order_by(SignalRow.generated_at.desc())
                .limit(30),
            )
        ).all()
    return [(sig, question or "") for sig, question in rows]


async def _pick_signal_id(explicit: int | None) -> int:
    if explicit is not None:
        return explicit

    rows = await _list_new_signals()
    if not rows:
        print("Ingen NEW-signaler. Kør signal-pipeline eller vent på scheduler.")
        sys.exit(0)

    print("NEW-signaler:\n")
    for sig, question in rows:
        print(
            f"  {sig.id:>4}  ${float(sig.suggested_size_usd):>5.0f}  {sig.side:7}  "
            f"edge={float(sig.edge_pct):.2%}  {question[:60]}",
        )
    print()
    raw = input("Vælg signal-id: ").strip()
    if not raw.isdigit():
        print("Ugyldigt id.")
        sys.exit(1)
    return int(raw)


def _collect_answers(signal: SignalRow, question: str) -> PreTradeAnswers:
    defaults = defaults_from_signal(signal, market_question=question)
    values: dict[str, str] = {}
    for field in PRE_TRADE_FIELDS:
        values[field.key] = _prompt(field.key, field.prompt, defaults.get(field.key, ""))

    return PreTradeAnswers(
        strategy=values["strategy"],
        thesis=values["thesis"],
        base_rate_estimate=_parse_float(values["base_rate_estimate"], field="base_rate"),
        my_probability_estimate=_parse_float(
            values["my_probability_estimate"],
            field="my_probability",
        ),
        expected_edge_pct=_parse_float(values["expected_edge_pct"], field="edge"),
        position_size_usd=_parse_float(values["position_size_usd"], field="size"),
        exit_criteria=values["exit_criteria"],
        invalidation_scenarios=values["invalidation_scenarios"],
        strongest_counter_argument=values["strongest_counter_argument"],
        potential_biases=values["potential_biases"],
        max_loss_impact=values["max_loss_impact"],
    )


async def main() -> None:
    parser = argparse.ArgumentParser(description="Pre-trade journal (10 spørgsmål)")
    parser.add_argument("--signal-id", type=int, help="Spring valgmenu over")
    args = parser.parse_args()

    signal_id = await _pick_signal_id(args.signal_id)
    loaded = await load_signal_for_journal(signal_id)
    if loaded is None:
        print(f"Signal {signal_id} findes ikke.")
        sys.exit(1)
    signal, market = loaded
    if signal.status != "NEW":
        print(f"Signal {signal_id} er {signal.status!r} — kun NEW kan journaleres.")
        sys.exit(1)

    print("\n--- Kontekst ---")
    print(f"Marked: {market.question}")
    print(
        f"side={signal.side}  pris={float(signal.market_price):.3f}  "
        f"fair={float(signal.fair_value_estimate):.3f}  edge={float(signal.edge_pct):.2%}",
    )
    print("Tryk Enter for at beholde forslag.\n")

    answers = _collect_answers(signal, market.question or "")
    errors = answers.validate()
    if errors:
        print("\nValidering fejlede:")
        for err in errors:
            print(f"  - {err}")
        sys.exit(1)

    print("\n--- Opsummering ---")
    for field in PRE_TRADE_FIELDS:
        print(f"{field.prompt}: {getattr(answers, field.key)}")
    print()

    accept_raw = input("Godkend signal (ACCEPTED)? [j/N]: ").strip().lower()
    accept = accept_raw in ("j", "ja", "y", "yes")

    journal_id, status = await save_pre_trade_journal(signal_id, answers, accept=accept)
    print(f"\nGemt journal_id={journal_id}  signal_status={status}")
    print("pre_trade_journal: ok")


if __name__ == "__main__":
    asyncio.run(main())
