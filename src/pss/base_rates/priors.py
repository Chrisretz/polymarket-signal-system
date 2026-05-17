"""Faste priors hvor FRED ikke dækker (ECB-møder, EU-politik)."""

from __future__ import annotations

from pss.base_rates.types import RateEstimate

# Konservative startværdier — opdateres når vi har bedre historik (ECB SDW, valgdata).
PRIOR_ESTIMATES: dict[str, RateEstimate] = {
    "ecb_hold": RateEstimate(
        base_probability=0.58,
        sample_size=48,
        confidence_lower=0.44,
        confidence_upper=0.71,
        source="expert_prior_v0",
        notes="ECB Governing Council: ca. andel uændret beslutning (2000–2024, grov)",
    ),
    "ecb_cut": RateEstimate(
        base_probability=0.22,
        sample_size=48,
        confidence_lower=0.12,
        confidence_upper=0.35,
        source="expert_prior_v0",
        notes="ECB: andel møder med netto sænkning",
    ),
    "ecb_hike": RateEstimate(
        base_probability=0.20,
        sample_size=48,
        confidence_lower=0.11,
        confidence_upper=0.32,
        source="expert_prior_v0",
        notes="ECB: andel møder med netto hævning",
    ),
    "boj_hold": RateEstimate(
        base_probability=0.78,
        sample_size=40,
        confidence_lower=0.64,
        confidence_upper=0.88,
        source="expert_prior_v0",
        notes="BOJ: andel møder uden policy rate-ændring (grov, 2000–2024)",
    ),
    "boj_cut": RateEstimate(
        base_probability=0.12,
        sample_size=40,
        confidence_lower=0.05,
        confidence_upper=0.24,
        source="expert_prior_v0",
        notes="BOJ: andel møder med sænkning",
    ),
    "boj_hike": RateEstimate(
        base_probability=0.10,
        sample_size=40,
        confidence_lower=0.04,
        confidence_upper=0.22,
        source="expert_prior_v0",
        notes="BOJ: andel møder med hævning",
    ),
    "eu_election_incumbent_wins": RateEstimate(
        base_probability=0.42,
        sample_size=30,
        confidence_lower=0.28,
        confidence_upper=0.57,
        source="expert_prior_v0",
        notes="EU nationalvalg: incumbent/blok vinder (historisk grov)",
    ),
    "eu_coalition_formed": RateEstimate(
        base_probability=0.75,
        sample_size=25,
        confidence_lower=0.58,
        confidence_upper=0.87,
        source="expert_prior_v0",
        notes="Koalition dannet inden typisk deadline efter fragmenterede valg",
    ),
    "eu_referendum_yes": RateEstimate(
        base_probability=0.48,
        sample_size=20,
        confidence_lower=0.30,
        confidence_upper=0.66,
        source="expert_prior_v0",
        notes="EU-relevante folkeafstemninger: ja-side vinder",
    ),
}
