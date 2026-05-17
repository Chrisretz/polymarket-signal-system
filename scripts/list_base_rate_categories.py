"""Vis godkendte base rate-kategorier (Uge 4, Dag 1)."""

from __future__ import annotations

from pss.base_rates.categories import BASE_RATE_CATEGORIES


def main() -> None:
    macro = [c for c in BASE_RATE_CATEGORIES if c.vertical == "macro"]
    eu = [c for c in BASE_RATE_CATEGORIES if c.vertical == "eu_politics"]

    print(f"Base rate-kategorier: {len(BASE_RATE_CATEGORIES)} total\n")
    print(f"Macro ({len(macro)}):")
    for c in macro:
        print(f"  {c.category:28} — {c.description}")

    print(f"\nEU politics ({len(eu)}):")
    for c in eu:
        print(f"  {c.category:28} — {c.description}")

    print("\nlist_base_rate_categories: ok")


if __name__ == "__main__":
    main()
