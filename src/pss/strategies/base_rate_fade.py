"""Strategi A: fade mod historisk base rate."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from pss.base_rates.classifier import classify_market_fields
from pss.db.models import BaseRate, Market, MarketSnapshot
from pss.db.session import AsyncSessionLocal
from pss.strategies.base import Signal, Strategy


class BaseRateFadeStrategy(Strategy):
    """Markeder >18pp fra base rate → mean reversion (BUY_YES / BUY_NO). Se docs/strategies/base_rate_fade.md."""

    name = "base_rate_fade"

    MIN_DEVIATION_PCT = 0.18  # uge 6 review: færre marginale «støj»-signaler
    MIN_SAMPLE_SIZE = 10
    MAX_HORIZON_DAYS = 30
    MIN_LIQUIDITY_USD = 7500.0  # uge 6 review: over minimum Polymarket-likviditet
    CONVERGENCE_BAND = 0.05
    DEFAULT_CONFIDENCE = 0.6

    async def scan_for_signals(self) -> list[Signal]:
        signals: list[Signal] = []
        now = datetime.now(timezone.utc)
        max_end = now + timedelta(days=self.MAX_HORIZON_DAYS)

        async with AsyncSessionLocal() as session:
            base_rates = await self._load_base_rates(session)
            markets = await self._load_candidate_markets(session, now=now, max_end=max_end)

            for market in markets:
                signal = await self._signal_for_market(
                    session,
                    market,
                    base_rates,
                    now=now,
                )
                if signal is not None and self.validate_signal(
                    signal,
                    min_edge_pct=self.MIN_DEVIATION_PCT,
                ):
                    signals.append(self.enrich_signal(signal))

        return signals

    async def _load_base_rates(self, session: AsyncSession) -> dict[str, BaseRate]:
        rows = (await session.execute(select(BaseRate))).scalars().all()
        return {row.category: row for row in rows}

    async def _load_candidate_markets(
        self,
        session: AsyncSession,
        *,
        now: datetime,
        max_end: datetime,
    ) -> list[Market]:
        horizon_ok = or_(
            Market.end_date.is_(None),
            (Market.end_date > now) & (Market.end_date <= max_end),
        )
        result = await session.execute(
            select(Market).where(
                Market.is_active,
                ~Market.is_closed,
                Market.has_base_rate,
                horizon_ok,
            ),
        )
        return list(result.scalars().all())

    async def _signal_for_market(
        self,
        session: AsyncSession,
        market: Market,
        base_rates: dict[str, BaseRate],
        *,
        now: datetime,
    ) -> Signal | None:
        latest = await session.scalar(
            select(MarketSnapshot)
            .where(MarketSnapshot.market_id == market.id)
            .order_by(MarketSnapshot.snapshot_at.desc())
            .limit(1),
        )
        if latest is None or latest.yes_price is None:
            return None

        liquidity = float(latest.liquidity_usd or 0)
        if liquidity < self.MIN_LIQUIDITY_USD:
            return None

        category = classify_market_fields(
            question=market.question,
            description=market.description,
            category=market.category,
            primary_vertical=market.primary_vertical,
        )
        if category is None:
            return None

        base_rate = base_rates.get(category)
        if base_rate is None or base_rate.sample_size < self.MIN_SAMPLE_SIZE:
            return None

        yes_price = float(latest.yes_price)
        br = float(base_rate.base_probability)
        deviation = yes_price - br

        exit_when = market.end_date
        if exit_when is not None and exit_when.tzinfo is None:
            exit_when = exit_when.replace(tzinfo=timezone.utc)

        meta = {
            "base_rate_id": base_rate.id,
            "base_rate_category": category,
            "base_rate_probability": br,
            "deviation_pp": deviation,
            "yes_price": yes_price,
            "liquidity_usd": liquidity,
            "question": (market.question or "")[:120],
        }

        if deviation > self.MIN_DEVIATION_PCT:
            no_price = 1.0 - yes_price
            fair_no = 1.0 - br
            return Signal.build(
                market_id=market.id,
                condition_id=market.condition_id,
                strategy=self.name,
                side="BUY_NO",
                market_price=no_price,
                fair_value_estimate=fair_no,
                confidence=self.DEFAULT_CONFIDENCE,
                exit_price_target=min(1.0, br + self.CONVERGENCE_BAND),
                exit_date_target=exit_when,
                exit_conditions={
                    "reason": "convergence_to_base_rate",
                    "target_yes": br + self.CONVERGENCE_BAND,
                },
                metadata=meta,
            )

        if deviation < -self.MIN_DEVIATION_PCT:
            return Signal.build(
                market_id=market.id,
                condition_id=market.condition_id,
                strategy=self.name,
                side="BUY_YES",
                market_price=yes_price,
                fair_value_estimate=br,
                confidence=self.DEFAULT_CONFIDENCE,
                exit_price_target=max(0.0, br - self.CONVERGENCE_BAND),
                exit_date_target=exit_when,
                exit_conditions={
                    "reason": "convergence_to_base_rate",
                    "target_yes": br - self.CONVERGENCE_BAND,
                },
                metadata=meta,
            )

        return None
