# Polymarket Kvant-system: Teknisk implementering
## IMPLEMENTATION.md

**Version:** 1.0
**Dato:** Maj 2026
**Status:** Klar til opsætning i Cursor

> Dette dokument er det praktiske supplement til `STRATEGY.md`. Det dækker projekt-struktur, tech stack, database-schema, konkret API-integration, og uge-for-uge implementeringsplan. Alle kodeeksempler er udgangspunkter, ikke færdige løsninger. Verificér løbende mod den officielle Polymarket-dokumentation, da API'erne ændrer sig.

---

## 1. Beslutninger og antagelser

### 1.1 Tech stack

| Lag | Valg | Begrundelse |
|-----|------|-------------|
| Sprog | Python 3.11+ | Pandas/numpy ecosystem, py-clob-client officielt |
| Pakkehåndtering | `uv` | Markant hurtigere end pip, simpel lock-fil |
| Database | PostgreSQL 16 + TimescaleDB | Timeseries-data er kerne i systemet |
| ORM | SQLAlchemy 2.0 + Alembic | Migrations + typesafety |
| API-klient | py-clob-client + httpx | Polymarket SDK + async fetch til Gamma |
| Async-runtime | asyncio + APScheduler | Scheduled jobs uden Celery-overhead |
| Dashboard | Streamlit | Hurtigt til personlig brug |
| Notifications | python-telegram-bot | Mest pålidelig alert-kanal |
| Backtesting | Custom (pandas + numpy) | Eksisterende frameworks passer dårligt til prediction markets |
| Hosting | Railway eller Fly.io | Simpel deployment, ~20-50 USD/md |
| Secrets | `.env` lokalt, Railway/Fly secrets i prod | Aldrig commit secrets |

### 1.2 Konkrete API-detaljer

**Gamma API (markedsdata, ingen auth):**
- Base URL: `https://gamma-api.polymarket.com`
- Rate limit: cirka 60 requests/min, ingen API-key krævet
- Primære endpoints: `/markets`, `/events`, `/markets/{id}`, `/positions`

**CLOB API (orderbook + trading, wallet auth):**
- Base URL: `https://clob.polymarket.com`
- Rate limit: cirka 100+ req/min authenticated
- Krav: Polygon wallet, USDC (pUSD) til trades, POL til gas
- Auth: L1 (EOA signature) → L2 (HMAC API creds)
- SDK: `py-clob-client` (v0.34.6 er stadig produktion-stabil)

**WebSocket (realtime priser):**
- URL: `wss://ws-subscriptions-clob.polymarket.com/ws/market`
- Limit: max 5 concurrent connections per IP
- Bruges til fokus-markeder, ikke discovery

**Ingen testnet eller paper trading mode.** Polymarket har ikke et sandbox-miljø. Det betyder:
- "Paper trading" implementeres som signal-log uden eksekvering
- Første live test sker med små positioner (10-50 USD) på real money
- Amoy testnet (chain_id 80002) findes for SDK-testing men har ikke real markets

### 1.3 Wallet-arkitektur

Brug **dedicated wallet** for tradingsystemet, separat fra evt. private crypto-holdings.

**Anbefalet setup:**
- Hardware wallet (Ledger) til cold storage af USDC over 50% af bankroll
- Hot wallet med Polygon (EOA, signature_type=0) til aktiv trading
- Polymarket deposit wallet (signature_type=3) for nye konti er nu anbefalet flow
- Aldrig wallet-private keys i kode. Brug `.env` eller key-management

> **Vigtigt:** Verificér først om Polymarket-adgang fra Danmark stadig kræver VPN eller har KYC-restriktioner. Det ændrer sig løbende. Tjek `polymarket.com/learn` før setup.

---

## 2. Projekt-struktur

### 2.1 Repository layout

```
polymarket-quant/
├── README.md
├── STRATEGY.md                  # Strategi-dokument (eksisterende)
├── IMPLEMENTATION.md            # Dette dokument
├── JOURNAL.md                   # Trading-journal (oprettes løbende)
├── PERFORMANCE.md               # Månedlige reviews
├── pyproject.toml               # uv + dependencies
├── .env                         # Lokal config (gitignored, ingen secrets i repo)
├── .gitignore                   # .env, .venv, __pycache__, *.db
├── alembic.ini                  # DB migrations config
├── docker-compose.yml           # PostgreSQL lokalt
│
├── src/
│   ├── polymarket_quant/
│   │   ├── __init__.py
│   │   ├── config.py            # Pydantic settings fra .env
│   │   ├── db/
│   │   │   ├── __init__.py
│   │   │   ├── models.py        # SQLAlchemy models
│   │   │   ├── session.py       # DB connection
│   │   │   └── migrations/      # Alembic
│   │   ├── clients/
│   │   │   ├── __init__.py
│   │   │   ├── gamma.py         # Gamma API wrapper
│   │   │   ├── clob.py          # CLOB API wrapper
│   │   │   └── websocket.py     # WS-stream til fokus-markeder
│   │   ├── ingestion/
│   │   │   ├── __init__.py
│   │   │   ├── market_discovery.py
│   │   │   ├── price_snapshot.py
│   │   │   ├── orderbook_depth.py
│   │   │   └── resolution_check.py
│   │   ├── base_rates/
│   │   │   ├── __init__.py
│   │   │   ├── manual.py        # Hånd-pleget database
│   │   │   ├── fred.py          # Federal Reserve data
│   │   │   ├── ecb.py           # ECB Statistical Data
│   │   │   └── classifier.py    # Match market → base rate
│   │   ├── strategies/
│   │   │   ├── __init__.py
│   │   │   ├── base.py          # Strategy base class
│   │   │   ├── base_rate_fade.py
│   │   │   ├── stale_price.py
│   │   │   ├── cross_market.py
│   │   │   └── volatility_crush.py
│   │   ├── signals/
│   │   │   ├── __init__.py
│   │   │   ├── generator.py     # Genererer signaler fra strategier
│   │   │   └── filters.py       # Risk-filtre før signal udsendes
│   │   ├── risk/
│   │   │   ├── __init__.py
│   │   │   ├── sizing.py        # Kelly + caps
│   │   │   ├── portfolio.py     # Korrelations- og expo-tjek
│   │   │   └── drawdown.py      # Drawdown-regler
│   │   ├── execution/
│   │   │   ├── __init__.py
│   │   │   ├── manual.py        # Genererer trade-tickets til manual exec
│   │   │   └── auto.py          # Auto-execution (fase 2+)
│   │   ├── journal/
│   │   │   ├── __init__.py
│   │   │   ├── pre_trade.py     # 10-spørgsmåls tjekliste
│   │   │   └── post_trade.py    # Post-exit review
│   │   ├── performance/
│   │   │   ├── __init__.py
│   │   │   ├── metrics.py       # Hit rate, Sharpe, drawdown
│   │   │   └── calibration.py   # Kalibrerings-test
│   │   ├── notifications/
│   │   │   ├── __init__.py
│   │   │   └── telegram.py
│   │   └── scheduler.py         # APScheduler job-registration
│   │
│   └── dashboard/
│       ├── __init__.py
│       ├── app.py               # Streamlit hoved-app
│       ├── pages/
│       │   ├── 1_signals.py
│       │   ├── 2_positions.py
│       │   ├── 3_journal.py
│       │   └── 4_performance.py
│       └── components/
│
├── tests/
│   ├── __init__.py
│   ├── test_clients.py
│   ├── test_strategies.py
│   └── test_risk.py
│
├── scripts/
│   ├── init_db.py
│   ├── backfill_markets.py
│   └── manual_journal_entry.py
│
└── backtesting/
    ├── __init__.py
    ├── engine.py
    ├── data_loader.py
    └── notebooks/               # Jupyter til ad-hoc analyse
```

### 2.2 pyproject.toml (uv-format)

```toml
[project]
name = "polymarket-quant"
version = "0.1.0"
description = "Kvantitativt tradingsystem til Polymarket"
requires-python = ">=3.11"
dependencies = [
    # Polymarket
    "py-clob-client>=0.34.6",
    # HTTP og async
    "httpx>=0.27.0",
    "websockets>=12.0",
    # Data
    "pandas>=2.2.0",
    "numpy>=1.26.0",
    "polars>=1.0.0",
    "scipy>=1.13.0",
    # Database
    "sqlalchemy[asyncio]>=2.0.30",
    "asyncpg>=0.29.0",
    "alembic>=1.13.0",
    "psycopg2-binary>=2.9.9",
    # Scheduling
    "apscheduler>=3.10.0",
    # Config
    "pydantic-settings>=2.3.0",
    "python-dotenv>=1.0.0",
    # Notifications
    "python-telegram-bot>=21.0",
    # Dashboard
    "streamlit>=1.35.0",
    "plotly>=5.22.0",
    # Web3 (bruges af py-clob-client)
    "web3>=6.20.0",
    # Logging
    "structlog>=24.2.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.2.0",
    "pytest-asyncio>=0.23.0",
    "ruff>=0.5.0",
    "mypy>=1.10.0",
    "jupyter>=1.0.0",
]

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.mypy]
python_version = "3.11"
strict = true
```

### 2.3 .env (lokal)

```bash
# Polymarket
POLYMARKET_PRIVATE_KEY=        # Hot wallet private key (Polygon)
POLYMARKET_FUNDER_ADDRESS=     # Address der holder USDC
POLYMARKET_SIGNATURE_TYPE=0    # 0=EOA, 1=Magic, 2=Safe, 3=deposit wallet

# Database
DATABASE_URL=postgresql+asyncpg://polyquant:password@localhost:5432/polyquant
DATABASE_URL_SYNC=postgresql://polyquant:password@localhost:5432/polyquant

# Telegram alerts
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=

# Eksterne datakilder
FRED_API_KEY=                  # https://fred.stlouisfed.org/docs/api/api_key.html
TWITTER_BEARER_TOKEN=          # Hvis news flow ønskes

# Operationelle
LOG_LEVEL=INFO
ENVIRONMENT=development        # development eller production
BANKROLL_USD=10000             # Brugt af risk-engine til sizing
```

---

## 3. Database-schema

PostgreSQL med TimescaleDB-extension. Schema er holdt simpelt og udvides løbende.

### 3.1 Komplet schema (SQL)

```sql
-- Aktivér TimescaleDB
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- =====================================================
-- MARKETS: Metadata om Polymarket-markeder
-- =====================================================
CREATE TABLE markets (
    id BIGSERIAL PRIMARY KEY,
    condition_id TEXT NOT NULL UNIQUE,
    question TEXT NOT NULL,
    description TEXT,
    slug TEXT,
    category TEXT,
    subcategory TEXT,
    event_id TEXT,                          -- Hvis del af multi-market event
    yes_token_id TEXT NOT NULL,
    no_token_id TEXT NOT NULL,
    end_date TIMESTAMP WITH TIME ZONE,
    resolution_source TEXT,
    minimum_tick_size NUMERIC(6,4),
    neg_risk BOOLEAN DEFAULT FALSE,
    is_active BOOLEAN DEFAULT TRUE,
    is_closed BOOLEAN DEFAULT FALSE,
    is_resolved BOOLEAN DEFAULT FALSE,
    resolved_outcome TEXT,                  -- "Yes", "No", eller NULL
    resolved_at TIMESTAMP WITH TIME ZONE,
    -- Klassifikation til strategi-routing
    primary_vertical TEXT,                  -- "macro", "eu_politics", "us_politics", "sports", "crypto", "other"
    has_base_rate BOOLEAN DEFAULT FALSE,
    -- Metadata
    raw_metadata JSONB,                     -- Hele raw response fra Gamma
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_markets_active ON markets (is_active, is_closed);
CREATE INDEX idx_markets_vertical ON markets (primary_vertical) WHERE is_active = TRUE;
CREATE INDEX idx_markets_end_date ON markets (end_date) WHERE is_active = TRUE;

-- =====================================================
-- MARKET_SNAPSHOTS: Tidsserier af odds, volume, likviditet
-- =====================================================
CREATE TABLE market_snapshots (
    market_id BIGINT NOT NULL REFERENCES markets(id) ON DELETE CASCADE,
    snapshot_at TIMESTAMP WITH TIME ZONE NOT NULL,
    yes_price NUMERIC(8,5),
    no_price NUMERIC(8,5),
    yes_best_bid NUMERIC(8,5),
    yes_best_ask NUMERIC(8,5),
    spread NUMERIC(8,5),                    -- ask - bid
    volume_24h NUMERIC(18,2),
    volume_total NUMERIC(18,2),
    liquidity_usd NUMERIC(18,2),
    PRIMARY KEY (market_id, snapshot_at)
);

-- Konvertér til TimescaleDB hypertable
SELECT create_hypertable('market_snapshots', 'snapshot_at', chunk_time_interval => INTERVAL '7 days');
CREATE INDEX idx_snapshots_market_time ON market_snapshots (market_id, snapshot_at DESC);

-- =====================================================
-- ORDERBOOK_DEPTH: Detaljerede orderbook-snapshots for fokus-markeder
-- =====================================================
CREATE TABLE orderbook_depth (
    market_id BIGINT NOT NULL REFERENCES markets(id) ON DELETE CASCADE,
    snapshot_at TIMESTAMP WITH TIME ZONE NOT NULL,
    token_id TEXT NOT NULL,                 -- yes eller no token
    bids JSONB NOT NULL,                    -- [{price, size}, ...]
    asks JSONB NOT NULL,
    depth_5pct_bid NUMERIC(18,2),           -- Kapital tilgængelig inden for 5% af mid
    depth_5pct_ask NUMERIC(18,2),
    PRIMARY KEY (market_id, snapshot_at, token_id)
);

SELECT create_hypertable('orderbook_depth', 'snapshot_at', chunk_time_interval => INTERVAL '7 days');

-- =====================================================
-- BASE_RATES: Historiske sandsynligheder per kategori
-- =====================================================
CREATE TABLE base_rates (
    id BIGSERIAL PRIMARY KEY,
    category TEXT NOT NULL,                 -- "fed_rate_hold", "ecb_rate_cut_25bps", "inflation_above_target"
    description TEXT NOT NULL,
    sample_size INTEGER NOT NULL,
    base_probability NUMERIC(5,4) NOT NULL, -- 0.0000-1.0000
    confidence_lower NUMERIC(5,4),
    confidence_upper NUMERIC(5,4),
    source TEXT,
    last_updated TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    notes TEXT
);

CREATE INDEX idx_base_rates_category ON base_rates (category);

-- =====================================================
-- SIGNALS: Genererede handelssignaler
-- =====================================================
CREATE TABLE signals (
    id BIGSERIAL PRIMARY KEY,
    market_id BIGINT NOT NULL REFERENCES markets(id),
    strategy TEXT NOT NULL,                 -- "base_rate_fade", "stale_price", etc.
    generated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    -- Signal-detaljer
    side TEXT NOT NULL,                     -- "BUY_YES", "BUY_NO"
    market_price NUMERIC(8,5) NOT NULL,     -- Pris ved signal-generation
    fair_value_estimate NUMERIC(8,5) NOT NULL,
    edge_pct NUMERIC(6,4) NOT NULL,         -- (fair - market) / market
    confidence NUMERIC(3,2),                -- 0.00-1.00, subjektiv tillid
    -- Sizing
    suggested_size_usd NUMERIC(18,2) NOT NULL,
    kelly_fraction NUMERIC(6,4),
    -- Exit-kriterier
    exit_price_target NUMERIC(8,5),
    exit_date_target TIMESTAMP WITH TIME ZONE,
    exit_conditions JSONB,                  -- Strukturerede conditions
    -- Status
    status TEXT NOT NULL DEFAULT 'NEW',     -- NEW, ACCEPTED, REJECTED, EXPIRED
    rejected_reason TEXT,
    -- Metadata
    signal_metadata JSONB                   -- Strategi-specifik data
);

CREATE INDEX idx_signals_status ON signals (status, generated_at DESC);
CREATE INDEX idx_signals_market ON signals (market_id, generated_at DESC);

-- =====================================================
-- POSITIONS: Aktive og historiske positioner
-- =====================================================
CREATE TABLE positions (
    id BIGSERIAL PRIMARY KEY,
    signal_id BIGINT REFERENCES signals(id),
    market_id BIGINT NOT NULL REFERENCES markets(id),
    strategy TEXT NOT NULL,
    -- Entry
    side TEXT NOT NULL,                     -- "BUY_YES", "BUY_NO"
    entry_price NUMERIC(8,5) NOT NULL,
    entry_size_shares NUMERIC(18,4) NOT NULL,
    entry_size_usd NUMERIC(18,2) NOT NULL,
    entry_fees_usd NUMERIC(18,4),
    entered_at TIMESTAMP WITH TIME ZONE NOT NULL,
    -- Exit
    exit_price NUMERIC(8,5),
    exit_size_shares NUMERIC(18,4),
    exit_size_usd NUMERIC(18,2),
    exit_fees_usd NUMERIC(18,4),
    exited_at TIMESTAMP WITH TIME ZONE,
    exit_reason TEXT,                       -- "target_hit", "stop_loss", "resolved", "thesis_invalid"
    -- PnL
    realized_pnl_usd NUMERIC(18,2),
    realized_pnl_pct NUMERIC(8,4),
    -- Status
    status TEXT NOT NULL DEFAULT 'OPEN',    -- OPEN, CLOSED, RESOLVED
    -- Paper vs live
    is_paper BOOLEAN NOT NULL DEFAULT TRUE,
    -- Metadata
    notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_positions_status ON positions (status, entered_at DESC);
CREATE INDEX idx_positions_strategy ON positions (strategy, status);
CREATE INDEX idx_positions_paper ON positions (is_paper, status);

-- =====================================================
-- DECISIONS_JOURNAL: Pre-trade og post-trade refleksioner
-- =====================================================
CREATE TABLE decisions_journal (
    id BIGSERIAL PRIMARY KEY,
    position_id BIGINT REFERENCES positions(id),
    market_id BIGINT NOT NULL REFERENCES markets(id),
    entry_type TEXT NOT NULL,               -- "PRE_TRADE", "POST_TRADE", "MID_TRADE_NOTE"
    -- Pre-trade tjekliste-svar
    strategy TEXT,
    thesis TEXT,                            -- 1-sætnings tese
    base_rate_estimate NUMERIC(5,4),
    my_probability_estimate NUMERIC(5,4),
    expected_edge_pct NUMERIC(6,4),
    position_size_usd NUMERIC(18,2),
    exit_criteria TEXT,
    invalidation_scenarios TEXT,
    strongest_counter_argument TEXT,
    potential_biases TEXT,
    max_loss_impact TEXT,
    -- Post-trade refleksioner
    outcome_matched_thesis BOOLEAN,
    was_lucky_or_skilled TEXT,              -- "lucky_win", "skilled_win", "unlucky_loss", "deserved_loss"
    lessons_learned TEXT,
    calibration_note TEXT,
    -- Metadata
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_journal_position ON decisions_journal (position_id);

-- =====================================================
-- PERFORMANCE_DAILY: Daglig PnL og porteføljerisiko
-- =====================================================
CREATE TABLE performance_daily (
    date DATE PRIMARY KEY,
    bankroll_start_usd NUMERIC(18,2) NOT NULL,
    bankroll_end_usd NUMERIC(18,2) NOT NULL,
    realized_pnl_usd NUMERIC(18,2) DEFAULT 0,
    unrealized_pnl_usd NUMERIC(18,2) DEFAULT 0,
    total_pnl_usd NUMERIC(18,2) DEFAULT 0,
    -- Eksponering
    open_positions_count INTEGER DEFAULT 0,
    open_positions_usd NUMERIC(18,2) DEFAULT 0,
    exposure_pct NUMERIC(6,4),
    -- Trades
    trades_today INTEGER DEFAULT 0,
    wins_today INTEGER DEFAULT 0,
    losses_today INTEGER DEFAULT 0,
    -- Drawdown
    peak_bankroll_usd NUMERIC(18,2),
    drawdown_pct NUMERIC(6,4),
    -- Per strategi (JSONB for fleksibilitet)
    strategy_breakdown JSONB
);

-- =====================================================
-- NEWS_EVENTS: Nyheder der kan påvirke markeder
-- =====================================================
CREATE TABLE news_events (
    id BIGSERIAL PRIMARY KEY,
    source TEXT NOT NULL,                   -- "reuters", "twitter", "rss"
    headline TEXT NOT NULL,
    url TEXT,
    body TEXT,
    published_at TIMESTAMP WITH TIME ZONE NOT NULL,
    fetched_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    -- Klassifikation
    relevance_tags TEXT[],                  -- ["fed", "ecb", "us_election"]
    relevance_score NUMERIC(3,2),
    processed BOOLEAN DEFAULT FALSE
);

CREATE INDEX idx_news_published ON news_events (published_at DESC);
CREATE INDEX idx_news_tags ON news_events USING GIN (relevance_tags);
```

### 3.2 Database-init script

```python
# scripts/init_db.py
"""Initialiserer database med schema og første base rates."""
import asyncio
from pathlib import Path

from polymarket_quant.config import settings
from polymarket_quant.db.session import engine, Base
from polymarket_quant.db.models import *  # noqa: registrér alle models


async def init_db() -> None:
    """Opretter alle tabeller og kører initial seed."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("Database initialiseret.")


if __name__ == "__main__":
    asyncio.run(init_db())
```

---

## 4. API-integration: konkrete eksempler

### 4.1 Gamma API wrapper (markedsdata)

```python
# src/polymarket_quant/clients/gamma.py
"""Wrapper for Polymarket Gamma API (read-only markedsdata)."""
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

import httpx
import structlog

logger = structlog.get_logger()

GAMMA_BASE_URL = "https://gamma-api.polymarket.com"


class GammaClient:
    """Async wrapper for Polymarket Gamma API.

    Rate limit: cirka 60 req/min uden auth. Vi holder os godt under.
    """

    def __init__(self, timeout: float = 30.0) -> None:
        self._client = httpx.AsyncClient(
            base_url=GAMMA_BASE_URL,
            timeout=timeout,
            headers={"User-Agent": "polymarket-quant/0.1"},
        )
        # Simpel intern rate-limit: max 30 req/min for at have margin
        self._semaphore = asyncio.Semaphore(5)
        self._last_request_at: float = 0.0
        self._min_interval = 2.0  # sekunder mellem requests

    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> GammaClient:
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()

    async def _get(self, path: str, params: dict | None = None) -> Any:
        """Internal: rate-limited GET."""
        async with self._semaphore:
            # Simpel rate limiting
            now = asyncio.get_event_loop().time()
            elapsed = now - self._last_request_at
            if elapsed < self._min_interval:
                await asyncio.sleep(self._min_interval - elapsed)

            try:
                response = await self._client.get(path, params=params)
                response.raise_for_status()
                self._last_request_at = asyncio.get_event_loop().time()
                return response.json()
            except httpx.HTTPStatusError as e:
                logger.error(
                    "gamma_api_error",
                    path=path,
                    status=e.response.status_code,
                    body=e.response.text[:200],
                )
                raise

    async def list_markets(
        self,
        active: bool = True,
        closed: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict]:
        """Henter liste af markeder med pagination.

        Vigtige felter i response:
            - conditionId: unique market ID
            - question: market spørgsmål
            - clobTokenIds: [yes_token, no_token]
            - outcomePrices: aktuelle priser
            - volume24hr, liquidity: handelsstatistik
            - endDate: resolution-dato
            - minimumTickSize, negRisk: trading-detaljer
        """
        params = {
            "active": str(active).lower(),
            "closed": str(closed).lower(),
            "limit": limit,
            "offset": offset,
        }
        data = await self._get("/markets", params=params)
        return data if isinstance(data, list) else data.get("data", [])

    async def get_market(self, condition_id: str) -> dict:
        """Henter detaljer for ét specifikt marked."""
        return await self._get(f"/markets/{condition_id}")

    async def list_all_active_markets(self) -> list[dict]:
        """Henter ALLE aktive markeder via pagination."""
        all_markets: list[dict] = []
        offset = 0
        page_size = 100

        while True:
            batch = await self.list_markets(
                active=True, closed=False, limit=page_size, offset=offset
            )
            if not batch:
                break
            all_markets.extend(batch)
            if len(batch) < page_size:
                break
            offset += page_size

        logger.info("fetched_active_markets", count=len(all_markets))
        return all_markets

    async def list_events(self, active: bool = True, limit: int = 50) -> list[dict]:
        """Henter events (grupper af relaterede markeder)."""
        params = {
            "active": str(active).lower(),
            "limit": limit,
        }
        data = await self._get("/events", params=params)
        return data if isinstance(data, list) else data.get("data", [])
```

### 4.2 CLOB API wrapper (orderbook + execution)

```python
# src/polymarket_quant/clients/clob.py
"""Wrapper for Polymarket CLOB API.

Bruges til orderbook-depth (read-only) og execution (fase 2+).
"""
from __future__ import annotations

from typing import Any

import structlog
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import BookParams

from polymarket_quant.config import settings

logger = structlog.get_logger()

CLOB_HOST = "https://clob.polymarket.com"
POLYGON_CHAIN_ID = 137


def get_readonly_client() -> ClobClient:
    """Read-only client til orderbook-data, ingen wallet krævet."""
    return ClobClient(host=CLOB_HOST)


def get_authenticated_client() -> ClobClient:
    """Fuldt autentificeret client til trading.

    Krav: PRIVATE_KEY og FUNDER_ADDRESS i .env.
    """
    if not settings.polymarket_private_key:
        raise ValueError("POLYMARKET_PRIVATE_KEY ikke sat - kan ikke autentificere")

    client = ClobClient(
        host=CLOB_HOST,
        key=settings.polymarket_private_key,
        chain_id=POLYGON_CHAIN_ID,
        signature_type=settings.polymarket_signature_type,
        funder=settings.polymarket_funder_address,
    )
    # Derive og sæt API credentials (L1 → L2)
    client.set_api_creds(client.create_or_derive_api_creds())
    return client


def get_orderbook_snapshot(token_id: str) -> dict[str, Any]:
    """Snapshot af orderbook for én token.

    Returns:
        {
            'midpoint': float,
            'best_bid': float,
            'best_ask': float,
            'spread': float,
            'bids': [{'price': float, 'size': float}, ...],
            'asks': [...],
            'depth_5pct_bid_usd': float,
            'depth_5pct_ask_usd': float,
        }
    """
    client = get_readonly_client()
    book = client.get_order_book(token_id)
    midpoint = float(client.get_midpoint(token_id).get("mid", 0))

    bids = [{"price": float(b.price), "size": float(b.size)} for b in book.bids]
    asks = [{"price": float(a.price), "size": float(a.size)} for a in book.asks]

    best_bid = max((b["price"] for b in bids), default=0.0)
    best_ask = min((a["price"] for a in asks), default=1.0)
    spread = best_ask - best_bid

    # Likviditet inden for 5% af mid
    bid_threshold = midpoint * 0.95
    ask_threshold = midpoint * 1.05
    depth_5pct_bid = sum(
        b["price"] * b["size"] for b in bids if b["price"] >= bid_threshold
    )
    depth_5pct_ask = sum(
        a["price"] * a["size"] for a in asks if a["price"] <= ask_threshold
    )

    return {
        "midpoint": midpoint,
        "best_bid": best_bid,
        "best_ask": best_ask,
        "spread": spread,
        "bids": bids[:20],  # gem kun top 20 niveauer
        "asks": asks[:20],
        "depth_5pct_bid_usd": depth_5pct_bid,
        "depth_5pct_ask_usd": depth_5pct_ask,
    }


def get_account_positions() -> list[dict]:
    """Henter brugerens åbne positioner på Polymarket.

    Bruges til reconciliation: matcher vores DB med Polymarkets eget view.
    """
    client = get_authenticated_client()
    # Bemærk: get_positions() returnerer fra Data API, ikke CLOB direkte
    # Verificér aktuel SDK-metode før brug
    return client.get_positions()
```

> **Vigtig advarsel:** Den autentificerede client kører real trades på real money. Sæt `ENVIRONMENT=development` i `.env` og lad execution-modulet refuse at trade hvis ikke `ENVIRONMENT=production`. Tilføj eksplicit safety-gates før hver execution-funktion.

### 4.3 Market discovery job

```python
# src/polymarket_quant/ingestion/market_discovery.py
"""Periodic job: opdager nye markeder og opdaterer metadata."""
from __future__ import annotations

from datetime import datetime, timezone

import structlog
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from polymarket_quant.clients.gamma import GammaClient
from polymarket_quant.db.models import Market
from polymarket_quant.db.session import AsyncSessionLocal

logger = structlog.get_logger()


def classify_vertical(market: dict) -> str:
    """Klassificér marked til vertikal for strategi-routing.

    Heuristik baseret på category, question-tekst, og keywords.
    Kan udbygges med LLM-klassifikation senere.
    """
    question = (market.get("question") or "").lower()
    category = (market.get("category") or "").lower()

    macro_keywords = ["fed", "fomc", "ecb", "interest rate", "inflation", "cpi", "gdp", "unemployment"]
    eu_keywords = ["eu ", "european", "germany", "france", "denmark", "uk election", "brexit"]
    us_pol_keywords = ["trump", "biden", "harris", "congress", "senate", "house of rep"]
    sports_keywords = ["nfl", "nba", "soccer", "world cup", "champions league", "premier league"]
    crypto_keywords = ["bitcoin", "btc", "ethereum", "eth", "solana", "crypto"]

    if any(k in question for k in macro_keywords):
        return "macro"
    if any(k in question for k in eu_keywords):
        return "eu_politics"
    if any(k in question for k in us_pol_keywords):
        return "us_politics"
    if any(k in question for k in sports_keywords) or "sports" in category:
        return "sports"
    if any(k in question for k in crypto_keywords) or "crypto" in category:
        return "crypto"
    return "other"


async def discover_markets() -> int:
    """Henter alle aktive markeder, upserter i database.

    Returns:
        Antal markeder behandlet.
    """
    count = 0
    async with GammaClient() as gamma:
        markets = await gamma.list_all_active_markets()

        async with AsyncSessionLocal() as session:
            for m in markets:
                try:
                    clob_tokens = m.get("clobTokenIds") or []
                    if isinstance(clob_tokens, str):
                        # Sometimes returned as JSON string
                        import json
                        clob_tokens = json.loads(clob_tokens)

                    if len(clob_tokens) < 2:
                        continue

                    end_date_str = m.get("endDate")
                    end_date = (
                        datetime.fromisoformat(end_date_str.replace("Z", "+00:00"))
                        if end_date_str else None
                    )

                    vertical = classify_vertical(m)

                    stmt = insert(Market).values(
                        condition_id=m["conditionId"],
                        question=m["question"],
                        description=m.get("description"),
                        slug=m.get("slug"),
                        category=m.get("category"),
                        event_id=m.get("eventId"),
                        yes_token_id=clob_tokens[0],
                        no_token_id=clob_tokens[1],
                        end_date=end_date,
                        minimum_tick_size=m.get("minimumTickSize"),
                        neg_risk=m.get("negRisk", False),
                        is_active=m.get("active", True),
                        is_closed=m.get("closed", False),
                        primary_vertical=vertical,
                        raw_metadata=m,
                        updated_at=datetime.now(timezone.utc),
                    )
                    # Upsert på condition_id
                    stmt = stmt.on_conflict_do_update(
                        index_elements=["condition_id"],
                        set_={
                            "question": stmt.excluded.question,
                            "is_active": stmt.excluded.is_active,
                            "is_closed": stmt.excluded.is_closed,
                            "primary_vertical": stmt.excluded.primary_vertical,
                            "raw_metadata": stmt.excluded.raw_metadata,
                            "updated_at": stmt.excluded.updated_at,
                        },
                    )
                    await session.execute(stmt)
                    count += 1
                except Exception as e:
                    logger.warning("market_discovery_skip", market=m.get("conditionId"), error=str(e))

            await session.commit()

    logger.info("market_discovery_complete", processed=count)
    return count
```

### 4.4 Price snapshot job

```python
# src/polymarket_quant/ingestion/price_snapshot.py
"""Tager periodiske snapshots af priser og volume."""
from __future__ import annotations

from datetime import datetime, timezone

import structlog
from sqlalchemy import select

from polymarket_quant.clients.gamma import GammaClient
from polymarket_quant.db.models import Market, MarketSnapshot
from polymarket_quant.db.session import AsyncSessionLocal

logger = structlog.get_logger()


async def snapshot_all_active_markets() -> int:
    """Snapshot af alle aktive markeder.

    Køres hver 5-15 min via scheduler.
    """
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Market).where(Market.is_active, ~Market.is_closed)
        )
        active_markets = result.scalars().all()

        if not active_markets:
            return 0

        snapshot_time = datetime.now(timezone.utc)
        count = 0

        async with GammaClient() as gamma:
            for market in active_markets:
                try:
                    # Henter friske data fra Gamma
                    data = await gamma.get_market(market.condition_id)

                    outcome_prices = data.get("outcomePrices") or []
                    if isinstance(outcome_prices, str):
                        import json
                        outcome_prices = json.loads(outcome_prices)

                    if len(outcome_prices) < 2:
                        continue

                    yes_price = float(outcome_prices[0])
                    no_price = float(outcome_prices[1])

                    snapshot = MarketSnapshot(
                        market_id=market.id,
                        snapshot_at=snapshot_time,
                        yes_price=yes_price,
                        no_price=no_price,
                        volume_24h=float(data.get("volume24hr") or 0),
                        volume_total=float(data.get("volume") or 0),
                        liquidity_usd=float(data.get("liquidity") or 0),
                    )
                    session.add(snapshot)
                    count += 1
                except Exception as e:
                    logger.warning(
                        "snapshot_skip",
                        market=market.condition_id,
                        error=str(e),
                    )

            await session.commit()

    logger.info("snapshot_complete", count=count)
    return count
```

### 4.5 Scheduler-konfiguration

```python
# src/polymarket_quant/scheduler.py
"""APScheduler setup. Køres som langtkørende proces."""
from __future__ import annotations

import asyncio

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from polymarket_quant.ingestion.market_discovery import discover_markets
from polymarket_quant.ingestion.price_snapshot import snapshot_all_active_markets

logger = structlog.get_logger()


def setup_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="UTC")

    # Market discovery: hver time
    scheduler.add_job(
        discover_markets,
        trigger=IntervalTrigger(hours=1),
        id="market_discovery",
        name="Discover new and updated markets",
        max_instances=1,
        coalesce=True,
    )

    # Price snapshot: hver 10 min
    scheduler.add_job(
        snapshot_all_active_markets,
        trigger=IntervalTrigger(minutes=10),
        id="price_snapshot",
        name="Snapshot prices of active markets",
        max_instances=1,
        coalesce=True,
    )

    # Daglig performance-beregning kl 23:30 UTC
    # scheduler.add_job(
    #     calculate_daily_performance,
    #     trigger=CronTrigger(hour=23, minute=30),
    #     id="daily_performance",
    # )

    return scheduler


async def main() -> None:
    scheduler = setup_scheduler()
    scheduler.start()
    logger.info("scheduler_started")
    try:
        while True:
            await asyncio.sleep(3600)
    except KeyboardInterrupt:
        scheduler.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
```

---

## 5. Strategi-implementering (base klasse)

```python
# src/polymarket_quant/strategies/base.py
"""Base class for trading strategier.

Hver strategi implementerer:
    - scan_for_signals(): finder nye signaler i aktive markeder
    - validate_signal(): konkretiserer og filtrerer signal
    - generate_exit_criteria(): definerer exit-betingelser
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass
class Signal:
    market_id: int
    condition_id: str
    strategy: str
    side: str  # "BUY_YES" | "BUY_NO"
    market_price: float
    fair_value_estimate: float
    edge_pct: float
    confidence: float  # 0.0-1.0
    suggested_size_usd: float
    exit_price_target: float | None
    exit_date_target: datetime | None
    exit_conditions: dict[str, Any]
    metadata: dict[str, Any]


class Strategy(ABC):
    """Abstract base for alle strategier."""

    name: str

    @abstractmethod
    async def scan_for_signals(self) -> list[Signal]:
        """Scan database for markeder der matcher strategiens kriterier.

        Returns: liste af potentielle signaler (før risk-filtre).
        """
        ...

    def passes_minimum_edge(self, signal: Signal, min_edge_pct: float = 0.03) -> bool:
        """Filtrér signaler med edge under threshold (efter friktion)."""
        return signal.edge_pct >= min_edge_pct
```

Eksempel implementering af strategi A (base rate fade) skitseres her som template:

```python
# src/polymarket_quant/strategies/base_rate_fade.py
"""Strategi A: Base rate fade.

Hypotese: Polymarket overreagerer på nylige nyheder. Markeder der bevæger sig
mere end 15 procentpoint fra etableret base rate har edge mod mean reversion.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from polymarket_quant.db.models import BaseRate, Market, MarketSnapshot
from polymarket_quant.db.session import AsyncSessionLocal
from polymarket_quant.strategies.base import Signal, Strategy


class BaseRateFadeStrategy(Strategy):
    name = "base_rate_fade"

    # Parametre (tunes via backtesting)
    MIN_DEVIATION_PCT = 0.15  # marked skal være >15pp fra base rate
    MIN_SAMPLE_SIZE = 10      # base rate skal have minimum 10 historiske obs
    MAX_HORIZON_DAYS = 30     # ignorér markeder længere end 30 dage ude
    MIN_LIQUIDITY_USD = 5000  # mindst 5k USD likviditet

    async def scan_for_signals(self) -> list[Signal]:
        signals: list[Signal] = []

        async with AsyncSessionLocal() as session:
            # Find aktive markeder med base rates
            now = datetime.now(timezone.utc)
            max_end = now + timedelta(days=self.MAX_HORIZON_DAYS)

            query = (
                select(Market)
                .where(
                    Market.is_active,
                    ~Market.is_closed,
                    Market.has_base_rate,
                    Market.end_date <= max_end,
                    Market.end_date > now,
                )
            )
            markets = (await session.execute(query)).scalars().all()

            for market in markets:
                # Hent seneste snapshot
                snap_query = (
                    select(MarketSnapshot)
                    .where(MarketSnapshot.market_id == market.id)
                    .order_by(MarketSnapshot.snapshot_at.desc())
                    .limit(1)
                )
                latest_snap = (await session.execute(snap_query)).scalar_one_or_none()
                if not latest_snap or latest_snap.liquidity_usd < self.MIN_LIQUIDITY_USD:
                    continue

                # Match til base rate (her: simpel category-lookup)
                # I produktion: smartere matching via metadata
                base_rate = await self._lookup_base_rate(session, market)
                if not base_rate or base_rate.sample_size < self.MIN_SAMPLE_SIZE:
                    continue

                yes_price = float(latest_snap.yes_price)
                br = float(base_rate.base_probability)

                # Hvis market >> base rate, fade ved at købe NO
                if yes_price - br > self.MIN_DEVIATION_PCT:
                    signal = Signal(
                        market_id=market.id,
                        condition_id=market.condition_id,
                        strategy=self.name,
                        side="BUY_NO",
                        market_price=1.0 - yes_price,  # no_price
                        fair_value_estimate=1.0 - br,
                        edge_pct=(yes_price - br),
                        confidence=0.6,
                        suggested_size_usd=0.0,  # sættes af risk-engine
                        exit_price_target=1.0 - (br + 0.05),
                        exit_date_target=market.end_date,
                        exit_conditions={
                            "reason": "convergence_to_base_rate",
                            "target_yes": br + 0.05,
                        },
                        metadata={
                            "base_rate_id": base_rate.id,
                            "base_rate": br,
                            "deviation": yes_price - br,
                        },
                    )
                    if self.passes_minimum_edge(signal):
                        signals.append(signal)

                # Hvis market << base rate, fade ved at købe YES
                elif br - yes_price > self.MIN_DEVIATION_PCT:
                    signal = Signal(
                        market_id=market.id,
                        condition_id=market.condition_id,
                        strategy=self.name,
                        side="BUY_YES",
                        market_price=yes_price,
                        fair_value_estimate=br,
                        edge_pct=(br - yes_price),
                        confidence=0.6,
                        suggested_size_usd=0.0,
                        exit_price_target=br - 0.05,
                        exit_date_target=market.end_date,
                        exit_conditions={
                            "reason": "convergence_to_base_rate",
                            "target_yes": br - 0.05,
                        },
                        metadata={
                            "base_rate_id": base_rate.id,
                            "base_rate": br,
                            "deviation": br - yes_price,
                        },
                    )
                    if self.passes_minimum_edge(signal):
                        signals.append(signal)

        return signals

    async def _lookup_base_rate(self, session, market: Market) -> BaseRate | None:
        # Simpel lookup baseret på category. Forfin senere.
        if not market.category:
            return None
        result = await session.execute(
            select(BaseRate).where(BaseRate.category == market.category).limit(1)
        )
        return result.scalar_one_or_none()
```

---

## 6. Risk og sizing engine

```python
# src/polymarket_quant/risk/sizing.py
"""Position sizing med modificeret Kelly + hard caps."""
from __future__ import annotations

from polymarket_quant.config import settings
from polymarket_quant.strategies.base import Signal


KELLY_FRACTION = 0.25       # Kvart-Kelly
MAX_POSITION_PCT = 0.05     # Maks 5% af bankroll
MIN_POSITION_USD = 10.0     # Under dette er friktion for stor


def calculate_kelly_size(
    signal: Signal,
    bankroll_usd: float,
) -> tuple[float, dict]:
    """Beregner anbefalet position size.

    Modificeret Kelly:
        f* = (b*p - q) / b
        anvendt = min(KELLY_FRACTION * f*, MAX_POSITION_PCT)

    Args:
        signal: Strategi-genereret signal
        bankroll_usd: Aktuel bankroll

    Returns:
        (size_usd, debug_dict)
    """
    market_price = signal.market_price  # pris vi køber til (0-1)
    if market_price <= 0 or market_price >= 1:
        return 0.0, {"reason": "invalid_price"}

    # b = nettoodds = (1 - p_mkt) / p_mkt
    b = (1.0 - market_price) / market_price
    p = signal.fair_value_estimate / (
        market_price + (1 - market_price) * signal.fair_value_estimate / (1 - signal.fair_value_estimate)
        if signal.side == "BUY_YES"
        else signal.fair_value_estimate
    )
    # Simplere: brug confidence-justeret estimat direkte
    p = signal.fair_value_estimate if signal.side == "BUY_YES" else (1 - signal.fair_value_estimate)
    q = 1.0 - p

    full_kelly = (b * p - q) / b
    if full_kelly <= 0:
        return 0.0, {"reason": "negative_edge_after_kelly", "kelly": full_kelly}

    fraction = min(KELLY_FRACTION * full_kelly, MAX_POSITION_PCT)
    size_usd = round(bankroll_usd * fraction, 2)

    if size_usd < MIN_POSITION_USD:
        return 0.0, {"reason": "below_min_size", "would_size": size_usd}

    return size_usd, {
        "full_kelly": round(full_kelly, 4),
        "applied_fraction": round(fraction, 4),
        "size_usd": size_usd,
    }


def apply_liquidity_constraint(
    size_usd: float,
    available_liquidity_usd: float,
    max_price_impact_pct: float = 0.01,
) -> float:
    """Begræns position så vi ikke flytter prisen mere end max_price_impact_pct.

    Tommelfingerregel: maks 30-50% af inside depth.
    """
    max_safe = available_liquidity_usd * 0.4
    return min(size_usd, max_safe)
```

```python
# src/polymarket_quant/risk/portfolio.py
"""Portefølje-niveau risk-tjek: korrelation og samlet eksponering."""
from __future__ import annotations

from sqlalchemy import func, select

from polymarket_quant.db.models import Position
from polymarket_quant.db.session import AsyncSessionLocal


MAX_TOTAL_EXPOSURE_PCT = 0.60       # Maks 60% allokeret samtidigt
MAX_CORRELATED_EXPOSURE_PCT = 0.30  # Maks 30% mod én korreleret begivenhed


async def get_current_exposure(bankroll_usd: float) -> dict:
    """Beregner aktuel portefølje-eksponering."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(func.coalesce(func.sum(Position.entry_size_usd), 0))
            .where(Position.status == "OPEN")
        )
        open_exposure = float(result.scalar() or 0)

    return {
        "open_exposure_usd": open_exposure,
        "open_exposure_pct": open_exposure / bankroll_usd if bankroll_usd > 0 else 0,
        "available_usd": max(0, bankroll_usd * MAX_TOTAL_EXPOSURE_PCT - open_exposure),
    }


async def can_open_new_position(
    proposed_size_usd: float,
    correlation_group: str | None,
    bankroll_usd: float,
) -> tuple[bool, str]:
    """Tjekker om vi må åbne ny position givet eksisterende eksponering.

    Returns: (allowed, reason)
    """
    exposure = await get_current_exposure(bankroll_usd)
    if exposure["open_exposure_usd"] + proposed_size_usd > bankroll_usd * MAX_TOTAL_EXPOSURE_PCT:
        return False, "total_exposure_cap"

    if correlation_group:
        # TODO: tjek mod eksisterende positioner i samme correlation_group
        pass

    return True, "ok"
```

---

## 7. Uge-for-uge implementeringsplan (første 12 uger)

Detaljeret breakdown af de 12 uger fra `STRATEGY.md`.

### Uge 1: Setup og foundation

**Mål:** Tomt projekt klar med database, config og en første GET mod Gamma API.

| Dag | Opgave | Deliverable |
|-----|--------|-------------|
| 1 | Initialisér Cursor-projekt, `uv init`, opsæt `pyproject.toml` | Projekt boot'er |
| 2 | Docker compose med PostgreSQL + TimescaleDB. Implementér `config.py` | `docker-compose up` virker |
| 3 | SQLAlchemy models + Alembic migrations | DB schema deployet |
| 4 | Telegram bot setup + test af notification | Modtag test-besked |
| 5 | Skriv `GammaClient` (read-only) og test `list_markets()` | Liste af aktive markeder printer |

### Uge 2: Data-pipeline live

**Mål:** Markedsdata strømmer ind i database hver 10 minutter.

| Dag | Opgave | Deliverable |
|-----|--------|-------------|
| 1 | Implementér `discover_markets()` med upsert-logik | Markets-tabel fyldes |
| 2 | Implementér `snapshot_all_active_markets()` | Snapshots-tabel fyldes |
| 3 | Setup APScheduler, kør lokalt | Jobs kører ifølge skema |
| 4 | Tilføj structlog + JSON-logging | Logs er strukturerede |
| 5 | Deploy til Railway/Fly.io | Pipeline kører 24/7 |

### Uge 3: Manuel research (parallel med uge 4)

**Mål:** Egen erfaring med Polymarket-mekanik via hands-on trading.

| Dag | Opgave |
|-----|--------|
| 1-2 | Setup wallet, deposit 200-500 USD, lav 3-5 små handler |
| 3-4 | Mærk friktion: spread, slippage, gas, resolution-tid |
| 5 | Skriv noter i `JOURNAL.md` om markedsdynamik |

### Uge 4: Første base rates

**Mål:** Database af base rates for makro-events.

| Dag | Opgave | Deliverable |
|-----|--------|-------------|
| 1 | Identificér 10-15 base rate-kategorier (Fed-beslutninger, ECB, GDP, CPI, etc.) | Liste i `JOURNAL.md` |
| 2-3 | Manual indtastning via SQL eller script. Brug FRED til historiske data | `base_rates` tabel fyldt |
| 4 | Skriv `classifier.py`: matcher markets til base rates via keywords | Auto-mapping virker |
| 5 | Sæt `has_base_rate=true` på relevante markets | Strategi A kan finde candidates |

### Uge 5-6: Strategi A implementeret

**Mål:** Base rate fade strategi genererer signaler dagligt.

| Uge 5 |  |
|-------|---|
| Mandag | Implementér `Strategy` base class + Signal-dataclass |
| Tirsdag | Implementér `BaseRateFadeStrategy.scan_for_signals()` |
| Onsdag | Implementér risk-engine (`sizing.py`, `portfolio.py`) |
| Torsdag | Signal-persistens til database |
| Fredag | Telegram-notification ved nyt signal |

| Uge 6 |  |
|-------|---|
| Mandag | Tilføj scheduler-job: scan hver time |
| Tirsdag | Implementér decision-journal pre-trade flow |
| Onsdag | Manuelt review af første 10 signaler genereret |
| Torsdag | Tuning af thresholds baseret på review |
| Fredag | Dokumentér første strategi i `JOURNAL.md` |

### Uge 7-8: Backtesting + strategi B

| Uge 7 |  |
|-------|---|
| Mandag-Tirsdag | Backtest-engine: walk-forward, friktion-modellering |
| Onsdag | Backtest strategi A mod 2024-2025 data |
| Torsdag | Analyse: hit rate, edge realiseret, drawdown |
| Fredag | Beslut: går strategi A videre eller skal kalibreres? |

| Uge 8 |  |
|-------|---|
| Mandag-Onsdag | Implementér `StalePriceStrategy` (likviditet-screen) |
| Torsdag | News-feed setup (RSS-aggregator) |
| Fredag | Backtest strategi B (begrænset af manglende historiske news) |

### Uge 9-10: Dashboard + risk-system formaliseret

| Uge 9 |  |
|-------|---|
| Mandag-Tirsdag | Streamlit dashboard: side 1 (signaler), side 2 (positioner) |
| Onsdag | Side 3 (journal), side 4 (performance) |
| Torsdag | Drawdown-monitoring: alert ved 10/15/20% |
| Fredag | E2E test af workflow: signal → journal → position → exit |

| Uge 10 |  |
|--------|---|
| Mandag-Onsdag | Implementér `CrossMarketStrategy` (arbitrage) |
| Torsdag-Fredag | Implementér `VolatilityCrushStrategy` |

### Uge 11-12: Paper trading launch

| Uge 11 |  |
|--------|---|
| Mandag | Alle 4 strategier kører signal-generation |
| Tirsdag-Fredag | Manuel review af alle signaler i 5 dage, kalibrér |

| Uge 12 |  |
|--------|---|
| Mandag | Start formel paper trading: log alle "ville være eksekveret" |
| Tirsdag-Fredag | Daglig journal-disciplin, ingen real trades endnu |

Efter uge 12: 12 ugers paper trading før beslutning om live capital allocation. Total 6 måneder fra start til første live trade.

---

## 8. Operationelle og sikkerhedsmæssige overvejelser

### 8.1 Secrets management

| Type | Lokal udvikling | Production |
|------|-----------------|------------|
| Wallet private key | `.env` (i `.gitignore`) | Railway/Fly secrets |
| API keys | `.env` | Platform secrets |
| Database password | `.env` | Platform secrets |
| Telegram tokens | `.env` | Platform secrets |

Aldrig commit `.env` (står i `.gitignore`).

### 8.2 Sikkerhed omkring trading

Tre safety-gates skal være på plads før første live trade:

1. **Environment-flag:** `auto.py` refuser at trade hvis `ENVIRONMENT != "production"`.
2. **Max position cap i kode:** Hard-coded ceiling på 100 USD per trade for første live måned, hævet manuelt herefter.
3. **Telegram confirmation:** Auto-execution kræver Telegram-godkendelse for første 50 trades (manuelt OK via bot).

### 8.3 Monitorering

| Metrik | Threshold | Action |
|--------|-----------|--------|
| Pipeline lag | >15 min siden sidste snapshot | Telegram alert |
| DB connection fejl | Hvis ja | Telegram alert + log |
| API rate limit hit | >5x/dag | Reducér polling frekvens |
| Realized drawdown | >10% | Telegram alert |
| Realized drawdown | >15% | Reducér sizing 50% (kode-enforced) |
| Realized drawdown | >20% | Stop nye positioner (kode-enforced) |

### 8.4 Backup

Database backup dagligt via Railway/Fly built-in snapshots.

Journal og strategi-noter er Git-tracket i samme repo som koden.

Eksport af alle trades til CSV ugentligt, gemt separat (Google Drive eller lignende), så performance-track ikke afhænger af Polymarket-platformen.

---

## 9. Test og kvalitetssikring

### 9.1 Test-pyramide

```
        /\
       /  \  E2E (få, dyre): hele signal-workflow
      /----\
     /      \  Integration: DB + API mocks
    /--------\
   /          \  Unit: strategi-logik, sizing, klassifikation
  /____________\
```

### 9.2 Vigtige unit tests

```python
# tests/test_risk.py eksempler

def test_kelly_sizing_zero_when_no_edge():
    """Hvis fair value = market price, size = 0."""
    signal = Signal(..., market_price=0.5, fair_value_estimate=0.5, ...)
    size, _ = calculate_kelly_size(signal, bankroll_usd=10000)
    assert size == 0

def test_kelly_sizing_respects_max_cap():
    """Selv ved enorm edge, max 5% af bankroll."""
    signal = Signal(..., market_price=0.1, fair_value_estimate=0.9, ...)
    size, _ = calculate_kelly_size(signal, bankroll_usd=10000)
    assert size <= 500  # 5% cap

def test_liquidity_constraint():
    """Position må ikke overstige 40% af tilgængelig likviditet."""
    constrained = apply_liquidity_constraint(
        size_usd=1000,
        available_liquidity_usd=1000,
    )
    assert constrained == 400
```

### 9.3 Integration tests

Mock Gamma API responses og verificér at:
- Market discovery håndterer pagination korrekt
- Snapshots gemmes med korrekt timestamp
- Resolved markeder flagges korrekt

---

## 10. Kendte risici og workarounds

| Risiko | Mitigation |
|--------|------------|
| py-clob-client v1 har kendte bugs (FOK på thin markets, balance-fejl) | Følg GitHub issues, overvej v2 når stabil |
| Ingen sandbox = første tests koster real money | Start med 10-50 USD positioner |
| Gamma API priser kan lagge orderbook med sekunder | Brug CLOB orderbook for execution-priser |
| Resolution-disputes via UMA kan tage uger | Allokér ikke over 10% mod én resolution-dato |
| Rate limit overskridelse → 429 | Eksponentiel backoff, reducér polling frekvens |
| Polymarket adgang fra DK kan ændres regulatorisk | Monitorer løbende, hav exit-plan for at trække USDC |
| WebSocket silent freezes (kendt bug #292) | Heartbeat-monitoring, reconnect efter 60s stilhed |

---

## 11. Næste skridt

### Denne uge

1. Setup Cursor-projekt med struktur fra sektion 2
2. Initialisér Git-repo, commit både `STRATEGY.md` og dette dokument
3. Opret/rediger lokal `.env`
4. Docker compose op med PostgreSQL + TimescaleDB
5. Første successful kald mod Gamma API: hent 10 markeder, print dem

### Inden uge 2

6. Setup Telegram bot og test notification
7. Deploy database og scheduler til Railway/Fly.io
8. Verificér adgang til Polymarket fra Danmark (KYC-status, eventuel VPN-behov)
9. Konsultér revisor om dansk skattebehandling af Polymarket-gevinster
10. Læs UMA Optimistic Oracle dokumentation grundigt

### Beslutninger der venter

Hvilken wallet-type bruges? Anbefaler dedicated MetaMask eller Magic-wallet med signature_type matching.

Hvilken niche-vertikal går først live? Forslag: makro-events først fordi base rates er klarest. EU-politik som anden vertikal efter 2 måneder.

Skal performance være offentlig eller privat? Offentlig giver accountability men også press. Privat er mere komfortabel men giver mindre disciplin.

---

## Appendix A: Nyttige links

- Polymarket docs: https://docs.polymarket.com
- Gamma API base: https://gamma-api.polymarket.com
- CLOB API base: https://clob.polymarket.com
- py-clob-client: https://github.com/Polymarket/py-clob-client
- py-clob-client v2 (early): https://github.com/Polymarket/py-clob-client-v2
- UMA Optimistic Oracle: https://docs.uma.xyz
- FRED API: https://fred.stlouisfed.org/docs/api
- ECB Statistical Data Warehouse: https://sdw-wsrest.ecb.europa.eu/help
- Polygon RPC: https://polygon-rpc.com (eller Chainstack/Alchemy for stabilitet)

## Appendix B: Cursor-prompts du kan starte med

Når du sidder i Cursor og vil have hjælp til specifikke filer, brug disse prompts som starting points:

> "Læs STRATEGY.md og IMPLEMENTATION.md. Vi er på uge 1 dag 5. Hjælp mig implementere GammaClient i src/polymarket_quant/clients/gamma.py baseret på sektion 4.1, og skriv en test der verificerer at list_markets() returnerer mindst 10 markeder."

> "Vi har discovery og snapshots kørende. Nu skal vi implementere BaseRateFadeStrategy. Læs sektion 5 i IMPLEMENTATION.md. Lav en konkret implementering, og forklar hvor du gør ting anderledes end skitsen."

> "Lav 5 enhedstests for risk/sizing.py der dækker edge cases: zero edge, negativ edge, ekstrem edge, lav likviditet, og position under MIN_POSITION_USD."
