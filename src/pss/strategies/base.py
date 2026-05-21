"""Base class og Signal-dataclass for PSS-strategier."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

SignalSide = Literal["BUY_YES", "BUY_NO"]
ModelConfidence = Literal["low", "medium", "high"]
VALID_SIDES: frozenset[str] = frozenset({"BUY_YES", "BUY_NO"})


def compute_edge_pct(market_price: float, fair_value: float, side: SignalSide) -> float:
    """Edge for den valgte side (yes-sandsynligheder 0–1)."""
    if side == "BUY_YES":
        return fair_value - market_price
    return market_price - fair_value


@dataclass
class Signal:
    """Potentielt trade-signal før persistens og risk-engine."""

    market_id: int
    condition_id: str
    strategy: str
    side: SignalSide
    market_price: float
    fair_value_estimate: float
    edge_pct: float
    confidence: float
    model_confidence: ModelConfidence = "medium"
    suggested_size_usd: float = 0.0
    exit_price_target: float | None = None
    exit_date_target: datetime | None = None
    exit_conditions: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.side not in VALID_SIDES:
            msg = f"Ugyldig side: {self.side!r}"
            raise ValueError(msg)
        for name in ("market_price", "fair_value_estimate", "confidence"):
            value = getattr(self, name)
            if not 0.0 <= value <= 1.0:
                msg = f"{name} skal være mellem 0 og 1, fik {value}"
                raise ValueError(msg)

    @classmethod
    def build(
        cls,
        *,
        market_id: int,
        condition_id: str,
        strategy: str,
        side: SignalSide,
        market_price: float,
        fair_value_estimate: float,
        confidence: float,
        model_confidence: ModelConfidence = "medium",
        suggested_size_usd: float = 0.0,
        exit_price_target: float | None = None,
        exit_date_target: datetime | None = None,
        exit_conditions: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Signal:
        """Opret signal med edge udregnet fra pris og fair value."""
        edge = compute_edge_pct(market_price, fair_value_estimate, side)
        return cls(
            market_id=market_id,
            condition_id=condition_id,
            strategy=strategy,
            side=side,
            market_price=market_price,
            fair_value_estimate=fair_value_estimate,
            edge_pct=edge,
            confidence=confidence,
            model_confidence=model_confidence,
            suggested_size_usd=suggested_size_usd,
            exit_price_target=exit_price_target,
            exit_date_target=exit_date_target,
            exit_conditions=exit_conditions or {},
            metadata=metadata or {},
        )


class Strategy(ABC):
    """Abstract base for alle strategier."""

    name: str

    @abstractmethod
    async def scan_for_signals(self) -> list[Signal]:
        """Find kandidat-signaler i database (før risk-filtre)."""

    def passes_minimum_edge(self, signal: Signal, min_edge_pct: float = 0.03) -> bool:
        """Filtrér signaler med edge under threshold (efter friktion)."""
        return signal.edge_pct >= min_edge_pct

    def validate_signal(self, signal: Signal, *, min_edge_pct: float = 0.03) -> bool:
        """Konkretiser og filtrér signal."""
        if signal.strategy != self.name:
            return False
        return self.passes_minimum_edge(signal, min_edge_pct=min_edge_pct)

    def generate_exit_criteria(
        self,
        signal: Signal,
        *,
        convergence_band: float = 0.05,
        max_hold_days: int = 30,
    ) -> dict[str, Any]:
        """Standard exit: konvergens mod fair value eller tidsstop."""
        if signal.side == "BUY_YES":
            target = signal.fair_value_estimate - convergence_band
        else:
            target = signal.fair_value_estimate + convergence_band

        target = max(0.0, min(1.0, target))
        exit_at = datetime.now(timezone.utc) + timedelta(days=max_hold_days)
        return {
            "exit_price_target": target,
            "exit_date_target": exit_at,
            "exit_conditions": {
                "reason": "convergence_to_base_rate",
                "convergence_band": convergence_band,
                "max_hold_days": max_hold_days,
            },
        }

    def enrich_signal(self, signal: Signal) -> Signal:
        """Udfyld exit-felter hvis de mangler."""
        criteria = self.generate_exit_criteria(signal)
        if signal.exit_price_target is None:
            signal.exit_price_target = criteria["exit_price_target"]
        if signal.exit_date_target is None:
            signal.exit_date_target = criteria["exit_date_target"]
        if not signal.exit_conditions:
            signal.exit_conditions = criteria["exit_conditions"]
        return signal
