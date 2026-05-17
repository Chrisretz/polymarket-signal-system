"""Match Polymarket-markeder til base_rate-kategori via keywords."""

from __future__ import annotations

from typing import Literal

from pss.base_rates.categories import BASE_RATE_CATEGORIES, BaseRateCategory, Vertical

Institution = Literal["fed", "ecb", "boj", "boe"]

VERTICAL_ALIASES: dict[str, Vertical] = {
    "macro": "macro",
    "eu_politics": "eu_politics",
}

# Rækkefølge: mere specifik institution før generiske ord
INSTITUTION_MARKERS: tuple[tuple[Institution, tuple[str, ...]], ...] = (
    (
        "boj",
        (
            "bank of japan",
            "boj's",
            "boj ",
            " boj",
            "boj.",
            "japanese central bank",
        ),
    ),
    (
        "ecb",
        (
            "european central bank",
            "ecb ",
            " ecb",
            "ecb's",
            "ecb.",
            "christine lagarde",
            "lagarde",
        ),
    ),
    (
        "boe",
        (
            "bank of england",
            "boe ",
            " boe",
            "monetary policy committee",
            "mpc meeting",
        ),
    ),
    (
        "fed",
        (
            "fomc",
            "federal reserve",
            "fed funds",
            "fed's",
            "the fed",
            " fed ",
            "fed.",
            "jerome powell",
            "powell",
        ),
    ),
)

# Mapping institution + rente-handling → category slug
_INSTITUTION_RATE_CATEGORIES: dict[Institution, dict[str, str]] = {
    "fed": {
        "hold": "fed_hold",
        "cut": "fed_cut_25bps",
        "hike": "fed_hike_25bps",
    },
    "ecb": {
        "hold": "ecb_hold",
        "cut": "ecb_cut",
        "hike": "ecb_hike",
    },
    "boj": {
        "hold": "boj_hold",
        "cut": "boj_cut",
        "hike": "boj_hike",
    },
}

_CUT_PHRASES = (
    "cut rates",
    "rate cut",
    "cut 25",
    "25bp cut",
    "25bps",
    "bps decrease",
    "bp decrease",
    "lower rates",
    "reduce rates",
    "decrease rates",
    "decreases interest",
    "decrease interest",
    "ecb cut",
    "boj cut",
    "fed cut",
    "announce a decrease",
)
_HIKE_PHRASES = (
    "hike rates",
    "rate hike",
    "hike 25",
    "25bp hike",
    "raise rates",
    "increase rates",
    "increases interest",
    "increase interest",
    "bps increase",
    "bp increase",
    "ecb hike",
    "boj hike",
    "fed hike",
    "announce an increase",
    "announce a increase",
)
_HOLD_PHRASES = (
    "no change",
    "unchanged",
    "hold rates",
    "leave rates",
    "steady rates",
    "maintain rates",
    "keep rates",
    "pause",
    "leave unchanged",
)


def market_search_text(
    question: str,
    description: str | None = None,
    category: str | None = None,
) -> str:
    parts = [question or "", description or "", category or ""]
    return " ".join(p for p in parts if p).lower()


def detect_institution(text: str) -> Institution | None:
    """Identificér centralbank i markeds-tekst (højst én)."""
    hits: list[Institution] = []
    for institution, markers in INSTITUTION_MARKERS:
        if any(marker in text for marker in markers):
            hits.append(institution)
    if not hits:
        return None
    if len(hits) == 1:
        return hits[0]
    # Flere institutioner nævnt — vælg den med længst specifikt match
    best: Institution | None = None
    best_len = 0
    for institution in hits:
        for marker in INSTITUTION_MARKERS:
            if marker[0] != institution:
                continue
            for m in marker[1]:
                if m in text and len(m) > best_len:
                    best_len = len(m)
                    best = institution
    return best


def _rate_action(text: str) -> Literal["hold", "cut", "hike"] | None:
    has_cut = any(p in text for p in _CUT_PHRASES) or (
        " cut " in f" {text} " and "rate" in text
    )
    has_hike = any(p in text for p in _HIKE_PHRASES) or (
        " hike " in f" {text} " and "rate" in text
    )
    has_hold = any(p in text for p in _HOLD_PHRASES)

    if has_cut and not has_hike:
        return "cut"
    if has_hike and not has_cut:
        return "hike"
    if has_hold and not has_cut and not has_hike:
        return "hold"
    if has_hold:
        return "hold"
    return None


def classify_institution_rate(text: str, institution: Institution) -> str | None:
    """Klassificér rentebeslutning for kendt centralbank."""
    if institution not in _INSTITUTION_RATE_CATEGORIES:
        return None
    action = _rate_action(text)
    if action is None:
        return None
    return _INSTITUTION_RATE_CATEGORIES[institution].get(action)


def _score_category(text: str, cat: BaseRateCategory) -> int:
    score = 0
    for kw in cat.keywords:
        if kw in text:
            score += 10 + len(kw)

    if score == 0:
        return 0

    if "above" in cat.category and "below expectations" in text:
        score -= 40
    if "below" in cat.category and "above expectations" in text:
        score -= 40

    if cat.category == "fed_hold" and any(
        x in text for x in ("cut rates", "rate cut", "fed cut", "hike rates", "rate hike", "fed hike")
    ):
        score -= 40
    if cat.category.startswith("fed_") and any(
        x in text for x in ("bank of japan", "boj", "ecb", "european central bank", "bank of england")
    ):
        score -= 50
    if cat.category.startswith("ecb_") and any(
        x in text
        for x in ("bank of japan", "boj", "fomc", "federal reserve", "fed ", "bank of england")
    ):
        score -= 50
    if cat.category.startswith("boj_") and any(
        x in text for x in ("fomc", "federal reserve", "ecb", "european central bank", "bank of england")
    ):
        score -= 50

    if cat.category.startswith("us_") and any(
        x in text for x in ("eurozone", "hicp", "ecb ", "european central")
    ):
        score -= 25

    if cat.vertical == "eu_politics" and not any(
        x in text for x in ("election", "referendum", "coalition", "parliament", "government")
    ):
        if cat.category != "eu_referendum_yes" or "referendum" not in text:
            score -= 15

    return score


def classify_text(
    text: str,
    *,
    primary_vertical: str | None = None,
    min_score: int = 12,
) -> str | None:
    """Returnér bedste `base_rates.category` slug eller None."""
    if not text.strip():
        return None

    institution = detect_institution(text)
    if institution is not None:
        inst_cat = classify_institution_rate(text, institution)
        if inst_cat is not None:
            return inst_cat

    vertical: Vertical | None = None
    if primary_vertical and primary_vertical in VERTICAL_ALIASES:
        vertical = VERTICAL_ALIASES[primary_vertical]

    candidates = [
        c
        for c in BASE_RATE_CATEGORIES
        if vertical is None or c.vertical == vertical
    ]

    best_cat: BaseRateCategory | None = None
    best_score = 0
    for cat in candidates:
        score = _score_category(text, cat)
        if score > best_score or (
            score == best_score and best_cat and len(cat.category) > len(best_cat.category)
        ):
            best_score = score
            best_cat = cat

    if best_cat is None or best_score < min_score:
        return None
    return best_cat.category


def _question_too_granular_for_cb_base_rate(question: str) -> bool:
    """Polymarket «25 bps decrease»-kontrakter passer ikke til aggregeret hold/cut/hike."""
    q = question.lower()
    # Polymarket multi-outcome («announce 50+ bps decrease»), ikke FOMC «25bps cut»
    return "announce" in q and any(
        x in q for x in ("50+ bps", "50 bps", "25 bps", "75 bps", "100 bps", "0 bps")
    )


def classify_market_fields(
    *,
    question: str,
    description: str | None = None,
    category: str | None = None,
    primary_vertical: str | None = None,
) -> str | None:
    """Klassificér marked; rente-handling (hold/cut/hike) kun fra spørgsmålstekst."""
    text = market_search_text(question, description, category)
    question_only = (question or "").lower()

    if _question_too_granular_for_cb_base_rate(question_only):
        return None

    institution = detect_institution(text)
    if institution is not None:
        inst_cat = classify_institution_rate(question_only, institution)
        if inst_cat is not None:
            return inst_cat

    return classify_text(text, primary_vertical=primary_vertical)


__all__ = [
    "classify_institution_rate",
    "classify_market_fields",
    "classify_text",
    "detect_institution",
    "market_search_text",
]
