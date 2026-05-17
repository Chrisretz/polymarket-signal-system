"""Seed base_rates fra FRED + priors (Uge 4, Dag 2–3)."""

from __future__ import annotations

import asyncio
import sys

from sqlalchemy import func, select

from pss.base_rates.seed import seed_base_rates
from pss.config import settings
from pss.db.models import BaseRate
from pss.db.session import AsyncSessionLocal


async def _print_summary() -> None:
    async with AsyncSessionLocal() as session:
        total = await session.scalar(select(func.count()).select_from(BaseRate))
        rows = (
            await session.execute(
                select(
                    BaseRate.category,
                    BaseRate.base_probability,
                    BaseRate.sample_size,
                    BaseRate.source,
                ).order_by(BaseRate.category),
            )
        ).all()

    print(f"\nRækker i base_rates: {total}")
    for category, prob, n, source in rows:
        print(f"  {category:28} p={float(prob):.3f} n={n:4d}  ({source})")


async def main() -> None:
    if settings.fred_api_key is None:
        print(
            "Advarsel: FRED_API_KEY mangler — kun expert priors seedes (ECB/EU-politik).",
            file=sys.stderr,
        )
        print(
            "Tilføj nøgle: https://fred.stlouisfed.org/docs/api/api_key.html\n",
            file=sys.stderr,
        )

    written, missing = await seed_base_rates()
    await _print_summary()

    if missing:
        print(f"\nMangler estimat for: {', '.join(missing)}", file=sys.stderr)
        if settings.fred_api_key is not None:
            raise SystemExit(1)
        print("Delvis seed — sæt FRED_API_KEY i .env og kør igen for fuld dækning.")

    print(f"\nseed_base_rates: ok ({written} kategorier)")


if __name__ == "__main__":
    asyncio.run(main())
