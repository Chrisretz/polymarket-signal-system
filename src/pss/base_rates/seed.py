"""Upsert base_rates fra FRED + priors."""

from __future__ import annotations

from sqlalchemy import select

from pss.base_rates.categories import BASE_RATE_CATEGORIES
from pss.base_rates.estimates import build_all_estimates, categories_missing_estimates
from pss.base_rates.fred import FredClient
from pss.base_rates.types import RateEstimate
from pss.config import settings
from pss.db.models import BaseRate
from pss.db.session import AsyncSessionLocal


async def upsert_base_rates(estimates: dict[str, RateEstimate]) -> int:
    """Indsæt/opdater alle kategorier med kendt estimat. Returnerer antal rækker."""
    count = 0
    async with AsyncSessionLocal() as session:
        for cat in BASE_RATE_CATEGORIES:
            est = estimates.get(cat.category)
            if est is None:
                continue
            row = await session.scalar(
                select(BaseRate).where(BaseRate.category == cat.category),
            )
            if row is None:
                session.add(
                    BaseRate(
                        category=cat.category,
                        description=cat.description,
                        sample_size=est.sample_size,
                        base_probability=est.base_probability,
                        confidence_lower=est.confidence_lower,
                        confidence_upper=est.confidence_upper,
                        source=est.source,
                        notes=est.notes,
                    ),
                )
            else:
                row.description = cat.description
                row.sample_size = est.sample_size
                row.base_probability = est.base_probability
                row.confidence_lower = est.confidence_lower
                row.confidence_upper = est.confidence_upper
                row.source = est.source
                row.notes = est.notes
            count += 1
        await session.commit()
    return count


async def seed_base_rates() -> tuple[int, list[str]]:
    """Hent estimater og skriv til DB. Returnerer (antal, manglende kategorier)."""
    api_key = (
        settings.fred_api_key.get_secret_value()
        if settings.fred_api_key is not None
        else None
    )
    if api_key:
        async with FredClient(api_key) as fred:
            estimates = await build_all_estimates(fred)
    else:
        estimates = await build_all_estimates(None)

    written = await upsert_base_rates(estimates)
    missing = [c.category for c in categories_missing_estimates(estimates)]
    return written, missing
