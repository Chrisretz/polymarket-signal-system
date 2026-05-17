# Strategi A: Base rate fade (v0)

**Status:** Implementeret uge 5–6. Paper trading — ingen live trades.  
**Kode:** `src/pss/strategies/base_rate_fade.py`  
**Strategi-slug:** `base_rate_fade`

Hypotesen og den overordnede ramme står i [STRATEGY.md §5.1](../../STRATEGY.md). Dette dokument er den **operative** reference efter uge 6 review og tuning.

---

## 1. Hypotese (kort)

Polymarket overprissætter eller underprissætter begivenheder med kendt historisk frekvens (base rate). Vi handler **mean reversion** mod base rate over dage til få uger — ikke mod nyhedsflow i realtid.

**Edge-kilde:** Behavioral (recency, narrativ).  
**Realistisk edge efter friktion:** ca. 3–8 procentpoint per trade (ikke 40 %+ som rå scanner-output kan vise ved fejlklassifikation).

---

## 2. Hvornår strategien gælder

### Marked skal opfylde

| Krav | Implementeret |
|------|----------------|
| `primary_vertical` = `macro` eller `eu_politics` | Ja |
| `has_base_rate = true` (classifier-match) | Ja |
| Aktivt, ikke lukket | Ja |
| Resolution inden for **30 dage** (eller ukendt dato) | `MAX_HORIZON_DAYS` |
| Seneste snapshot: likviditet ≥ **$7 500** | `MIN_LIQUIDITY_USD` |
| Base rate i DB med `sample_size ≥ 10` | `MIN_SAMPLE_SIZE` |
| Afvigelse mellem marked (YES) og base rate ≥ **18 pp** | `MIN_DEVIATION_PCT` |
| Risk-engine godkender (Kelly ¼, max 5 % bankroll) | `src/pss/risk/` |

### Side

- Marked **over** base rate → `BUY_NO` (fade ned)
- Marked **under** base rate → `BUY_YES` (fade op)

### Exit (automatisk i signal)

- Konvergens mod base rate (±5 pp bånd, `CONVERGENCE_BAND`)
- Senest ved `end_date` / 30 dages hold

---

## 3. Hvornår strategien **ikke** gælder (afvis)

Disse regler kommer fra uge 6 manuelt review. **Ingen position** — heller ikke paper — uden at de er opfyldt.

| Afvis hvis | Eksempel fra review |
|------------|---------------------|
| Forkert centralbank-kategori | BOJ-spørgsmål med `fed_hold` (løst i classifier v2) |
| Spørgsmål om **cut/hike**, men kategori er **hold** | «BOJ decreases rates» vs `boj_hold` |
| Granulært bps-outcome | «ECB announce 50+ bps decrease» — ikke samme som aggregeret `ecb_cut` |
| Edge **> ~35 %** efter klassifikation | Typisk fejltese eller tail-outcome til ~0 % |
| Kategori matcher ikke **spørgsmålstekst** | Tjek `review_signal` vs `classify_market_fields` |
| «Inflation reaches X% in 2026» som `us_cpi_above_consensus` | CPI-**niveau**-markeder ≠ CPI **surprise**-print |
| Du ville ikke åbne Polymarket manuelt | Ultimativt filter |

**Workflow:** Telegram → `review_signal` / `review_all_new_signals` → ved tvivl `pre_trade_journal` → kun `ACCEPTED` er kandidat til senere position.

---

## 4. Classifier (base rates)

**Kode:** `src/pss/base_rates/classifier.py`

- Centralbank: Fed / ECB / BOJ (hold, cut, hike) — **rente-handling kun fra `question`**, ikke `description` (undgår «no change» i resolutions-tekst).
- Polymarket «announce 25/50+ bps …» → **ingen** kategori (for granulært).
- Test: `uv run python scripts/test_classifier.py`

Efter ændring: `apply_base_rate_flags.py`, `seed_base_rates.py`, `expire_stale_new_signals.py`, derefter `run_signal_pipeline.py`.

---

## 5. Parametre (v0, uge 6)

| Parameter | Værdi | Note |
|-----------|-------|------|
| `MIN_DEVIATION_PCT` | 0.18 | Op fra 0.15 efter review |
| `MIN_LIQUIDITY_USD` | 7500 | Op fra 5000 |
| `MIN_SAMPLE_SIZE` | 10 | |
| `MAX_HORIZON_DAYS` | 30 | |
| `CONVERGENCE_BAND` | 0.05 | 5 pp |
| `DEFAULT_CONFIDENCE` | 0.6 | |
| Max position | 5 % bankroll | Risk-engine |
| Kelly | ¼ Kelly, cap 5 % | `src/pss/risk/sizing.py` |

---

## 6. Pipeline og drift

```
market_discovery (1t) → price_snapshot (10m) → signal_scan (1t)
                              ↓
                    base_rate_fade.scan_for_signals
                              ↓
                    risk → persist (NEW) → Telegram (nye only)
```

| Kommando | Formål |
|----------|--------|
| `uv run python scripts/run_signal_pipeline.py` | Fuld scan manuelt |
| `uv run python scripts/list_signals.py` | NEW-signaler |
| `uv run python scripts/review_all_new_signals.py` | Batch-review |
| `uv run python scripts/review_signal.py <id>` | Ét signal |
| `uv run python scripts/pre_trade_journal.py --signal-id <id>` | Pre-trade + ACCEPTED/REJECTED |
| `uv run python -m pss.scheduler` | Lokal scheduler (ellers Railway) |

**Scheduler:** Én primær instans (Railway anbefalet). `LOG_LEVEL=WARNING` i prod.

---

## 7. Uge 6 konklusion

| Emne | Konklusion |
|------|------------|
| Teknisk pipeline | Virker (scan, risk, persist, Telegram, journal) |
| Første signal-batch (4 stk.) | **Ingen** godkendt — alle `EXPIRED`/`REJECTED` efter review |
| Hovedårsag | Classifier + markedstype (tail outcomes, granulære bps) |
| Tuning | Classifier v2 + strammere deviation/likviditet → midlertidigt **0** rå signaler (OK) |
| Næste (uge 7) | Backtest walk-forward; beslut om strategi A fortsætter eller kalibreres |

---

## 8. Beslutningskriterium (uge 7+)

Strategi A **fortsætter** mod backtest hvis:

1. Classifier producerer stabile matches på **rigtige** markedstyper (CB hold/cut/hike, CPI surprise, NFP, …).
2. Manuelt review af næste 5–10 signaler: mindst nogle med **plausible** tese og edge &lt; 35 %.
3. Backtest (efter friktion) viser edge der ikke tydeligt er lookahead/survivorship.

Ellers: yderligere classifier-arbejde eller pause strategi A før strategi B.

---

*Sidst opdateret: uge 6 fredag (2026-05-17).*
