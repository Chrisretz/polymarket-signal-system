"""Kanoniske base rate-kategorier (Uge 4, Dag 1).

Macro primær, EU politics sekundær — matcher STRATEGY.md.
Bruges af seed/classifier i dag 2–5.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Vertical = Literal["macro", "eu_politics"]


@dataclass(frozen=True, slots=True)
class BaseRateCategory:
    """Én historisk event-type med fast `category`-slug i `base_rates`-tabellen."""

    category: str
    description: str
    vertical: Vertical
    keywords: tuple[str, ...]
    fred_hint: str | None = None


BASE_RATE_CATEGORIES: tuple[BaseRateCategory, ...] = (
    # --- US macro (Fed + data prints) ---
    BaseRateCategory(
        category="fed_hold",
        description="Fed holder target range uændret ved FOMC-møde",
        vertical="macro",
        keywords=("fomc", "fed hold", "fed pause", "federal reserve hold", "fed meeting"),
        fred_hint="FEDFUNDS",
    ),
    BaseRateCategory(
        category="fed_cut_25bps",
        description="Fed sænker renten 25 basis points ved FOMC-møde",
        vertical="macro",
        keywords=(
            "cut 25",
            "25bp cut",
            "25bps",
            "cut rates",
            "rate cut",
            "fed cut",
            "lower rates",
        ),
    ),
    BaseRateCategory(
        category="fed_hike_25bps",
        description="Fed hæver renten 25 basis points ved FOMC-møde",
        vertical="macro",
        keywords=(
            "hike 25",
            "25bp hike",
            "25bps",
            "raise rates",
            "rate hike",
            "fed hike",
            "hike rates",
        ),
    ),
    BaseRateCategory(
        category="us_cpi_above_consensus",
        description="US CPI (headline) over analyst consensus for printet",
        vertical="macro",
        keywords=("cpi", "inflation", "above expectations", "hot print"),
        fred_hint="CPIAUCSL",
    ),
    BaseRateCategory(
        category="us_cpi_below_consensus",
        description="US CPI (headline) under analyst consensus for printet",
        vertical="macro",
        keywords=("cpi", "inflation", "below expectations", "cool print"),
        fred_hint="CPIAUCSL",
    ),
    BaseRateCategory(
        category="us_nfp_above_consensus",
        description="Nonfarm payrolls over consensus",
        vertical="macro",
        keywords=("nonfarm", "nfp", "payrolls", "jobs report", "above expectations"),
        fred_hint="PAYEMS",
    ),
    BaseRateCategory(
        category="us_nfp_below_consensus",
        description="Nonfarm payrolls under consensus",
        vertical="macro",
        keywords=("nonfarm", "nfp", "payrolls", "jobs report", "below expectations"),
        fred_hint="PAYEMS",
    ),
    BaseRateCategory(
        category="us_gdp_above_consensus",
        description="US GDP (advance/second/third) over consensus",
        vertical="macro",
        keywords=("gdp", "growth", "above expectations"),
        fred_hint="GDP",
    ),
    BaseRateCategory(
        category="us_recession_12m",
        description="US recession inden for 12 måneder (NBER-style markedsdefinition)",
        vertical="macro",
        keywords=("recession", "economic contraction", "nber"),
    ),
    # --- EU macro (ECB + inflation) ---
    BaseRateCategory(
        category="ecb_hold",
        description="ECB holder key policy rates uændret",
        vertical="macro",
        keywords=("ecb hold", "ecb unchanged", "ecb meeting", "lagarde"),
    ),
    # --- Japan (BOJ) ---
    BaseRateCategory(
        category="boj_hold",
        description="Bank of Japan holder policy rate uændret ved møde",
        vertical="macro",
        keywords=("boj hold", "bank of japan hold", "boj unchanged", "boj meeting"),
    ),
    BaseRateCategory(
        category="boj_cut",
        description="BOJ sænker policy rate ved møde",
        vertical="macro",
        keywords=("boj cut", "bank of japan cut", "boj lower"),
    ),
    BaseRateCategory(
        category="boj_hike",
        description="BOJ hæver policy rate ved møde",
        vertical="macro",
        keywords=("boj hike", "bank of japan hike", "boj raise"),
    ),
    BaseRateCategory(
        category="ecb_cut",
        description="ECB sænker deposit/refinancing rate ved møde",
        vertical="macro",
        keywords=("ecb cut", "ecb lower", "rate cut"),
    ),
    BaseRateCategory(
        category="ecb_hike",
        description="ECB hæver key policy rates ved møde",
        vertical="macro",
        keywords=("ecb hike", "ecb raise", "rate hike"),
    ),
    BaseRateCategory(
        category="eu_hicp_above_consensus",
        description="Eurozone HICP/inflation print over consensus",
        vertical="macro",
        keywords=("hicp", "eurozone inflation", "eu cpi", "above expectations"),
    ),
    # --- EU politics ---
    BaseRateCategory(
        category="eu_election_incumbent_wins",
        description="Incumbent party/blok vinder nationalt valg (EU-medlemsstat)",
        vertical="eu_politics",
        keywords=("election", "wins", "victory", "incumbent", "parliament"),
    ),
    BaseRateCategory(
        category="eu_coalition_formed",
        description="Ny regering/koalition dannes inden deadline efter valg",
        vertical="eu_politics",
        keywords=("coalition", "government formed", "cabinet"),
    ),
    BaseRateCategory(
        category="eu_referendum_yes",
        description="Ja-side vinder folkeafstemning (EU-relevant)",
        vertical="eu_politics",
        keywords=("referendum", "vote yes", "passes"),
    ),
)
