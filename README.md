# Polymarket Signal System (PSS)

Kvantitativt tradingsystem til Polymarket prediction markets.

- [STRATEGY.md](STRATEGY.md) — strategi, edge-hypoteser, risk
- [IMPLEMENTATION.md](IMPLEMENTATION.md) — teknisk implementation og ugeplan

## Lokal opsætning

```bash
uv sync --extra dev
docker compose up -d
docker compose ps
uv run python scripts/verify_setup.py
uv run python scripts/init_db.py
uv run python scripts/verify_schema.py
uv run pss
```

### Telegram (Dag 4)

1. Opret bot via [@BotFather](https://t.me/BotFather) (`/newbot`) → kopier token til `TELEGRAM_BOT_TOKEN`
2. Åbn chat med din bot og send `/start`
3. Find dit `chat_id` (fx [@userinfobot](https://t.me/userinfobot)) → `TELEGRAM_CHAT_ID`
4. Test:

```bash
uv run python scripts/test_telegram.py
```

### Gamma API (Dag 5)

```bash
uv run python scripts/test_gamma.py
```

### Market discovery (Uge 2, Dag 1)

Kræver Docker/Postgres. Første kørsel kan tage flere minutter (pagination + rate limit).

```bash
uv run python scripts/run_market_discovery.py
```

### Price snapshots (Uge 2, Dag 2)

Kræver at `markets` allerede er fyldt. Første kørsel tager ~3-4 min.

```bash
uv run python scripts/run_price_snapshot.py
```

### Scheduler (Uge 2, Dag 3)

Kræver Docker/Postgres. Kører discovery (hver time) og snapshots (hver 10. min).
Kører begge jobs én gang med det samme ved opstart.

```bash
uv run python -m pss.scheduler
```

Tjek job-plan uden at starte pipeline:

```bash
uv run python scripts/check_scheduler_jobs.py
```

### Struktureret logging (Uge 2, Dag 4)

Standard i `development`: læsbare logs. Sæt `LOG_FORMAT=json` i `.env` (eller `ENVIRONMENT=production`) for én JSON-linje per event.

```bash
uv run python scripts/test_logging.py
LOG_FORMAT=json uv run python scripts/test_logging.py
```

Kør kommandoerne **én ad gangen** (undgå `#`-kommentarer på samme linje i terminalen).

Alle secrets og lokale indstillinger ligger i **`.env`** i projektroden (filen committes ikke til git). Database: `localhost:5432`, bruger/db `pss`, password som i din `.env`.

## Deploy til Railway (Uge 2, Dag 5)

PSS kører i skyen som **én worker**: scheduler (discovery + snapshots 24/7).  
Database skal understøtte **TimescaleDB** (hypertables) — standard Railway Postgres uden extension er ikke nok.

### Anbefalet opsætning

1. **Database:** [Timescale Cloud](https://www.timescale.com/) (eller anden Postgres med `timescaledb`-extension). Kopiér connection string.
2. **Railway:** Nyt projekt → **Deploy from GitHub** (dette repo).
3. **Service variables** (se `env.template`):
   - `DATABASE_URL` = connection string fra Timescale
   - `ENVIRONMENT=production`
   - `LOG_FORMAT=json`
   - `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` (valgfrit men anbefalet)
4. Railway bruger `Dockerfile` + `railway.toml` automatisk.
5. Ved deploy: migrationer (`init_db`) → scheduler starter.

### Verificér deploy

I Railway → **Deployments** → **View logs**. Forvent JSON-linjer:

- `logging_configured`
- `scheduler_started`
- `job_finished` for `market_discovery` og `price_snapshot`

### Lokal test af Docker-image (valgfrit)

```bash
docker build -t pss-scheduler .
docker run --env-file .env pss-scheduler
```

Kræver at `.env` peger på en reachable database (ikke `localhost` fra containerens perspektiv).
