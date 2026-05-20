# Polymarket Signal System (PSS)

Kvantitativt tradingsystem til Polymarket prediction markets.

- [STRATEGY.md](STRATEGY.md) — strategi, edge-hypoteser, risk
- [IMPLEMENTATION.md](IMPLEMENTATION.md) — teknisk implementation og ugeplan
- [PROGRESS.md](PROGRESS.md) — **hvilke uger er implementeret** (✅ / 🟡 / ⬜)
- [docs/strategies/base_rate_fade.md](docs/strategies/base_rate_fade.md) — strategi A (v0, drift og review)

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

PSS kører i skyen som **én worker**: scheduler (discovery + snapshots + signal-scan 24/7).  
Database skal understøtte **TimescaleDB** (hypertables) — standard Railway Postgres uden extension er ikke nok.

**Vigtigt:** Kør kun scheduler **ét sted** (Railway *eller* lokal `uv run python -m pss.scheduler`).

### Anbefalet opsætning

1. **Database:** [Timescale Cloud](https://www.timescale.com/) (samme DB som lokal `.env`).
2. **Railway:** Projekt → **Deploy from GitHub** → `Chrisretz/polymarket-signal-system` → `main`.
3. **Service variables** — åbn **selve worker-servicen** (ikke Project → Shared Variables).
   Klik `polymarket-signal-system` → fanen **Variables** → Raw Editor eller Add:
   - `DATABASE_URL`, `DATABASE_SSL_INSECURE=true`
   - `ENVIRONMENT=production`, `LOG_FORMAT=json`, `LOG_LEVEL=WARNING`
   - `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`
   - `FRED_API_KEY` (base rates), `BANKROLL_USD=10000`
   - Sæt **ikke** `PORT` manuelt — Railway injicerer den (medmindre docs siger andet).
4. Railway bruger `Dockerfile` + `railway.toml` automatisk.
5. Ved deploy: migrationer (`init_db`) → scheduler med 3 jobs (discovery, snapshot, signal_scan).

### Verificér deploy

I Railway → **Deployments** → **View logs**. Forvent JSON-linjer:

- `logging_configured`
- `scheduler_started` (3 jobs)
- `job_finished` for `market_discovery`, `price_snapshot`, `signal_scan`

### Lokal test af Docker-image (valgfrit)

```bash
docker build -t pss-scheduler .
docker run --env-file .env pss-scheduler
```

Kræver at `.env` peger på en reachable database (ikke `localhost` fra containerens perspektiv).

## Dashboard (Uge 9)

Streamlit-UI mod samme database som scheduler (`.env` med `DATABASE_URL`).

```bash
uv run streamlit run src/pss/dashboard/app.py
```

Åbner typisk `http://localhost:8501` — sider: **Signaler**, **Positioner**, **Journal**, **Performance** (drawdown-alerts på forsiden og under Performance).

Se [PROGRESS.md](PROGRESS.md) for status per uge.

### Dashboard online (Railway)

Opret en **anden Railway-service** i samme projekt (scheduler og dashboard skal ikke dele én container):

1. **New Service** → samme GitHub-repo → branch `main`.
2. **Settings → Build:** `Dockerfile Path` = **`Dockerfile.dashboard`** (præcis det — ikke `Dockerfile`).  
   **Settings → Deploy → Config-as-code:** `railway.dashboard.json` (valgfrit, healthcheck til Streamlit).
3. Efter deploy: **View logs** skal vise `PSS STREAMLIT DASHBOARD` — **ikke** `PSS: starter scheduler`.  
   Hvis browseren kun viser `ok`, kører forkert image (scheduler-healthcheck).
4. **Variables** (samme som worker, minus scheduler-specifikke):
   - `DATABASE_URL`, `DATABASE_SSL_INSECURE=true`
   - `ENVIRONMENT=production`, `BANKROLL_USD=10000`
   - Sæt **ikke** `PORT` manuelt.
5. **Networking → Generate domain** (fx `pss-dashboard.up.railway.app`).
6. Åbn URL fra telefon/anden PC.

Scheduler-serviceen beholder `Dockerfile` + `docker_entrypoint.sh` uændret.

## Telegram: link til Polymarket

Nye signaler inkluderer **«Åbn marked på Polymarket»** (HTML-link) når `markets.slug` findes i DB.  
URL gemmes også i `signal_metadata.polymarket_url` og vises i dashboard under **Signaler**.

Test lokalt:

```bash
uv run python scripts/notify_test_signal.py
```
