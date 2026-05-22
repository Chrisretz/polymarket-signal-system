# Copy Trading Research — Fase 0

**Status:** Empirisk research (ingen implementation)  
**Dato:** 2026-05-21  
**Formål:** Validér om der findes nok kvalificerede Polymarket-wallets til copy trading som strategi.

---

## 1. Polymarket Data API — endpoint-oversigt

**Base URL:** `https://data-api.polymarket.com`  
**Auth:** Ingen for read-only profile/leaderboard endpoints (offentlige data).  
**Trading/CLOB write:** Kræver API-nøgle (L1/L2) — ikke relevant for denne research.

**Kilde:** [Polymarket API docs](https://docs.polymarket.com/api-reference/introduction), [Rate Limits](https://docs.polymarket.com/api-reference/rate-limits)

### 1.1 Wallet trade history

| | |
|---|---|
| **Endpoint** | `GET /trades` |
| **Formål** | Hent individuelle trade fills for wallet og/eller markeder |
| **Auth** | Nej |

**Vigtige query params:**

| Param | Beskrivelse |
|-------|-------------|
| `user` | Wallet-adresse (`0x` + 40 hex) |
| `limit` | 0–10.000 (default 100) |
| `offset` | 0–10.000 |
| `takerOnly` | `true` (default) / `false` — inkl. maker fills |
| `side` | `BUY` / `SELL` |
| `market` | Condition IDs (comma-sep.) |
| `eventId` | Event IDs |
| `filterType` + `filterAmount` | Min. `CASH` eller `TOKENS` volume |

**Response-felter per fill:**

`proxyWallet`, `side`, `asset`, `conditionId`, `size`, `price`, `timestamp`, `title`, `slug`, `eventSlug`, `outcome`, `outcomeIndex`, `transactionHash`, `name`, `pseudonym`

**Begrænsning:** Paginering max `offset + limit` ≈ 20.000 rækker per wallet. Fills ≠ resolved bets.

### 1.2 Top wallets / leaderboard

| | |
|---|---|
| **Endpoint** | `GET /v1/leaderboard` |
| **Formål** | Ranked traders efter PnL eller volume |
| **Auth** | Nej |

**Query params:**

| Param | Default | Options |
|-------|---------|---------|
| `orderBy` | `PNL` | `PNL`, `VOL` |
| `timePeriod` | `DAY` | `DAY`, `WEEK`, `MONTH`, `ALL` |
| `category` | `OVERALL` | `POLITICS`, `SPORTS`, `CRYPTO`, `CULTURE`, `ECONOMICS`, `TECH`, `FINANCE`, … |
| `limit` | 25 | 1–50 |
| `offset` | 0 | 0–1000 |
| `user` / `userName` | — | Filter til én trader |

**Response:** `rank`, `proxyWallet`, `userName`, `vol`, `pnl`, `profileImage`, `xUsername`, `verifiedBadge`

**Note:** Top 100 by all-time volume = 2 kald (`limit=50`, `offset=0` og `offset=50`) med `orderBy=VOL&timePeriod=ALL`.

### 1.3 Resolved P&L (anbefalet for performance)

| | |
|---|---|
| **Endpoint** | `GET /closed-positions` |
| **Formål** | Lukkede/afsluttede positioner med **realiseret P&L** |
| **Auth** | Nej |

**Query params:**

| Param | Beskrivelse |
|-------|-------------|
| `user` | **Required** — wallet-adresse |
| `limit` | 0–50 (default 10) |
| `offset` | 0–100.000 |
| `sortBy` | `REALIZEDPNL`, `TIMESTAMP`, `TITLE`, … |
| `sortDirection` | `ASC` / `DESC` |

**Response-felter:**

`realizedPnl`, `avgPrice`, `totalBought`, `curPrice`, `timestamp`, `title`, `slug`, `eventSlug`, `outcome`, `conditionId`, `endDate`

→ **Én closed position ≈ én resolved market-bet** (bedre end at rekonstruere P&L fra `/trades` fills).

### 1.4 Andre relevante endpoints

| Endpoint | Formål |
|----------|--------|
| `GET /positions` | Åbne positioner (urealiseret) |
| `GET /activity` | Wallet-aktivitet (TRADE, REDEEM, MERGE, …) med `usdcSize` |
| `GET /v1/profile/{address}` | Offentlig profil |
| `GET /v1/markets-traded` | Antal markeder handlet |
| `GET /value` | Total værdi af åbne positioner |

### 1.5 Rate limits (Data API)

| Endpoint | Limit |
|----------|-------|
| General | 1.000 req / 10s |
| `/trades` | 200 req / 10s |
| `/closed-positions` | 150 req / 10s |
| `/positions` | 150 req / 10s |

Throttling (Cloudflare queue) — ikke hard 429 ved let overskridelse. Research-script bruger ~12 req/s.

---

## 2. Metodologi

### 2.1 Wallet-univers

- Hent **top 100** wallets: `GET /v1/leaderboard?orderBy=VOL&timePeriod=ALL&category=OVERALL`
- For hver wallet: paginer `GET /closed-positions` (50 per side)
- **Volume-adaptive cap:** Wallets med >$100M volume cap'es ved 2.500 positions; lavere volume op til 15.000. Flagges i `fetch_note`.

### 2.2 Metrics (per wallet)

| Metric | Beregning |
|--------|-----------|
| Resolved trades | Antal closed positions |
| Total realiseret P&L | Sum af `realizedPnl` |
| Win rate | Andel positions med `realizedPnl > $0.01` |
| Avg trade size | Mean(`avgPrice × totalBought`) |
| Return % per position | `realizedPnl / (avgPrice × totalBought)` |
| Sharpe (approx.) | `mean(return %) / stdev(return %)` på position-niveau |
| Aktiv periode | `(max timestamp − min timestamp)` i dage |
| Kategorier | Keyword-klassifikation på `title` / `eventSlug` |

### 2.3 Filterkriterier

- ≥ 200 resolved positions (closed)
- ≥ 6 måneders aktivitet (180 dage)
- Positiv total realiseret P&L
- Sharpe approximation > 0.5

### 2.4 Kendte begrænsninger

1. **Volume-leaderboard ≠ copy-trading-kandidater** — høj volume kan være market making / hedging
2. **Pagination cap** — wallets med >15k closed positions trunceres i denne run
3. **`/trades` cap** — max ~20k fills tilgængelige; bruger closed positions som primær P&L-kilde
4. **Leaderboard PnL vs closed-position PnL** kan afvige (åbne positioner, timing)
5. **Sharpe på position-niveau** er ikke annualiseret — kun relativ ranking

---

## 3. Resultater

<!-- GENERATED BELOW -->

*Genereret: 2026-05-21T12:38:46.782310+00:00*

## 3. Top 100 wallets efter volume (basis-metrics)

| Rank | User | Volume ($M) | LB PnL ($) | Closed pos | Win% | Realized PnL ($) | Sharpe | Active days |
|------|------|-------------|------------|------------|------|------------------|--------|-------------|
| 1 | swisstony | 796.4 | 8,680,451 | 2500 | 45.2 | -101,761 | -0.05 | 48 |
| 2 | tripping | 680.1 | 96,055 | 805 | 56.8 | 96,067 | 0.07 | 413 |
| 3 | risk-manager | 658.0 | 323,327 | 974 | 60.5 | 435,824 | 0.07 | 559 |
| 4 | RN1 | 570.2 | 9,053,092 | 2500 | 60.0 | 136,288 | 0.14 | 66 |
| 5 | gmanas | 529.0 | 4,955,881 | 2500 | 59.4 | 8,749,963 | 0.08 | 47 |
| 6 | cigarettes | 501.4 | 1,063,701 | 2500 | 38.2 | 53,694 | 0.05 | 60 |
| 7 | 0x492442EaB586F242B53bDa933fD5dE859c8A3782-1766317541188 | 493.0 | -1,808,586 | 1657 | 50.0 | -1,636,867 | -0.01 | 148 |
| 8 | 0x2a2C53bD278c04DA9962Fcf96490E17F3DfB9Bc1-1772479215461 | 476.7 | 4,231,246 | 2500 | 53.2 | 2,272,119 | 0.07 | 38 |
| 9 | ImJustKen | 474.6 | 3,099,797 | 2500 | 53.2 | 361,425 | 0.10 | 724 |
| 10 | InfiniteCrypt0 | 458.1 | 113,157 | 625 | 55.7 | 107,063 | 0.12 | 421 |
| 11 | debased | 455.6 | 1,475,065 | 2500 | 47.0 | 79,591 | 0.18 | 507 |
| 12 | GamblingIsAllYouNeed | 430.3 | 4,925,386 | 2500 | 55.3 | 462,086 | 0.01 | 11 |
| 13 | interstellaar | 413.5 | 122,327 | 2500 | 66.6 | 125,599 | 0.19 | 561 |
| 14 | ArmageddonRewardsBilly | 399.3 | 269,625 | 2500 | 45.0 | -18,832 | 0.26 | 30 |
| 15 | sovereign2013 | 399.3 | 3,588,720 | 2500 | 51.1 | 76,037 | 0.03 | 79 |
| 16 | TheGuru-791 | 397.5 | 574,050 | 980 | 45.4 | 574,050 | -0.07 | 725 |
| 17 | YatSen | 342.3 | 2,312,190 | 864 | 47.8 | 3,315,131 | 0.03 | 692 |
| 18 | XAE12Archangel | 315.5 | 292,706 | 1334 | 72.8 | 12,100,570 | 0.04 | 788 |
| 19 | Q96s3kwozynxpau | 313.4 | 485,000 | 499 | 46.5 | 471,971 | 0.03 | 760 |
| 20 | .Sisyphus | 300.4 | 489,968 | 2500 | 74.0 | 154,442 | 0.15 | 295 |
| 21 | kch123 | 290.5 | 12,545,268 | 2500 | 61.3 | 37,146,756 | 0.14 | 248 |
| 22 | LuckyNFT444 | 287.6 | 65,005 | 389 | 66.6 | 64,984 | 0.13 | 537 |
| 23 | VeryLucky888 | 276.2 | 230,461 | 2500 | 64.4 | 28,026 | -0.01 | 66 |
| 24 | Desy-1725192185234 | 262.3 | 103,648 | 544 | 74.4 | 86,576 | 0.21 | 624 |
| 25 | GMIB | 261.2 | 69,071 | 237 | 80.6 | 79,307 | 0.11 | 495 |
| 26 | influenz.eth | 259.8 | 1,846,541 | 2500 | 36.0 | 7,208 | 0.14 | 42 |
| 27 | Countryside | 256.5 | 1,580,077 | 551 | 93.6 | 29,397,975 | 0.91 | 194 |
| 28 | AiBird | 251.6 | 114,505 | 2500 | 43.2 | 43,201 | 0.03 | 195 |
| 29 | DrPufferfish | 248.5 | 3,548,541 | 877 | 90.4 | 46,169,478 | 0.58 | 347 |
| 30 | Spon | 242.7 | 133,835 | 1234 | 53.1 | 142,132 | 0.10 | 522 |
| 31 | poorsob | 240.8 | 318,102 | 190 | 93.2 | 313,737 | 0.10 | 203 |
| 32 | StarryPath | 239.7 | 44,370 | 2500 | 46.6 | 43,491 | 0.02 | 462 |
| 33 | EF203F2IPFC2ICP20W-CP3 | 226.9 | -43,728 | 2500 | 53.8 | 73,354 | 0.16 | 25 |
| 34 | qrpenc | 225.8 | 332,567 | 2500 | 13.1 | 459,661 | 0.04 | 142 |
| 35 | bobe2 | 224.5 | 1,822,031 | 1502 | 87.8 | 1,745,333 | -0.04 | 1042 |
| 36 | beachboy4 | 221.5 | 5,101,526 | 184 | 53.3 | 5,105,007 | 0.03 | 170 |
| 37 | aenews2 | 219.9 | 1,953,033 | 2500 | 53.0 | 4,508,161 | 0.11 | 630 |
| 38 | elkmonkey | 215.5 | 431,885 | 2500 | 50.0 | -396,339 | -0.00 | 279 |
| 39 | bossoskil1 | 213.0 | -2,341,138 | 1380 | 60.3 | 13,131,657 | 0.24 | 134 |
| 40 | wokerjoesleeper | 212.9 | 874,200 | 2500 | 32.6 | 26,157 | 0.03 | 65 |
| 41 | k9Q2mX4L8A7ZP3R | 209.1 | 1,720,272 | 2500 | 49.1 | 33,674 | -0.24 | 15 |
| 42 | planktonXD | 208.3 | 107,248 | 2500 | 61.3 | 3,685 | 0.06 | 70 |
| 43 | Apsalar | 204.6 | 983,030 | 2500 | 36.3 | 9,287 | 0.15 | 153 |
| 44 | Sharky6999 | 203.3 | 878,181 | 2500 | 95.9 | 186,142 | -0.04 | 210 |
| 45 | Ignisss | 201.0 | 37,395 | 2500 | 16.4 | -88,928 | 0.06 | 247 |
| 46 | gloriafoster | 200.6 | 10,447 | 194 | 91.2 | 294,113 | 0.63 | 179 |
| 47 | 0x8dxd | 200.2 | 2,382,957 | 2500 | 49.8 | 80,314 | -0.15 | 12 |
| 48 | undertaker | 197.6 | 286,474 | 2500 | 28.4 | 26,563 | 0.04 | 236 |
| 49 | SeriouslySirius | 192.6 | 3,648,172 | 2500 | 77.0 | 12,718,975 | 0.62 | 42 |
| 50 | wasianiversonworldchamp2025 | 192.3 | -2,432,083 | 478 | 49.0 | 7,237,188 | 0.07 | 57 |
| 51 | HotChili | 190.8 | 73,093 | 2500 | 24.1 | 92,435 | 0.10 | 505 |
| 52 | Pestle | 187.1 | 1,900,088 | 2500 | 35.1 | -37,720 | 0.13 | 220 |
| 53 | 11122 | 185.5 | 665,018 | 2500 | 43.0 | 434,147 | 0.22 | 229 |
| 54 | 432614799197 | 185.5 | 4,526,176 | 2500 | 66.8 | 17,677,420 | 0.35 | 33 |
| 55 | kingfisher | 185.3 | -238,575 | 2500 | 40.8 | -245,059 | 0.19 | 107 |
| 56 | c0O0OLI0O03 | 184.9 | 83,581 | 102 | 73.5 | 60,753 | 0.07 | 659 |
| 57 | S-Works | 184.6 | 2,749,539 | 2500 | 57.9 | 254,033 | 0.07 | 126 |
| 58 | Hersheys | 180.4 | 38,626 | 328 | 69.8 | 38,626 | 0.25 | 390 |
| 59 | knedloveprovelo | 179.0 | 492,802 | 2500 | 75.0 | 1,847,070 | 0.35 | 22 |
| 60 | ferrariChampions2026 | 178.0 | 1,826,298 | 2500 | 71.2 | 3,020,764 | 0.32 | 10 |
| 61 | TimeQuestion | 177.9 | 215,770 | 1838 | 49.9 | 216,726 | 0.10 | 328 |
| 62 | BoneReader | 176.8 | 1,042,625 | 2500 | 59.8 | 16,165 | 0.02 | 24 |
| 63 | 0xfb1c3c1ab4fb2d0cbcbb9538c8d4d357dd95963e | 175.0 | 413,391 | 2500 | 49.9 | 228,028 | 0.20 | 214 |
| 64 | 50Whence | 172.9 | 1,118,848 | 2500 | 50.2 | 125,334 | 0.08 | 620 |
| 65 | ashash111 | 172.8 | 34,151 | 136 | 72.1 | 32,773 | 0.52 | 82 |
| 66 | Zippy | 172.2 | 53,154 | 362 | 57.2 | 53,487 | 0.06 | 635 |
| 67 | 0x53757615de1c42b83f893b79d4241a009dc2aeea | 169.5 | -2,860,301 | 2500 | 39.2 | -1,340,217 | -0.07 | 124 |
| 68 | SMCAOMCRL | 163.7 | -332,180 | 2500 | 64.2 | 340,973 | 0.04 | 76 |
| 69 | Car | 161.5 | 1,307,914 | 2500 | 62.8 | 241,923 | 0.03 | 356 |
| 70 | qwertyasdfghjkl | 158.5 | 1,438,541 | 2500 | 54.8 | 1,892,438 | 0.09 | 183 |
| 71 | LynxTitan | 156.2 | 336,001 | 2500 | 57.1 | 7,858 | 0.19 | 27 |
| 72 | sleepy-panda | 155.7 | 240,616 | 2500 | 54.0 | 715,526 | 0.07 | 333 |
| 73 | 0xb7511d7b0dcb75ffad0507cbac7223653d08915 | 150.7 | -1,225,773 | 2500 | 50.0 | -44,423 | 0.03 | 12 |
| 74 | 10xBTClong | 150.3 | -10,021,172 | 175 | 97.7 | 28,810,917 | 2.25 | 48 |
| 75 | CemeterySun | 148.7 | 1,927,133 | 2500 | 66.6 | 12,281,227 | 0.34 | 17 |
| 76 | Lakersfan111 | 147.3 | -990,205 | 2500 | 56.0 | 944,318 | 0.18 | 34 |
| 77 | Winry | 146.9 | 47,780 | 553 | 62.9 | 53,620 | 0.08 | 599 |
| 78 | 0x4c2966a198cd7ac982110d0219b037afa9997570 | 146.5 | 102,418 | 136 | 34.6 | 104,297 | 0.04 | 122 |
| 79 | Anjun | 146.2 | 1,067,899 | 2500 | 53.5 | 88,386 | 0.14 | 1011 |
| 80 | gabagool22 | 144.8 | 868,863 | 2500 | 52.4 | 20,930 | 0.33 | 5 |
| 81 | Dillius | 144.3 | -3,673,887 | 171 | 94.7 | 28,135,741 | 0.93 | 57 |
| 82 | BabyGroot | 141.6 | 46,564 | 2500 | 44.6 | 33,740 | 0.01 | 261 |
| 83 | truthteller | 139.4 | 177,737 | 2500 | 49.8 | 268,098 | 0.07 | 1299 |
| 84 | Polfirefly | 135.1 | 72,843 | 2500 | 29.6 | 1,942,711 | 0.08 | 86 |
| 85 | ComTruise | 135.1 | 161,328 | 2500 | 49.9 | 42,927 | 0.20 | 315 |
| 86 | ExhaustedBoyBilly | 134.9 | 468,566 | 2500 | 53.7 | -113,901 | 0.12 | 100 |
| 87 | bcda | 134.5 | -959,630 | 2030 | 45.0 | -915,242 | -0.02 | 137 |
| 88 | 0xE594336603F4fB5d3ba4125a67021ab3B4347052-1769022918519 | 134.0 | 406,384 | 2500 | 50.0 | 47,720 | -0.08 | 5 |
| 89 | Erasmus. | 133.8 | 25,728 | 799 | 69.5 | 197,803 | 0.04 | 657 |
| 90 | comon119 | 133.7 | -2,901,090 | 1695 | 93.0 | 19,820,915 | 0.95 | 578 |
| 91 | JustCrazy | 133.4 | -29,667 | 1405 | 44.3 | 176,347 | 0.08 | 180 |
| 92 | TonyEffe | 132.6 | 59,608 | 75 | 68.0 | 59,324 | 0.37 | 464 |
| 93 | rwo | 131.6 | 653,393 | 2500 | 83.9 | 1,985,066 | 0.04 | 282 |
| 94 | 0x971f91a412236cc942a6f4485d3d88aa8dcb5929 | 131.5 | -21,280 | 7 | 42.9 | 99,383 | -0.46 | 1 |
| 95 | fhantombets | 129.7 | 318,147 | 2500 | 51.4 | 125,913 | 0.11 | 1079 |
| 96 | 0xb27bc932bf8110d8f78e55da7d5f0497a18b5b82 | 129.5 | 568,928 | 2500 | 48.8 | 8,368 | 0.09 | 14 |
| 97 | x6916Cc00AA1c3e75ECf4081DF7caE7D2f3592fd4 | 128.7 | 391,486 | 2500 | 60.4 | 89,182 | -0.10 | 161 |
| 98 | iDARKenjoyer | 127.1 | 600,891 | 2500 | 48.2 | 79,376 | 0.02 | 225 |
| 99 | ScottyNooo | 126.2 | 997,638 | 2500 | 46.1 | 388,581 | 0.36 | 238 |
| 100 | lameloballer | 125.8 | 36,349 | 2500 | 51.7 | 90,513 | -0.13 | 71 |

## 4. Filtreret liste (kvalitetskriterier)

**Antal der overlever filter: 3**

| User | Address | Closed | Win% | Realized PnL | Sharpe | Avg size | Active days | Top categories |
|------|---------|--------|------|--------------|--------|----------|-------------|----------------|
| comon119 | `0xc3c3b3ef…` | 1695 | 93.0% | $19,820,915 | 0.95 | $15,743 | 578 | Sports, Other, Crypto |
| Countryside | `0xbddf61af…` | 551 | 93.6% | $29,397,975 | 0.91 | $59,762 | 194 | Sports, Other, Culture |
| DrPufferfish | `0xdb27bf2a…` | 877 | 90.4% | $46,169,478 | 0.58 | $56,119 | 347 | Sports, Other, Politics |

## 5. Sanity check — top 5 efter Sharpe

### comon119 (`0xc3c3b3ef304ddbea39fa2246e683a71da5d0eec8`)

- **Leaderboard PnL:** $-2,901,090 | **Closed-pos PnL:** $19,820,915
- **Win rate:** 93.0% (1577W / 110L / 8BE)
- **Sharpe (approx):** 0.95
- **Specialisering:** Sports (1349), Other (258), Crypto (40), Politics (38), Economics (7)
- **Periode:** 2024-10-20 → 2026-05-20 (578 dage)
- **Fetch note:** complete

**Seneste 20 closed positions:**

| Date | Market | Outcome | PnL | Cost |
|------|--------|---------|-----|------|
| 2026-05-20 | Will Liaoning Tieren FC win on 2026-05-20? | Yes | $16,500 | $13,500 |
| 2026-05-20 | Will CA Tigre win on 2026-05-19? | No | $9,601 | $10,399 |
| 2026-05-20 | Will Recoleta FC win on 2026-05-19? | No | $4,750 | $5,250 |
| 2026-05-20 | Will Independiente Santa Fe win on 2026-05-19? | Yes | $172 | $89 |
| 2026-05-20 | Will AFC Bournemouth win on 2026-05-19? | No | $9,750 | $15,250 |
| 2026-05-20 | Will Chelsea FC win on 2026-05-19? | Yes | $19,600 | $20,400 |
| 2026-05-18 | Arsenal FC vs. Burnley FC: O/U 3.5 | Under | $12,336 | $12,762 |
| 2026-05-18 | Arsenal FC vs. Burnley FC: O/U 2.5 | Under | $10,050 | $4,950 |
| 2026-05-18 | RC Strasbourg Alsace vs. AS Monaco FC: O/U 3.5 | Over | $12,339 | $13,212 |
| 2026-05-18 | Will Olympique de Marseille win on 2026-05-17? | Yes | $15,600 | $14,400 |
| 2026-05-18 | Will Udinese Calcio win on 2026-05-17? | No | $11,700 | $18,300 |
| 2026-05-18 | Will Le Havre AC win on 2026-05-17? | Yes | $18,900 | $11,100 |
| 2026-05-18 | Will Paris Saint-Germain FC win on 2026-05-17? | No | $18,300 | $11,700 |
| 2026-05-18 | Spread: Paris Saint-Germain FC (-1.5) | Paris FC | $1,391 | $2,269 |
| 2026-05-18 | Will US Lecce win on 2026-05-17? | Yes | $19,300 | $10,700 |
| 2026-05-17 | Spread: FC Internazionale Milano (-2.5) | Hellas Verona FC | $131 | $233 |
| 2026-05-17 | Will Hertha BSC win on 2026-05-17? | No | $6,050 | $8,950 |
| 2026-05-17 | Brentford FC vs. Crystal Palace FC: O/U 3.5 | Over | $847 | $436 |
| 2026-05-17 | Newcastle United FC vs. West Ham United FC: O/U 2.5 | Over | $1,850 | $3,150 |
| 2026-05-17 | Will FC Volendam win on 2026-05-17? | No | $11,800 | $8,200 |

*Seneste 20: 20 winners, max win $19,600, median PnL $10,875*

### Countryside (`0xbddf61af533ff524d27154e589d2d7a81510c684`)

- **Leaderboard PnL:** $1,580,077 | **Closed-pos PnL:** $29,397,975
- **Win rate:** 93.6% (516W / 34L / 1BE)
- **Sharpe (approx):** 0.91
- **Specialisering:** Sports (515), Other (28), Culture (8)
- **Periode:** 2025-11-07 → 2026-05-20 (194 dage)
- **Fetch note:** complete

**Seneste 20 closed positions:**

| Date | Market | Outcome | PnL | Cost |
|------|--------|---------|-----|------|
| 2026-05-20 | Houston Astros vs. Minnesota Twins | Minnesota Twins | $866 | $1,102 |
| 2026-05-20 | Spread: Knicks (-6.5) | Cavaliers | $2,708 | $66,761 |
| 2026-05-20 | Spread: Knicks (-5.5) | Cavaliers | $-79,742 | $79,742 |
| 2026-05-20 | Spread: Knicks (-5.5) | Knicks | $13,226 | $13,765 |
| 2026-05-20 | Spread: Knicks (-6.5) | Knicks | $92,762 | $82,261 |
| 2026-05-20 | Cavaliers vs. Knicks | Knicks | $190,773 | $409,781 |
| 2026-05-19 | Spurs vs. Thunder | Spurs | $185,419 | $154,117 |
| 2026-05-19 | Will Morocco win the 2026 FIFA World Cup? | Yes | $-212 | $12,806 |
| 2026-05-19 | Spread: Thunder (-5.5) | Spurs | $15,813 | $12,067 |
| 2026-05-19 | Spread: Thunder (-2.5) | Spurs | $1,261 | $650 |
| 2026-05-19 | Spread: Thunder (-6.5) | Spurs | $22,642 | $20,886 |
| 2026-05-18 | Will Turkiye win the 2026 FIFA World Cup? | Yes | $-5,382 | $9,280 |
| 2026-05-18 | Arizona Diamondbacks vs. Colorado Rockies | Arizona Diamondbacks | $50 | $66 |
| 2026-05-18 | Milwaukee Brewers vs. Minnesota Twins | Minnesota Twins | $61,111 | $50,000 |
| 2026-05-18 | New York Yankees vs. New York Mets | New York Mets | $112,223 | $121,459 |
| 2026-05-18 | Will Scottie Scheffler win the 2026 PGA Championship? | No | $22 | $86 |
| 2026-05-18 | Will Fulham FC win on 2026-05-17? | No | $132,500 | $117,500 |
| 2026-05-18 | Will Chris Gotterup win the 2026 PGA Championship? | No | $128 | $1,778 |
| 2026-05-17 | Will Newcastle United FC vs. West Ham United FC end in a dra | No | $1,164 | $3,492 |
| 2026-05-17 | Will Nottingham Forest FC win on 2026-05-17? | No | $4,894 | $23,893 |

*Seneste 20: 17 winners, max win $190,773, median PnL $3,801*

### DrPufferfish (`0xdb27bf2ac5d428a9c63dbc914611036855a6c56e`)

- **Leaderboard PnL:** $3,548,541 | **Closed-pos PnL:** $46,169,478
- **Win rate:** 90.4% (793W / 80L / 4BE)
- **Sharpe (approx):** 0.58
- **Specialisering:** Sports (759), Other (115), Politics (2), Tech (1)
- **Periode:** 2025-05-30 → 2026-05-12 (347 dage)
- **Fetch note:** complete

**Seneste 20 closed positions:**

| Date | Market | Outcome | PnL | Cost |
|------|--------|---------|-----|------|
| 2026-05-12 | Will the Minnesota Timberwolves win the 2026 NBA Finals? | Yes | $-374 | $3,074 |
| 2026-05-08 | Will Netherlands win the 2026 FIFA World Cup? | Yes | $1,011 | $7,905 |
| 2026-05-07 | Timberwolves vs. Spurs | Spurs | $23,000 | $77,000 |
| 2026-05-06 | Indian Premier League: Gujarat Titans vs Royal Challengers B | Gujarat Titans | $26,107 | $21,029 |
| 2026-05-06 | Will Nottingham Forest FC vs. Aston Villa FC end in a draw? | No | $2,267 | $5,291 |
| 2026-05-06 | Will SC Freiburg win on 2026-04-30? | No | $34,533 | $88,799 |
| 2026-05-06 | Will Aston Villa FC win on 2026-04-30? | No | $794 | $1,242 |
| 2026-05-06 | Will Nottingham Forest FC win on 2026-04-30? | Yes | $56,950 | $28,050 |
| 2026-05-04 | Will Germany win the 2026 FIFA World Cup? | Yes | $-259 | $9,472 |
| 2026-05-04 | Will England win the 2026 FIFA World Cup? | Yes | $-2,098 | $13,184 |
| 2026-04-30 | Will Arsenal FC win on 2026-04-29? | No | $145,197 | $248,899 |
| 2026-04-26 | Spurs vs. Trail Blazers | Spurs | $8,381 | $14,899 |
| 2026-04-26 | Spurs vs. Trail Blazers | Trail Blazers | $-82,500 | $82,500 |
| 2026-04-26 | Spread: Cavaliers (-3.5) | Raptors | $28,372 | $26,190 |
| 2026-04-26 | Cavaliers vs. Raptors | Raptors | $189,094 | $120,896 |
| 2026-04-26 | Nuggets vs. Timberwolves | Timberwolves | $183,447 | $176,253 |
| 2026-04-25 | Pistons vs. Magic | Magic | $50,083 | $37,782 |
| 2026-04-25 | Spread: Pistons (-2.5) | Magic | $7,051 | $6,775 |
| 2026-04-25 | Spread: Celtics (-8.5) | 76ers | $3,445 | $3,055 |
| 2026-04-25 | Lakers vs. Rockets | Lakers | $10,305 | $4,509 |

*Seneste 20: 16 winners, max win $189,094, median PnL $9,343*


## 6. Konklusion

**3 wallets** overlever filteret (kræver ≥5 for levedygtighed) → strategien er **ikke levedygtig** med nuværende kriterier og wallet-univers.

### Beslutningsmatrix (fra brief)

| Resultat | Fortolkning |
|----------|-------------|
| 3 wallets (< 5) | **Ikke levedygtig** — for lille univers, høj single-point-of-failure |
| Alle 3 er sports-specialister | Ingen diversifikation; samme strategitype |
| Gns. trade size $15k–$60k | Copy trading med retail bankroll urealistisk uden slippage-test |
| 90–94% win rate | Ekstremt — kræver dybere due diligence (ikke blind copy) |

### Vigtige fund

1. **Volume-leaderboard ≠ copy-trade kandidater.** Top 100 by volume er overvejende market makers, sports bots og højfrekvens-handlere. Kun 3/100 passer stramme kvalitetsfiltre.

2. **Leaderboard PnL vs closed-position PnL afviger massivt** for flere wallets (fx comon119: LB −$2.9M vs closed +$19.8M). Brug closed positions til performance, ikke leaderboard alene.

3. **De 3 kvalificerede wallets** (comon119, Countryside, DrPufferfish) handler næsten udelukkende sports spreads/O-U/match winners med store positionsstørrelser og få store outliers (Countryside: enkeltbet op til $190k PnL).

4. **Sharpe > 0.5 er sjældent** i top-100 volume: median Sharpe ≈ 0.05–0.15. De fleste profitable high-volume traders har lav risk-adjusted return på position-niveau.

### Anbefaling

**Parkér copy trading som automatisk strategi** indtil:
- Fase 1 slippage-test på de 3 kandidater viser eksekverbar edge ved retail size, ELLER
- Universe udvides til **PnL-leaderboard** / lavere volume wallets med lavere trade sizes, ELLER
- Filter lempes (fx Sharpe > 0.3, min 100 trades) — men det øger false-positive risiko.

**Research-artefakter:**
- `docs/copy_trading_research.md` — denne rapport
- `research/copy_trading_data.json` — rå data (100 wallets, metrics, filtered, sanity)
- `scripts/copy_trading_research.py` — reproducerbart script