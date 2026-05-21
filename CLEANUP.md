# PSS Cleanup Plan - Pivot fra Strategi A til Strategi C

**Version:** 1.0
**Dato:** Maj 2026
**Status:** Klar til eksekvering

## Formål

Strategi A (base_rate_fade) er frosset permanent som handelsstrategi efter at backtest og live-test viste at konceptet ikke har edge på de markedstyper hvor templates virker. Projektet pivoteres til Strategi C (cross-market konsistens / arbitrage), som har et helt andet edge-grundlag.

Dette dokument beskriver præcis hvad der fjernes, hvad der beholdes, og hvad der refactores. Cursor følger dette dokument trin-for-trin med stop mellem hver fase.

## Princippet bag oprydning

Vi river ikke hele systemet ned. Infrastrukturen er bygget rigtigt og er strategi-agnostisk. Vi fjerner kun det strategi-specifikke lag der ikke længere er relevant.

| Lag | Status | Begrundelse |
|-----|--------|-------------|
| DB schema (markets, snapshots, positions) | Behold | Strategi-agnostisk infrastruktur |
| Gamma og CLOB klienter | Behold | API-adgang er den samme |
| Market discovery + price snapshot | Behold | Vi har stadig brug for markedsdata |
| Scheduler | Behold (omkonfigureres) | Schedule for nye jobs |
| Telegram notifications | Behold | Alert-system genbruges |
| Logging + health server | Behold | Operationel infrastruktur |
| Risk sizing | Behold (modificeres) | Kelly + caps stadig relevant, men sizing-logik for arbitrage er anderledes |
| Dashboard skelet | Behold | Tilpasses til nye signal-typer |
| Base rates (hele mappen) | Fjern | Specifikt til Strategi A |
| Strategi base_rate_fade | Fjern | Strategi A er død |
| Classifier + templates | Fjern | Brugte kun til Strategi A |
| FRED integration | Fjern | Brugte kun til fair value-beregning |
| Backtesting (eksisterende) | Fjern | Bygget specifikt til base_rate_fade; ny backtest til C bygges nyt |
| Journal | Behold | Generisk struktur, kan genbruges |
| Performance metrics | Behold | Generisk, strategi-agnostisk |

## Fase 1: Fjern Strategi A-specifik kode

Disse filer og mapper slettes fuldstændigt. Ingen import af dem skal blive tilbage i kodebasen.

### Filer der slettes

```
src/pss/base_rates/
  __init__.py
  apply_flags.py
  categories.py
  cb_meeting_fair.py
  classifier.py
  estimates.py
  fred.py
  priors.py
  seed.py
  templates.py
  types.py

src/pss/strategies/base_rate_fade.py

src/pss/backtesting/
  __init__.py
  analysis.py
  config.py
  data_loader.py
  engine.py
  friction.py
  simulator.py
  types.py
```

### Scripts der slettes

```
scripts/apply_base_rate_flags.py
scripts/analyze_backtest.py
scripts/backfill_price_history.py
scripts/backtest_week7_report.py
scripts/classify_markets.py
scripts/expire_stale_new_signals.py
scripts/list_base_rate_categories.py
scripts/review_all_new_signals.py
scripts/review_signal.py
scripts/run_backtest.py
scripts/scan_and_size_signals.py
scripts/scan_base_rate_signals.py
scripts/seed_base_rates.py
scripts/test_backtest_engine.py
scripts/test_cb_meeting_fair.py
scripts/test_classifier.py
scripts/test_strategy_base.py
scripts/bulk_signal_decision.py
scripts/pre_trade_journal.py
scripts/notify_test_signal.py
```

### Tests der slettes

Alle tests under `tests/` der refererer til base_rates, classifier, templates, base_rate_fade, eller cb_meeting_fair.

### Arkiv-data

`data/archive/invalid_baseline/` arkiveres som historisk dokumentation. Slettes ikke. Tilføj en `ARCHIVED_NOTES.md` i mappen der forklarer kontekst.

## Fase 2: Refactor af DB schema

Vi tilføjer felter og tabeller til at understøtte arbitrage-tracking, og fjerner felter der kun bruges af Strategi A.

### Markets-tabel

**Fjern:** `has_base_rate` kolonne (kan markeres deprecated først, fjernes i senere migration).

**Behold:** Alle andre felter inkl. `event_id` (kritisk for Strategi C - linker markeder i samme event).

### Signal-tabel

Strategi C-signaler er fundamentalt forskellige fra Strategi A. Vi tilføjer felter:

```sql
ALTER TABLE signals ADD COLUMN event_id TEXT;
ALTER TABLE signals ADD COLUMN legs JSONB;  -- liste af {market_id, side, market_price, size_usd}
ALTER TABLE signals ADD COLUMN sum_yes_prices NUMERIC(8,5);  -- summen af YES-priser på tværs af ben
ALTER TABLE signals ADD COLUMN inconsistency_pp NUMERIC(8,5);  -- afvigelse fra 100% i procentpoint
ALTER TABLE signals ADD COLUMN net_edge_pp NUMERIC(8,5);  -- efter friktion
ALTER TABLE signals ADD COLUMN min_leg_liquidity_usd NUMERIC(18,2);  -- bottleneck-likviditet
```

Eksisterende felter (market_id, strategy, side, market_price, fair_value_estimate, etc.) beholdes for bagudkompatibilitet, men for arbitrage-signaler er de mindre relevante.

### Ny tabel: events

For at tracke Polymarket-events struktureret:

```sql
CREATE TABLE events (
    id BIGSERIAL PRIMARY KEY,
    event_id TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    description TEXT,
    slug TEXT,
    end_date TIMESTAMP WITH TIME ZONE,
    is_active BOOLEAN DEFAULT TRUE,
    is_resolved BOOLEAN DEFAULT FALSE,
    neg_risk BOOLEAN DEFAULT FALSE,
    raw_metadata JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_events_active ON events (is_active);
CREATE INDEX idx_events_end_date ON events (end_date);
```

### Ny tabel: event_snapshots

Tidsserier af event-konsistens (sum af YES-priser på tværs af ben). Vigtigt for at se hvor ofte og hvor længe inkonsistenser persisterer.

```sql
CREATE TABLE event_snapshots (
    event_id BIGINT NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    snapshot_at TIMESTAMP WITH TIME ZONE NOT NULL,
    leg_count INTEGER NOT NULL,
    sum_yes_prices NUMERIC(8,5) NOT NULL,
    inconsistency_pp NUMERIC(8,5) NOT NULL,
    min_leg_liquidity_usd NUMERIC(18,2),
    leg_details JSONB,  -- {market_id, yes_price, liquidity_usd, bid, ask} per ben
    PRIMARY KEY (event_id, snapshot_at)
);

SELECT create_hypertable('event_snapshots', 'snapshot_at', chunk_time_interval => INTERVAL '7 days');
CREATE INDEX idx_event_snapshots_event ON event_snapshots (event_id, snapshot_at DESC);
```

## Fase 3: Konfiguration og scheduler

Scheduler-jobs der kun var relevante for Strategi A fjernes. Nye jobs tilføjes for Strategi C.

### Fjernes fra scheduler.py

- `signal_scan` (kaldte base_rate_fade)
- Alt der refererer til base_rates

### Tilføjes til scheduler.py

| Job | Frekvens | Formål |
|-----|----------|--------|
| event_discovery | Hver time | Find aktive Polymarket-events med multi-leg struktur |
| event_snapshot | Hver 5-10 min | Snapshot sum_yes_prices for hver tracked event |
| inconsistency_scan | Hver 5 min | Detect events hvor sum afviger fra 100% mere end threshold |

### Behold uændret

- `market_discovery` (hver time)
- `price_snapshot` (hver 10 min)

## Fase 4: Dashboard tilpasning

Dashboard-sider tilpasses til Strategi C.

### Side 1: Signaler

Vises stadig, men signalvisning ændres til at fokusere på multi-leg inkonsistenser:
- Event-titel
- Liste over ben med YES-pris og likviditet
- Sum af YES-priser
- Inkonsistens i procentpoint
- Forventet edge efter friktion
- Min-likviditet på tværs af ben

### Side 2: Positioner

Tilpasses til at vise multi-leg positioner som én logisk position med flere fysiske ben.

### Side 3: Journal

Skemaet for pre-trade tjekliste ændres. Cross-market arbitrage har andre risici end mean-reversion. Nye spørgsmål:
- Hvad er din confidence i at alle ben kan fyldes med size?
- Hvad er den værste partial-fill scenario?
- Hvad er din exposure hvis ét ben resolverer anderledes end forventet?

### Side 4: Performance

Beholdes med små justeringer. Inkluder ny metric: "fill rate" (andel signaler hvor alle ben blev udfyldt med fuld size).

## Fase 5: Ingestion-pipeline udvidelse

`market_discovery.py` skal udvides så den også populerer `events`-tabellen og linker markeder til events via `event_id`.

`price_snapshot.py` skal udvides så den efter snapshot af alle markeder også beregner og gemmer `event_snapshots` for events med multi-leg struktur.

Ny fil: `src/pss/events/discovery.py` med funktionen `discover_events()`.
Ny fil: `src/pss/events/snapshot.py` med funktionen `snapshot_events()`.

## Faseplan for cleanup

| Fase | Indhold | Estimat |
|------|---------|---------|
| 1 | Slet Strategi A-kode + scripts + tests | 2-3 timer |
| 2 | DB migration (Alembic) + nye tabeller | 3-4 timer |
| 3 | Refactor scheduler | 2 timer |
| 4 | Refactor dashboard | 4-6 timer |
| 5 | Nye ingestion-moduler (events) | 1-2 dage |

Forventet samlet cleanup-tid: 3-5 dage med 10 timers ugentlig allokering.

## Stop-kriterier mellem faser

Mellem hver fase: kør hele test-suite, verificer at scheduler stadig starter uden fejl, og verificer at dashboard kan loades. Hvis noget fejler, stop og adresser før næste fase.

## Hvad sker der efter cleanup

Når cleanup er gennemført, har du et tomt strategi-lag oven på et fungerende infrastruktur-fundament. Næste fase er research og implementering af Strategi C, som beskrevet i nye STRATEGY.md og IMPLEMENTATION.md.

Vigtigt: før første kodelinje på Strategi C skrives, gennemføres en 2-3 ugers empirisk research-fase med kun event-discovery og event-snapshot pipeline. Vi bygger ikke trading-logik før vi har konkrete data om hvor ofte og hvor stor inkonsistenser eksisterer.
