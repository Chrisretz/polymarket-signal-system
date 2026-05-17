"""Regressionstest for base-rate classifier (centralbanker)."""

from __future__ import annotations

from pss.base_rates.classifier import classify_market_fields

CASES: list[tuple[str, str | None]] = [
    (
        "No change in Bank of Japan's interest rates after the June 2026 meeting?",
        "boj_hold",
    ),
    (
        "Bank of Japan decreases interest rates after the June 2026 meeting?",
        "boj_cut",
    ),
    (
        "Will the ECB announce a 50+ bps decrease at the June 2026 meeting?",
        None,
    ),
    (
        "Will the ECB announce a 50+ bps increase at the June 2026 meeting?",
        None,
    ),
    (
        "Will the ECB cut rates at the June 2026 meeting?",
        "ecb_cut",
    ),
    (
        "Will the Fed cut rates by 25bps at the March FOMC meeting?",
        "fed_cut_25bps",
    ),
    (
        "Will ECB leave rates unchanged at the April meeting?",
        "ecb_hold",
    ),
    (
        "Will the Bank of England hike rates in 2026?",
        None,
    ),
    (
        "US CPI above expectations for January?",
        "us_cpi_above_consensus",
    ),
]


def main() -> None:
    failed = 0
    for question, expected in CASES:
        got = classify_market_fields(question=question, primary_vertical="macro")
        ok = got == expected
        status = "ok" if ok else "FAIL"
        print(f"[{status}] {question[:60]!r}…")
        print(f"       expected={expected!r}  got={got!r}\n")
        if not ok:
            failed += 1

    if failed:
        raise SystemExit(1)
    print("test_classifier: ok")


if __name__ == "__main__":
    main()
