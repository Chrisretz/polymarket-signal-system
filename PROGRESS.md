# PSS — implementeringsstatus (ugeplan)

Levende overblik over [IMPLEMENTATION.md](IMPLEMENTATION.md) / [STRATEGY.md](STRATEGY.md).  
Opdateres når en uge eller væsentlig del-leverance er på plads.

**Legende:** ✅ færdig · 🟡 delvist · ⬜ ikke startet

| Uge | Emne | Status | Noter |
|-----|------|--------|--------|
| **1** | Setup, DB, Gamma, Telegram | ✅ | `config`, Alembic, `GammaClient`, Docker |
| **2** | Data-pipeline, scheduler, Railway | ✅ | Discovery, snapshots, deploy |
| **3** | Manuel Polymarket-research | ⬜ | Bruger-/journal-opgave (`JOURNAL.md`) |
| **4** | Base rates + classifier | ✅ | FRED seed, `classifier.py`, `has_base_rate` |
| **5** | Strategi A (kode) | ✅ | `base_rate_fade`, risk, persist, Telegram |
| **6** | Strategi A (drift + review) | ✅ | Journal, review-scripts, tuning, Railway signal_scan |
| **7** | Backtest strategi A | 🟡 | Engine, backfill CLOB, rapporter — classifier-fix mangler |
| **8** | Strategi B (`StalePrice`) + news | ⬜ | Ikke startet |
| **9** | Streamlit dashboard | 🟡 | Lokal + Railway-deploy klar; Polymarket-links i Telegram/dashboard |
| **10** | Cross-market + vol crush | ⬜ | |
| **11–12** | Paper trading launch | ⬜ | |

## Uge 7 (detalje)

| Leverance | Status |
|-----------|--------|
| Walk-forward backtest-engine | ✅ `src/pss/backtesting/` |
| CLOB backfill (`backfill_price_history.py`) | ✅ |
| Analyse (`analyze_backtest.py`, `backtest_week7_report.py`) | ✅ |
| Beslutning strategi A | 🟡 Foreløbig: kalibrer classifier (CPI-niveau vs surprise) |

## Uge 9 (detalje)

| Leverance | Status |
|-----------|--------|
| Side 1 — Signaler | ✅ `dashboard/pages/1_Signaler.py` |
| Side 2 — Positioner | ✅ `dashboard/pages/2_Positioner.py` |
| Side 3 — Journal | ✅ `dashboard/pages/3_Journal.py` |
| Side 4 — Performance | ✅ `dashboard/pages/4_Performance.py` |
| Drawdown 10/15/20 % | ✅ `dashboard/drawdown.py` + forside/performance |
| E2E workflow-test | ⬜ |
| Polymarket-link i Telegram + dashboard | ✅ |
| Railway dashboard (`Dockerfile.dashboard`) | ✅ dokumenteret i README |

## Kommandoer

```bash
# Dashboard (lokal)
uv run streamlit run src/pss/dashboard/app.py

# Backtest (uge 7)
uv run python scripts/backfill_price_history.py --start 2026-04-01
uv run python scripts/backtest_week7_report.py --start 2026-04-01
```

*Sidst opdateret: maj 2026 (uge 9 dashboard start).*
