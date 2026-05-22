# Market Making Research (Fase 0d)

**Præmis:** Spread capture, ikke prisforudsigelse. 11 prior edge-strategier fejlede.

---

*Genereret: 2026-05-21T13:54:52.304886+00:00*

## Opgave 0: Polymarket market maker økonomi

### 1. Maker rewards / LP incentives

| Program | Beskrivelse |
|---------|-------------|
| **Maker Rebates** | 20–25% af taker fees redistribueres dagligt i USDC til makers hvis ordrer bliver filled. Min payout $1. |
| **Liquidity Rewards** | Separat incitamentprogram (dYdX-inspireret scoring) for resting limit orders tæt på midpoint. Daglig udbetaling. |
| **April 2026 Sports LP** | $5M+ i sports/esports liquidity incentives (pre/live per game). |
| **Maker fee** | **0** på alle kategorier — makers betaler ikke trading fee. |
| **Negative maker fees?** | Nej direkte; rebates kommer fra taker fee pool, ikke negative fees. |
| **Geopolitics** | Fee-free (ingen taker fees, ingen rebates). |

### 2. Fee structure

| Kategori | Taker fee rate | Maker fee |
|----------|----------------|-----------|
| Crypto | 0.07 | 0 |
| Sports | 0.03 | 0 |
| Finance / Politics / Tech / Mentions | 0.04 | 0 |
| Economics / Culture / Weather / Other | 0.05 | 0 |
| Geopolitics | 0 | 0 |
Formel: `fee = C × feeRate × p × (1-p)` (symmetrisk omkring 50%).

**Gas (Polygon):** Limit orders er off-chain signed; on-chain settlement sker ved match. Re-quote/cancel er gratis off-chain via CLOB API. Heartbeat påkrævet hvert 10s ellers cancel all. Estimeret ~$0.005 per batch re-quote ved on-chain allowance ops.

**Order cancellation:** Gratis via API (single, batch, all, per-market).

### 3. Order types

| Type | Beskrivelse |
|------|-------------|
| **GTC** | Good-til-cancel — default for passive quotes |
| **GTD** | Good-til-date — auto-expire |
| **FOK / FAK** | Market order typer |
| **Post-only** | Rejected hvis marketable — garanterer maker status |
### 4. Adverse selection & resolution

- Resolution via **UMA Optimistic Oracle** — 2t challenge period, op til 4-6 dage ved dispute.
- **Trading stopper** straks ved resolution; winning tokens redeemable til $1.
- Ingen dokumenteret pre-resolution order freeze ud over normal order lifecycle.
- **Heartbeat:** Manglende heartbeat inden 10s → **alle open orders cancelled**.
- Risiko: informed traders handler mod dig tæt på nyheder/resolution.

---

## Opgave 1: Flow-analyse (20 illikvide markeder)

Kriterier: avg daily volume $100–$5,000 (via `volume_total` delta), 14+ dage data, 14+ dage til resolution.

**Bemærk:** DB snapshots har **ingen bid/ask** — spread målt live via CLOB `/book` eller estimeret fra daglig pris-range.

**Trades estimeret** fra daily volume / median trade size (data-api sample).

| # | Market | Avg vol/d | Est trades/d | Spread | Inter-trade | Days left |
|---|--------|-----------|--------------|--------|-------------|-----------|
| 1 | Will 1 Fed rate cut happen in 2026? | $4,858 | 50.0 | 0pp (snap) | 29m | 223 |
| 2 | Will inflation reach more than 5% in 2026? | $4,420 | 50.0 | 2pp (snap) | 29m | 223 |
| 3 | Will the ECB announce no change at the June 2 | $3,342 | 40.6 | 3pp (snap) | 35m | 20 |
| 4 | Will the next UK election be called by June 3 | $1,578 | 15.1 | 1pp (snap) | 95m | 39 |
| 5 | Fed rate cut by July 2026 meeting? | $1,351 | 45.3 | 1pp (snap) | 32m | 26 |
| 6 | No change in Bank of Japan’s interest rates a | $1,154 | 30.7 | 4pp (snap) | 47m | 25 |
| 7 | Will the Fed Pause–Pause–Pause in the next th | $950 | 28.2 | 0pp (snap) | 51m | 26 |
| 8 | Bank of Japan increases interest rates by 25  | $948 | 34.8 | 2pp (snap) | 41m | 25 |
| 9 | Will inflation reach more than 4% in 2026? | $877 | 22.6 | 0pp (snap) | 64m | 223 |
| 10 | Will inflation reach more than 6% in 2026? | $793 | 27.9 | 3pp (snap) | 52m | 223 |
| 11 | Fed rate cut by September 2026 meeting? | $715 | 13.1 | 2pp (snap) | 110m | 26 |
| 12 | Will the upper bound of the target federal fu | $689 | 41.3 | 0pp (snap) | 35m | 201 |
| 13 | Will the Fed’s lower bound reach 2.5% or lowe | $683 | 26.8 | 0pp (snap) | 54m | 223 |
| 14 | Fed rate cut by June 2026 meeting? | $675 | 18.0 | 0pp (snap) | 80m | 26 |
| 15 | Will the Fed Pause–Pause–Cut in the next thre | $597 | 20.3 | 0pp (snap) | 71m | 26 |
| 16 | Fed rate cut by December 2026 meeting? | $588 | 22.6 | 1pp (snap) | 64m | 26 |
| 17 | Will the Fed decide differently in the next t | $575 | 17.9 | 0pp (snap) | 80m | 26 |
| 18 | Bank of Japan increases interest rates by 50+ | $520 | 10.1 | 0pp (snap) | 143m | 25 |
| 19 | Will the Fed’s lower bound reach 0.5% or lowe | $455 | 50.0 | 0pp (snap) | 29m | 223 |
| 20 | Bank of Japan decreases interest rates after  | $403 | 21.1 | 0pp (snap) | 68m | 25 |

### 5 kandidat-markeder

**Strict filter: 0/50 opfyldt** (ingen markeder med konsistent ≥10pp spread i illiquid bucket). CLOB order books er tomme (100pp artefakt); reelle daglige pris-ranges er 0–4pp. Backtest kører på **5 bedste-effort** markeder (højeste observerede spread):

| Market | Spread | Trades/d | Vol/d | Strict OK? |
|--------|--------|----------|-------|------------|
| No change in Bank of Japan’s interest rates after  | 4pp | 30.7 | $1,154 | — |
| Will inflation reach more than 6% in 2026? | 3pp | 27.9 | $793 | — |
| Will the ECB announce no change at the June 2026 m | 3pp | 40.6 | $3,342 | — |
| Fed rate cut by September 2026 meeting? | 2pp | 13.1 | $715 | — |
| Bank of Japan increases interest rates by 25 bps a | 2pp | 34.8 | $948 | — |

## Opgave 2: Simuleret market making backtest

Strategi: quote 2pp inde i spread, max $50/leg, re-quote hver 5 min. Fills simuleret fra `volume_total` deltas i snapshots.

**Simulationsbegrænsning:** Med 0–4pp observeret spread og 2pp quote-improvement er **spread capture ≈ $0** på alle markeder. Inventory PnL dominerer og er upålidelig (one-sided fills, ingen round-trips). Resultaterne understate gas/heartbeat-omkostninger og overstate inventory-exposure.

| Market | Fills | Round-trips | Spread PnL | Inventory PnL | Gas | **Net PnL** | Max inv |
|--------|-------|-------------|------------|---------------|-----|-------------|---------|
| No change in Bank of Japan’s interest ra | 1258 | 0 | $0.00 | $21588.61 | $47.52 | **$21541.09** | $70920 |
| Will inflation reach more than 6% in 202 | 1661 | 0 | $0.00 | $-36985.91 | $48.96 | **$-37034.87** | $220251 |
| Will the ECB announce no change at the J | 2477 | 0 | $0.00 | $-9835.24 | $44.64 | **$-9879.88** | $135099 |
| Fed rate cut by September 2026 meeting? | 3824 | 0 | $0.00 | $-12289.15 | $46.08 | **$-12335.23** | $318872 |
| Bank of Japan increases interest rates b | 1229 | 0 | $0.00 | $-4199.95 | $46.08 | **$-4246.03** | $63705 |

## Konklusion

**0 markeder** opfylder strict kriterier (spread ≥10pp, 2–5 trades/d). Bedste observerede spreads: 0–4pp (tomme CLOB books). Simuleret net PnL på 5 bedste-effort markeder: **$-41954.93** (1/5 positive). Spread capture dækker ikke gas + inventory risk. **Retail market making er ikke levedygtig** på Polymarket.