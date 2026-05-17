"""Delte typer for base rates."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RateEstimate:
    base_probability: float
    sample_size: int
    confidence_lower: float | None
    confidence_upper: float | None
    source: str
    notes: str
