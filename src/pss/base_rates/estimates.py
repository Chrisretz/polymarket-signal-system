"""Empiriske base rates fra FRED-serier."""

from __future__ import annotations

import math
from datetime import date

import httpx

from pss.base_rates.categories import BASE_RATE_CATEGORIES, BaseRateCategory
from pss.base_rates.fred import FredClient
from pss.base_rates.priors import PRIOR_ESTIMATES
from pss.base_rates.types import RateEstimate

FED_FUNDS_SERIES = "FEDFUNDS"
CPI_SERIES = "CPIAUCSL"
NFP_SERIES = "PAYEMS"
GDP_SERIES = "GDPC1"
RECESSION_SERIES = "USREC"
EU_HICP_SERIES = "CP0000EZ19M086NEST"


def wilson_interval(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n <= 0:
        return 0.0, 1.0
    p = successes / n
    denom = 1 + z**2 / n
    center = (p + z**2 / (2 * n)) / denom
    margin = (z / denom) * math.sqrt(p * (1 - p) / n + z**2 / (4 * n**2))
    return max(0.0, center - margin), min(1.0, center + margin)


def _monthly_last(points: list[tuple[date, float]]) -> list[float]:
    by_month: dict[tuple[int, int], float] = {}
    for obs_date, value in points:
        by_month[(obs_date.year, obs_date.month)] = value
    return [by_month[k] for k in sorted(by_month)]


def _monthly_changes(levels: list[float]) -> list[float]:
    return [levels[i] - levels[i - 1] for i in range(1, len(levels))]


def _quarterly_growth_rates(levels: list[float]) -> list[float]:
    """Approx. q/q annualized growth fra kvartalsvise niveauer."""
    rates: list[float] = []
    for i in range(4, len(levels)):
        if levels[i - 4] <= 0:
            continue
        qoq = (levels[i] / levels[i - 4]) - 1.0
        rates.append((1 + qoq) ** 4 - 1)
    return rates


def _estimate_from_binary_outcomes(
    outcomes: list[bool],
    *,
    source: str,
    notes: str,
) -> RateEstimate:
    n = len(outcomes)
    successes = sum(1 for x in outcomes if x)
    p = successes / n if n else 0.5
    lo, hi = wilson_interval(successes, n)
    return RateEstimate(
        base_probability=round(p, 4),
        sample_size=n,
        confidence_lower=round(lo, 4),
        confidence_upper=round(hi, 4),
        source=source,
        notes=notes,
    )


def _estimate_vs_rolling_mean(
    changes: list[float],
    *,
    window: int,
    above: bool,
    source: str,
    notes: str,
) -> RateEstimate | None:
    if len(changes) <= window:
        return None
    outcomes: list[bool] = []
    for i in range(window, len(changes)):
        trail = changes[i - window : i]
        mean = sum(trail) / len(trail)
        outcomes.append(changes[i] > mean if above else changes[i] < mean)
    label = "over" if above else "under"
    return _estimate_from_binary_outcomes(
        outcomes,
        source=source,
        notes=f"{notes}; {label} trailing {window}-periode mean",
    )


async def estimate_fed_outcomes(fred: FredClient) -> dict[str, RateEstimate]:
    points = await fred.fetch_observations(FED_FUNDS_SERIES, observation_start="1990-01-01")
    monthly = _monthly_last(points)
    deltas = _monthly_changes(monthly)

    holds: list[bool] = []
    cuts_25: list[bool] = []
    hikes_25: list[bool] = []
    for d in deltas:
        holds.append(abs(d) < 0.0625)
        cuts_25.append(-0.375 < d <= -0.125)
        hikes_25.append(0.125 <= d < 0.375)

    return {
        "fed_hold": _estimate_from_binary_outcomes(
            holds,
            source=f"fred:{FED_FUNDS_SERIES}",
            notes="Månedlig FEDFUNDS ændring ~0 bp",
        ),
        "fed_cut_25bps": _estimate_from_binary_outcomes(
            cuts_25,
            source=f"fred:{FED_FUNDS_SERIES}",
            notes="Månedlig ændring ca. -25 bp",
        ),
        "fed_hike_25bps": _estimate_from_binary_outcomes(
            hikes_25,
            source=f"fred:{FED_FUNDS_SERIES}",
            notes="Månedlig ændring ca. +25 bp",
        ),
    }


async def estimate_cpi_surprises(fred: FredClient) -> dict[str, RateEstimate]:
    points = await fred.fetch_observations(CPI_SERIES, observation_start="2000-01-01")
    monthly = _monthly_last(points)
    mom_pct = [
        (monthly[i] / monthly[i - 1] - 1.0) * 100.0
        for i in range(1, len(monthly))
        if monthly[i - 1] > 0
    ]
    above = _estimate_vs_rolling_mean(
        mom_pct,
        window=12,
        above=True,
        source=f"fred:{CPI_SERIES}",
        notes="CPI MoM % vs 12m gennemsnit",
    )
    below = _estimate_vs_rolling_mean(
        mom_pct,
        window=12,
        above=False,
        source=f"fred:{CPI_SERIES}",
        notes="CPI MoM % vs 12m gennemsnit",
    )
    out: dict[str, RateEstimate] = {}
    if above:
        out["us_cpi_above_consensus"] = above
    if below:
        out["us_cpi_below_consensus"] = below
    return out


async def estimate_nfp_surprises(fred: FredClient) -> dict[str, RateEstimate]:
    points = await fred.fetch_observations(NFP_SERIES, observation_start="2000-01-01")
    monthly = _monthly_last(points)
    changes = _monthly_changes(monthly)
    above = _estimate_vs_rolling_mean(
        changes,
        window=6,
        above=True,
        source=f"fred:{NFP_SERIES}",
        notes="Payrolls niveau MoM change (thousands)",
    )
    below = _estimate_vs_rolling_mean(
        changes,
        window=6,
        above=False,
        source=f"fred:{NFP_SERIES}",
        notes="Payrolls niveau MoM change (thousands)",
    )
    out: dict[str, RateEstimate] = {}
    if above:
        out["us_nfp_above_consensus"] = above
    if below:
        out["us_nfp_below_consensus"] = below
    return out


async def estimate_gdp_surprise(fred: FredClient) -> dict[str, RateEstimate]:
    points = await fred.fetch_observations(GDP_SERIES, observation_start="1990-01-01")
    by_q: dict[tuple[int, int], float] = {}
    for obs_date, value in points:
        quarter = (obs_date.month - 1) // 3 + 1
        by_q[(obs_date.year, quarter)] = value
    levels = [by_q[k] for k in sorted(by_q)]
    growth = _quarterly_growth_rates(levels)
    est = _estimate_vs_rolling_mean(
        growth,
        window=8,
        above=True,
        source=f"fred:{GDP_SERIES}",
        notes="Real GDP q/q annualized vs 8q mean",
    )
    return {"us_gdp_above_consensus": est} if est else {}


async def estimate_recession(fred: FredClient) -> dict[str, RateEstimate]:
    points = await fred.fetch_observations(RECESSION_SERIES, observation_start="1990-01-01")
    monthly = _monthly_last(points)
    outcomes = [v >= 0.5 for v in monthly[-240:]]
    return {
        "us_recession_12m": _estimate_from_binary_outcomes(
            outcomes,
            source=f"fred:{RECESSION_SERIES}",
            notes="Andel måneder i recession (USREC, sidste 20 år)",
        ),
    }


async def estimate_eu_hicp(fred: FredClient) -> dict[str, RateEstimate]:
    try:
        points = await fred.fetch_observations(EU_HICP_SERIES, observation_start="2000-01-01")
    except httpx.HTTPStatusError:
        return {}
    monthly = _monthly_last(points)
    mom_pct = [
        (monthly[i] / monthly[i - 1] - 1.0) * 100.0
        for i in range(1, len(monthly))
        if monthly[i - 1] > 0
    ]
    est = _estimate_vs_rolling_mean(
        mom_pct,
        window=12,
        above=True,
        source=f"fred:{EU_HICP_SERIES}",
        notes="Eurozone HICP MoM % vs 12m mean",
    )
    return {"eu_hicp_above_consensus": est} if est else {}


async def build_all_estimates(fred: FredClient | None) -> dict[str, RateEstimate]:
    """Samlet kategori → estimat (FRED + priors)."""
    estimates: dict[str, RateEstimate] = dict(PRIOR_ESTIMATES)
    if fred is None:
        return estimates

    for builder in (
        estimate_fed_outcomes,
        estimate_cpi_surprises,
        estimate_nfp_surprises,
        estimate_gdp_surprise,
        estimate_recession,
        estimate_eu_hicp,
    ):
        estimates.update(await builder(fred))

    return estimates


def categories_missing_estimates(
    estimates: dict[str, RateEstimate],
) -> list[BaseRateCategory]:
    return [c for c in BASE_RATE_CATEGORIES if c.category not in estimates]
