# Polymarket Signal System (PSS)

Kvantitativt analyse- og handelssystem til Polymarket prediction markets.

**Status (maj 2026):** Pivot fra Strategi A (base_rate_fade) til Strategi C (cross-market konsistens arbitrage). Cleanup-fase startet. Se CLEANUP.md, STRATEGY.md og IMPLEMENTATION.md.

## Strategi-historik

| Version | Strategi | Status | Hvorfor |
|---------|----------|--------|---------|
| v1.0 | Base rate fade (Strategi A) | Frosset permanent | Backtest viste 70% suspect classification; live ECB-test viste 80pp model-fejl; CB-markeder er for velinformerede |
| v2.0 | Cross-market konsistens (Strategi C) | Research-fase | Ren matematisk arbitrage, ingen forudsigelse krævet |

Arkiveret kontekst: `data/archive/invalid_baseline/` indeholder den oprindelige backtest fra Strategi A som dokumentation af hvorfor strategi-skiftet skete.

## Dokumenter

- [STRATEGY.md](STRATEGY.md) - aktuel strategi, edge-hypotese, risici
- [IMPLEMENTATION.md](IMPLEMENTATION.md) - teknisk implementering og ugeplan
- [CLEANUP.md](CLEANUP.md) - oprydningsplan ved pivot fra A til C
- [PROGRESS.md](PROGRESS.md) - status per fase

## Lokal opsætning

```bash
uv sync --extra dev
docker compose up -d
docker compose ps
uv run python scripts/verify_setup.py
uv run python scripts/init_db.py
uv run python scripts/verify_schema.py
```

### Telegram

1. Opret bot via [@BotFather](https://t.me/BotFather) (`/newbot`) - kopier token til `TELEGRAM_BOT_TOKEN`
2. Åbn chat med din bot og send `/start`
3. Find dit `chat_id` (fx [@userinfobot](https://t.me/userinfobot)) - `TELEGRAM_CHAT_ID`
4. Test: `uv run python scripts/test_telegram.py`

### Gamma API

```bash
uv run python scripts/test_gamma.py
```

### Market og event discovery

```bash
uv run python scripts/run_market_discovery.py
uv run python scripts/run_event_discovery.py  # NY for Strategi C
```

### Snapshot pipeline

```bash
uv run python scripts/run_price_snapshot.py
uv run python scripts/run_event_snapshot.py  # NY for Strategi C
```

### Scheduler

Kører alle ingestion-jobs på faste intervaller.

```bash
uv run python -m pss.scheduler
```

Tjek job-plan: `uv run python scripts/check_scheduler_jobs.py`

### Struktureret logging

Standard i development: læsbare logs. Sæt `LOG_FORMAT=json` for én JSON-linje per event.

```bash
uv run python scripts/test_logging.py
LOG_FORMAT=json uv run python scripts/test_logging.py
```

Alle secrets ligger i `.env` (ikke committet til git).

## Deploy til Railway

PSS kører som én worker med scheduler (discovery + snapshots 24/7).
Database skal understøtte TimescaleDB.

**Vigtigt:** Kør kun scheduler ét sted (Railway eller lokal).

### Opsætning

1. Database: [Timescale Cloud](https://www.timescale.com/)
2. Railway: Deploy from GitHub
3. Service variables (i selve worker-service, ikke project-level):
   - `DATABASE_URL`, `DATABASE_SSL_INSECURE=true`
   - `ENVIRONMENT=production`, `LOG_FORMAT=json`, `LOG_LEVEL=WARNING`
   - `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`
   - `BANKROLL_USD=10000`

Bemærk: `FRED_API_KEY` er ikke længere nødvendig efter pivot til Strategi C.

## Tekniske valg

- Python 3.11+ med uv som package manager
- PostgreSQL 16 + TimescaleDB for tidsserie-data
- SQLAlchemy 2.0 + Alembic migrations
- httpx + py-clob-client for Polymarket API
- APScheduler for jobs
- Streamlit for dashboard
- Telegram for alerts

## Edge-hypotese (Strategi C kort)

Polymarket events med mutually exclusive outcomes bør summere til P(yes) = 1.0. Når sum afviger fra 1.0 med mere end friktion, eksisterer ren matematisk arbitrage. Ingen forudsigelse om udfald nødvendig.

Realistisk forventning: 2-10 trades/måned, 100-500 USD/trade, edge 2-6pp efter friktion. Skalerer ikke godt opad.

Se STRATEGY.md for fuld hypotese, risici, og stop-kriterier.
