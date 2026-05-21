# PSS Implementation: Strategi C
## Cross-market konsistens og arbitrage

**Version:** 2.0
**Dato:** Maj 2026
**Status:** Klar efter cleanup

> Dette dokument er det tekniske supplement til den nye STRATEGY.md. Det forudsætter at CLEANUP.md er gennemført.

---

## Bevarede komponenter fra eksisterende kode

Følgende moduler er strategi-agnostiske og bruges som de er, evt. med små justeringer:

| Modul | Status | Note |
|-------|--------|------|
| src/pss/db/ (markets, snapshots, positions) | Behold | Tilføj events + event_snapshots tabeller |
| src/pss/clients/gamma.py | Behold | Ingen ændringer nødvendige |
| src/pss/clients/clob.py | Behold | Skal udvides til execution senere |
| src/pss/ingestion/market_discovery.py | Behold | Tilføj event-mapping |
| src/pss/ingestion/price_snapshot.py | Behold | Ingen ændringer |
| src/pss/scheduler.py | Refactor | Fjern signal_scan, tilføj event-jobs |
| src/pss/notifications/telegram.py | Behold | Nye besked-templates for arbitrage |
| src/pss/logging_config.py | Behold | Uændret |
| src/pss/health_server.py | Behold | Uændret |
| src/pss/risk/sizing.py | Modificer | Multi-leg sizing-logik |
| src/pss/risk/portfolio.py | Behold | Kapital-cap er stadig relevant |
| src/pss/dashboard/ | Refactor | Tilpas til multi-leg visning |
| src/pss/performance/metrics.py | Behold | Uændret |
| src/pss/signals/persist.py | Behold med udvidelser | Multi-leg signal-struktur |
| src/pss/journal/ | Behold | Tilpas pre-trade tjekliste |
| src/pss/config.py | Behold | Tilføj C-specifikke parametre |

---

## Nye komponenter der skal bygges

### Fase 0: Cleanup (se CLEANUP.md)

### Fase 1: Empirisk research-pipeline

**Ny mappe:** `src/pss/events/`

```
src/pss/events/
  __init__.py
  discovery.py       # find aktive events med multi-leg struktur
  snapshot.py        # snapshot sum_yes_prices for hver event
  inconsistency.py   # detect og log inkonsistenser
  models.py          # event + event_snapshot ORM models
```

#### src/pss/events/discovery.py

```python
"""Discover Polymarket events med multi-leg struktur."""

from __future__ import annotations
from datetime import datetime, timezone

import structlog
from sqlalchemy.dialects.postgresql import insert

from pss.clients.gamma import GammaClient
from pss.db.models import Event, Market
from pss.db.session import AsyncSessionLocal

logger = structlog.get_logger()


async def discover_events() -> int:
    """Find aktive events med 3+ ben og populér events-tabellen.
    
    Et 'multi-leg event' er et Polymarket-event hvor flere markeder 
    er mutually exclusive (typisk markeret som neg_risk=True).
    
    Returns:
        Antal events behandlet.
    """
    count = 0
    async with GammaClient() as gamma:
        events = await gamma.list_events(active=True, limit=200)
        
        async with AsyncSessionLocal() as session:
            for event in events:
                event_markets = event.get("markets") or []
                
                # Krav: minimum 3 ben og neg_risk markeret
                if len(event_markets) < 3:
                    continue
                if not event.get("negRisk", False):
                    # Conservative: kun stol på neg_risk events for 
                    # ren mutually exclusive antagelse
                    continue
                
                end_date_str = event.get("endDate")
                end_date = (
                    datetime.fromisoformat(end_date_str.replace("Z", "+00:00"))
                    if end_date_str else None
                )
                
                stmt = insert(Event).values(
                    event_id=event["id"],
                    title=event["title"],
                    description=event.get("description"),
                    slug=event.get("slug"),
                    end_date=end_date,
                    is_active=event.get("active", True),
                    is_resolved=event.get("closed", False),
                    neg_risk=True,
                    raw_metadata=event,
                ).on_conflict_do_update(
                    index_elements=["event_id"],
                    set_={
                        "title": stmt.excluded.title,
                        "is_active": stmt.excluded.is_active,
                        "raw_metadata": stmt.excluded.raw_metadata,
                        "updated_at": datetime.now(timezone.utc),
                    },
                )
                await session.execute(stmt)
                count += 1
            
            await session.commit()
    
    logger.info("event_discovery_complete", processed=count)
    return count
```

#### src/pss/events/snapshot.py

```python
"""Snapshot af inkonsistens-data per event."""

from __future__ import annotations
from datetime import datetime, timezone

import structlog
from sqlalchemy import select

from pss.clients.clob import get_orderbook_snapshot
from pss.db.models import Event, EventSnapshot, Market, MarketSnapshot
from pss.db.session import AsyncSessionLocal

logger = structlog.get_logger()


async def snapshot_events() -> int:
    """For hver aktiv event, beregn sum af YES-priser og likviditet.
    
    Køres efter price_snapshot, så vi har friske market snapshots 
    at trække fra.
    """
    snapshot_time = datetime.now(timezone.utc)
    count = 0
    
    async with AsyncSessionLocal() as session:
        events = (await session.execute(
            select(Event).where(Event.is_active, ~Event.is_resolved)
        )).scalars().all()
        
        for event in events:
            # Find alle markets der hører til event
            markets = (await session.execute(
                select(Market).where(Market.event_id == event.event_id)
            )).scalars().all()
            
            if len(markets) < 3:
                continue
            
            # Hent seneste snapshot for hvert market
            leg_details = []
            sum_yes = 0.0
            min_liquidity = float("inf")
            
            for market in markets:
                latest = await session.scalar(
                    select(MarketSnapshot)
                    .where(MarketSnapshot.market_id == market.id)
                    .order_by(MarketSnapshot.snapshot_at.desc())
                    .limit(1)
                )
                if not latest or latest.yes_price is None:
                    break  # incomplete data, skip event
                
                yes_p = float(latest.yes_price)
                liq = float(latest.liquidity_usd or 0)
                sum_yes += yes_p
                min_liquidity = min(min_liquidity, liq)
                leg_details.append({
                    "market_id": market.id,
                    "condition_id": market.condition_id,
                    "yes_price": yes_p,
                    "liquidity_usd": liq,
                    "best_bid": float(latest.yes_best_bid or 0),
                    "best_ask": float(latest.yes_best_ask or 1),
                })
            else:
                # All legs had data
                inconsistency_pp = abs(sum_yes - 1.0) * 100
                
                snapshot = EventSnapshot(
                    event_id=event.id,
                    snapshot_at=snapshot_time,
                    leg_count=len(markets),
                    sum_yes_prices=sum_yes,
                    inconsistency_pp=inconsistency_pp,
                    min_leg_liquidity_usd=min_liquidity,
                    leg_details=leg_details,
                )
                session.add(snapshot)
                count += 1
        
        await session.commit()
    
    logger.info("event_snapshot_complete", count=count)
    return count
```

#### src/pss/events/inconsistency.py

```python
"""Detect og alert på interessante inkonsistenser."""

from __future__ import annotations
from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import select

from pss.db.models import Event, EventSnapshot
from pss.db.session import AsyncSessionLocal
from pss.notifications.telegram import send_telegram

logger = structlog.get_logger()


# Tunes baseret på Fase 1 empirisk data
INTERESTING_INCONSISTENCY_PP = 3.0
MIN_LEG_LIQUIDITY_USD = 100.0


async def scan_for_inconsistencies() -> int:
    """Scan seneste event snapshots for interessante inkonsistenser.
    
    Sender Telegram alert (informational only, ikke trade-signal) 
    når inkonsistens overstiger threshold.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=15)
    alerts_sent = 0
    
    async with AsyncSessionLocal() as session:
        recent = (await session.execute(
            select(EventSnapshot, Event)
            .join(Event, EventSnapshot.event_id == Event.id)
            .where(
                EventSnapshot.snapshot_at >= cutoff,
                EventSnapshot.inconsistency_pp >= INTERESTING_INCONSISTENCY_PP,
                EventSnapshot.min_leg_liquidity_usd >= MIN_LEG_LIQUIDITY_USD,
            )
            .order_by(EventSnapshot.inconsistency_pp.desc())
            .limit(10)
        )).all()
        
        for snap, event in recent:
            await send_telegram(
                f"Inconsistency detected:\n"
                f"Event: {event.title}\n"
                f"Sum YES: {snap.sum_yes_prices:.4f}\n"
                f"Inconsistency: {snap.inconsistency_pp:.2f}pp\n"
                f"Min leg liquidity: ${snap.min_leg_liquidity_usd:.2f}\n"
                f"Note: Informational only, ikke trade-signal."
            )
            alerts_sent += 1
    
    return alerts_sent
```

### Fase 2: Trading-strategi (kun hvis Fase 1 validerer)

**Ny fil:** `src/pss/strategies/inconsistency_arbitrage.py`

Implementeres efter Fase 1-rapport. Skitse:

```python
"""Strategi C: Cross-market inkonsistens arbitrage."""

from __future__ import annotations
from dataclasses import dataclass

from pss.strategies.base import Strategy


@dataclass
class LegOrder:
    market_id: int
    condition_id: str
    side: str  # "BUY_YES" eller "BUY_NO"
    target_price: float  # ask hvis BUY_YES, 1-bid hvis BUY_NO
    size_usd: float


@dataclass
class ArbitrageSignal:
    event_id: int
    legs: list[LegOrder]
    sum_yes_prices: float
    inconsistency_pp: float
    expected_edge_pp: float  # efter friktion
    total_size_usd: float
    min_leg_liquidity_usd: float


class InconsistencyArbitrageStrategy(Strategy):
    name = "inconsistency_arbitrage"
    
    MIN_INCONSISTENCY_PP = 4.0  # tunes baseret på Fase 1
    MIN_LEG_LIQUIDITY_USD = 200.0
    FRICTION_BUFFER_PP = 2.0
    MAX_POSITION_PCT = 0.05  # 5% af bankroll per event
    
    async def scan_for_signals(self) -> list[ArbitrageSignal]:
        # 1. Find events med inkonsistens over threshold
        # 2. Hent live orderbook for hvert ben (ikke kun snapshot)
        # 3. Beregn executable inkonsistens på ask/bid-priser
        # 4. Hvis stadig over threshold efter friktion: byg signal
        # 5. Size baseret på min(min_leg_depth * 0.5, bankroll * 0.05)
        ...
```

### Fase 3: Eksekvering-koordinator

**Ny fil:** `src/pss/execution/multi_leg.py`

Implementeres efter Fase 2. Håndterer samtidig multi-leg eksekvering med rollback hvis partial fill.

### Fase 4: Backtesting til arbitrage

**Ny mappe:** `src/pss/backtesting/`

Bygges nyt, ikke genbrug af gammel base_rate_fade-backtester. Nye krav:
- Walk-forward over event_snapshots historik
- Simulér leg-eksekvering med spread og slippage
- Modellér partial fills og rollback-omkostning

---

## Database schema-ændringer

### Migration 1: Drop has_base_rate

```python
# alembic/versions/0002_drop_has_base_rate.py
def upgrade():
    op.drop_index("idx_markets_has_base_rate", table_name="markets")
    op.drop_column("markets", "has_base_rate")

def downgrade():
    op.add_column("markets", sa.Column("has_base_rate", sa.Boolean, default=False))
```

### Migration 2: Tilføj events og event_snapshots

```python
# alembic/versions/0003_add_events.py
def upgrade():
    op.create_table(
        "events",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("event_id", sa.Text, unique=True, nullable=False),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("slug", sa.Text),
        sa.Column("end_date", sa.DateTime(timezone=True)),
        sa.Column("is_active", sa.Boolean, default=True),
        sa.Column("is_resolved", sa.Boolean, default=False),
        sa.Column("neg_risk", sa.Boolean, default=False),
        sa.Column("raw_metadata", postgresql.JSONB),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_events_active", "events", ["is_active"])
    op.create_index("idx_events_end_date", "events", ["end_date"])
    
    op.create_table(
        "event_snapshots",
        sa.Column("event_id", sa.BigInteger, sa.ForeignKey("events.id", ondelete="CASCADE"), nullable=False),
        sa.Column("snapshot_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("leg_count", sa.Integer, nullable=False),
        sa.Column("sum_yes_prices", sa.Numeric(8, 5), nullable=False),
        sa.Column("inconsistency_pp", sa.Numeric(8, 5), nullable=False),
        sa.Column("min_leg_liquidity_usd", sa.Numeric(18, 2)),
        sa.Column("leg_details", postgresql.JSONB),
        sa.PrimaryKeyConstraint("event_id", "snapshot_at"),
    )
    op.execute("SELECT create_hypertable('event_snapshots', 'snapshot_at', chunk_time_interval => INTERVAL '7 days')")
    op.create_index("idx_event_snapshots_event", "event_snapshots", ["event_id", sa.text("snapshot_at DESC")])

def downgrade():
    op.drop_table("event_snapshots")
    op.drop_table("events")
```

### Migration 3: Udvid signals-tabel

```python
# alembic/versions/0004_signals_multi_leg.py
def upgrade():
    op.add_column("signals", sa.Column("event_id", sa.Text))
    op.add_column("signals", sa.Column("legs", postgresql.JSONB))
    op.add_column("signals", sa.Column("sum_yes_prices", sa.Numeric(8, 5)))
    op.add_column("signals", sa.Column("inconsistency_pp", sa.Numeric(8, 5)))
    op.add_column("signals", sa.Column("net_edge_pp", sa.Numeric(8, 5)))
    op.add_column("signals", sa.Column("min_leg_liquidity_usd", sa.Numeric(18, 2)))
```

---

## Scheduler-konfiguration

```python
# src/pss/scheduler.py - opdateret

def setup_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="UTC")
    
    # Behold disse fra eksisterende:
    scheduler.add_job(
        discover_markets,
        trigger=IntervalTrigger(hours=1),
        id="market_discovery",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        snapshot_all_active_markets,
        trigger=IntervalTrigger(minutes=10),
        id="price_snapshot",
        max_instances=1,
        coalesce=True,
    )
    
    # Nye jobs for Strategi C:
    scheduler.add_job(
        discover_events,
        trigger=IntervalTrigger(hours=1),
        id="event_discovery",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        snapshot_events,
        trigger=IntervalTrigger(minutes=10),
        id="event_snapshot",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        scan_for_inconsistencies,
        trigger=IntervalTrigger(minutes=10),
        id="inconsistency_scan",
        max_instances=1,
        coalesce=True,
    )
    
    # IKKE i Fase 1: signal_scan og auto-execution
    
    return scheduler
```

---

## Uge-for-uge plan

### Cleanup (Uge 1)

| Dag | Opgave |
|-----|--------|
| 1 | Slet Strategi A-kode (base_rates/, base_rate_fade.py, backtesting/) |
| 2 | Slet relaterede scripts og tests |
| 3 | Alembic migration: drop has_base_rate |
| 4 | Alembic migration: opret events + event_snapshots |
| 5 | Alembic migration: udvid signals med multi-leg felter, kør lokalt + Railway |

### Fase 1: Research-pipeline (Uge 2-4)

**Uge 2:**
| Dag | Opgave |
|-----|--------|
| 1-2 | Implementér events/discovery.py med tests |
| 3-4 | Implementér events/snapshot.py med tests |
| 5 | Refactor scheduler, deploy til Railway |

**Uge 3-4:** Lad pipeline køre 14 dage. Daglig kontrol af event_snapshots-tabel.

### Fase 1 Rapport (Slut uge 4)

Generer analyse:
- Antal unikke events tracked
- Distribution af leg_count (3, 4, 5+)
- Histogram af inconsistency_pp
- Median og 90-percentil af persistens-tid for inkonsistenser >3pp
- Likviditet-distribution

Beslutning: gå til Fase 2 eller stop.

### Fase 2: Strategi-engine (Uge 5-6, kun ved positive Fase 1)

**Uge 5:**
| Dag | Opgave |
|-----|--------|
| 1-2 | Implementér InconsistencyArbitrageStrategy.scan_for_signals() |
| 3 | Risk sizing for multi-leg |
| 4-5 | Live orderbook-check (executable prices, ikke snapshot) |

**Uge 6:**
| Dag | Opgave |
|-----|--------|
| 1-2 | Signal-persistens med multi-leg struktur |
| 3 | Telegram-notifications for arbitrage-signaler |
| 4-5 | Dashboard-tilpasning: multi-leg visning |

### Fase 3: Eksekvering og paper trading (Uge 7-8)

**Uge 7:**
| Dag | Opgave |
|-----|--------|
| 1-3 | Multi-leg eksekverings-koordinator (read-only først) |
| 4-5 | Manuel eksekverings-workflow (du modtager signal, eksekverer selv) |

**Uge 8:** Paper trading. Log alle signaler. Eksekver de bedste manuelt med 10-50 USD per ben. Verificér at fills sker som modeleret.

### Fase 4: Live (Uge 9+)

Start kun hvis Fase 2-3 viser:
- 5+ signaler per uge over MIN_INCONSISTENCY_PP
- Fill rate >70% i paper
- Modeleret edge holder i live test med små positioner

Initial bankroll: 1000-2000 USD.

---

## Operationelle og sikkerhedsmæssige overvejelser

### Multi-leg specifikke risici

**Rollback policy.** Hvis ben 1 og 2 fyldes men ben 3 fejler, hvad gør vi?
- Option A: Forsøg at sælge ben 1 og 2 ud igen (kan koste 2-3% spread)
- Option B: Acceptér ubalanceret position og lad event resolvere
- Option C: Forsøg at fylde ben 3 igen om kort tid

Anbefalet: Option B for små positioner under $100 (friktion er for stor), Option A for større. Beslutningen logges i journal.

**Safety gates:**
- Maks 5% af bankroll per event
- Maks 3 åbne arbitrage-positioner samtidigt
- Stop alle nye trades ved drawdown >15%

### Tests

Test-pyramide for Fase 1:
- Unit: discovery, snapshot, inconsistency-funktioner med mocked DB/API
- Integration: end-to-end test mod test-DB med kendt event-struktur
- Manuel: efter Fase 1 sluttet, verifikation af 10 detected inkonsistenser mod live Polymarket UI

---

## Næste skridt

Når dette dokument er læst og forstået:

1. Gennemfør CLEANUP.md fase-for-fase
2. Kør migrations mod lokal DB
3. Kør migrations mod Railway
4. Implementér events/discovery.py og events/snapshot.py
5. Deploy til Railway, lad pipeline køre 14 dage
6. Fase 1 rapport-analyse og go/no-go beslutning

Konkret prompt til Cursor følger separat.
