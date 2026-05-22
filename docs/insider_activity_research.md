# Insider Activity Research (Fase 0c)

**Hypotese:** Abnormal volume + prisbevægelse 24–72h før resolution indikerer informed trading.

---

*Genereret: 2026-05-21T13:17:31.626683+00:00*

## Metode

- **Universe:** 50 højest-volume politics/macro events, resolved siden 2025-11-21
- **Pris:** CLOB `/prices-history` (daily, interval=max)
- **Volume:** trade-notional per dag; activity-proxy (|Δprice|×1M) hvis <10 dages trade-historik
- **Spike:** 48h-volume > 3.0× median daglig baseline (dage −30 til −3)
- **Pris-signal:** ≥5.0pp move i outcome-retning mellem T−72h og T−24h
- **Friktion:** 3.0pp (spread+slippage estimat fra prior PSS-tests)

## Resultater

| Metric | Værdi |
|--------|-------|
| Events analyseret | 50 |
| Med tilstrækkelig prisdata | 50 |
| Volume-spike (>3×) | 34 |
| Insider pattern (spike + pris + >24h lead) | 2 |
| Volume-spike, forkert retning (false positive) | 32 |
| Volume-spike uden insider pattern | 32 |
| Hit rate (trade 24h efter spike, alle 34 spikes) | **14.7%** |
| Hit rate (kun insider pattern, n=2) | 100% (ikke statistisk signifikant) |
| Gns. net edge (alle spikes) | **1.4pp** |
| Gns. net edge (insider pattern only) | 6.2pp |

### Konklusion

**Hit rate 15%** på alle volume-spikes (5/34 profitable), **gns. net edge 1.4pp** efter 3pp friktion. Kun **2/50** events viste fuldt insider pattern (volume-spike + pris i outcome-retning + >24h lead).

Volume-anomali er primært **støj**: 32/34 spikes havde **ikke** prisbevægelse i outcome-retning. Mange macro-events (Fed m.m.) manglede trade-historik → volume estimeret via pris-activity-proxy, hvilket inflates spike-rate.

**Endegyldig test — ingen pipeline.** Hypotesen om detekterbar insider-aktivitet via pre-resolution volume/price er ikke understøttet.

## Events med insider pattern

| Event | Spike ratio | Price move | Entry | Net edge | Profitable |
|-------|-------------|------------|-------|----------|------------|
| Will Russia capture Siversk by...? | 12.1x | 6.2pp | 0.88 | 8.9pp | True |
| U.S. Government Funding Lapse on January 31? | 6.0x | 7.1pp | 0.94 | 3.5pp | True |

## False positives (volume-spike, forkert pris-retning)

- Who will Trump nominate as Fed Chair? (move 1.3pp mod outcome)
- Portugal Presidential Election (move -0.2pp mod outcome)
- Romania: Bucharest Mayoral Election (move -0.0pp mod outcome)
- Chile Presidential Election (move 0.1pp mod outcome)
- Xi Jinping out in 2025? (move 0.2pp mod outcome)
- How many Fed rate cuts in 2025? (move -0.0pp mod outcome)
- Which party holds the most seats after Argentina Deputi (move -0.0pp mod outcome)
- Russia x Ukraine ceasefire by end of 2026? (move -3.0pp mod outcome)
- Will China invade Taiwan in 2025? (move -0.1pp mod outcome)
- Jerome Powell out as Fed Chair in 2025? (move -0.1pp mod outcome)
- Khamenei out as Supreme Leader of Iran in 2025? (move 0.1pp mod outcome)
- Which countries will Donald Trump visit in 2025? (move -0.1pp mod outcome)
- Jerome Powell out as Fed Chair by...? (move -0.0pp mod outcome)
- Who will Trump meet with in 2025? (move -0.1pp mod outcome)
- How high will 10-year Treasury yield go in 2025? (move 0.2pp mod outcome)

## Alle 50 events (summary)

| # | Event | Vol ($M) | Spike | Pattern | Move | Net edge | Note |
|---|-------|---------|-------|---------|------|----------|------|
| 1 | Fed decision in January? | 659.5 | — | — | -0pp | — | trade history short (0d); |
| 2 | Who will Trump nominate as Fed Chair? | 617.3 | ✓ | — | 1pp | 2pp | trade history short (0d); |
| 3 | Fed decision in December? | 393.9 | — | — | -0pp | — | trade history short (0d); |
| 4 | Fed decision in April? | 284.2 | — | — | 0pp | — | trade history short (0d); |
| 5 | Fed decision in March? | 260.1 | — | — | 0pp | — | trade history short (0d); |
| 6 | Portugal Presidential Election | 136.5 | ✓ | — | -0pp | -2pp |  |
| 7 | Romania: Bucharest Mayoral Election | 134.2 | ✓ | — | -0pp | -3pp |  |
| 8 | Next Prime Minister of Hungary | 101.1 | — | — | -0pp | — |  |
| 9 | Chile Presidential Election | 86.1 | ✓ | — | 0pp | -1pp |  |
| 10 | Xi Jinping out in 2025? | 78.7 | ✓ | — | 0pp | -3pp | trade history short (0d); |
| 11 | Russia x Ukraine ceasefire in 2025? | 73.8 | — | — | 0pp | — | trade history short (0d); |
| 12 | Who will be confirmed as Fed Chair? | 64.5 | — | — | 0pp | — | trade history short (0d); |
| 13 | Maduro out by...? | 56.6 | — | — | 1pp | — | trade history short (0d); |
| 14 | How many Fed rate cuts in 2025? | 31.4 | ✓ | — | -0pp | -3pp |  |
| 15 | Which party holds the most seats after A | 24.2 | ✓ | — | -0pp | -3pp |  |
| 16 | Next Prime Minister of the Netherlands | 21.9 | — | — | -0pp | — |  |
| 17 | Russia x Ukraine ceasefire by end of 202 | 14.5 | ✓ | — | -3pp | 66pp |  |
| 18 | Will China invade Taiwan in 2025? | 12.4 | ✓ | — | -0pp | -3pp |  |
| 19 | Jerome Powell out as Fed Chair in 2025? | 11.8 | ✓ | — | -0pp | -3pp |  |
| 20 | Who will Trump announce as next Fed Chai | 11.6 | — | — | 1pp | — | trade history short (0d); |
| 21 | Which party wins most seats in Argentina | 11.6 | — | — | -1pp | — |  |
| 22 | Khamenei out as Supreme Leader of Iran i | 11.0 | ✓ | — | 0pp | -3pp |  |
| 23 | Lisa Cook out as Fed Governor by...? | 10.2 | — | — | -0pp | — |  |
| 24 | Which countries will Donald Trump visit  | 6.7 | ✓ | — | -0pp | -3pp |  |
| 25 | Jerome Powell out as Fed Chair by...? | 6.5 | ✓ | — | -0pp | -2pp |  |
| 26 | Who will Trump meet with in 2025? | 6.0 | ✓ | — | -0pp | -3pp |  |
| 27 | How high will 10-year Treasury yield go  | 5.9 | ✓ | — | 0pp | -2pp |  |
| 28 | Israel x Iran ceasefire broken by...?  | 5.1 | ✓ | — | -1pp | 41pp |  |
| 29 | Will the Iranian regime fall in 2025? | 5.0 | — | — | 0pp | — |  |
| 30 | Israel and Saudi Arabia normalize relati | 3.7 | ✓ | — | -0pp | -3pp |  |
| 31 | Will Iran close the Strait of Hormuz in  | 3.5 | ✓ | — | 0pp | -3pp |  |
| 32 | Will Putin meet with Zelenskyy in 2025? | 3.1 | ✓ | — | 0pp | -3pp |  |
| 33 | Nuclear weapon detonation in 2025? | 2.9 | ✓ | — | 0pp | -3pp |  |
| 34 | US-Iran nuclear deal in 2025? | 2.8 | ✓ | — | 0pp | -3pp |  |
| 35 | Putin out as President of Russia in 2025 | 2.7 | ✓ | — | -0pp | -3pp |  |
| 36 | Ukraine signs peace deal with Russia in  | 2.6 | — | — | 0pp | — |  |
| 37 | Will Russia capture Siversk by...? | 2.5 | ✓ | ✓ | 6pp | 9pp |  |
| 38 | Israel withdraws from Gaza in 2025? | 2.3 | ✓ | — | 0pp | -2pp |  |
| 39 | Judy Shelton Fed Chair Nomination Odds a | 2.0 | ✓ | — | 2pp | -2pp | trade history short (0d); |
| 40 | China x Taiwan military clash by...? | 2.0 | ✓ | — | -0pp | -3pp |  |
| 41 | Will Ukraine agree to cede territory to  | 1.9 | ✓ | — | 0pp | -2pp |  |
| 42 | U.S. Government Funding Lapse on January | 1.8 | ✓ | ✓ | 7pp | 3pp | trade history short (0d); |
| 43 | Will China unban Bitcoin in 2025? | 1.8 | — | — | -0pp | — |  |
| 44 | Will the US officially declare war on Ir | 1.7 | — | — | -0pp | — |  |
| 45 | Israel strikes Iran before 2026? | 1.7 | ✓ | — | 0pp | -1pp |  |
| 46 | Ukraine agrees not to join NATO in 2025? | 1.6 | ✓ | — | 1pp | -3pp |  |
| 47 | Fed emergency rate cut in 2025? | 1.6 | ✓ | — | -0pp | -3pp |  |
| 48 | Will Yoon be sentenced to prison in 2025 | 1.6 | ✓ | — | 0pp | -3pp |  |
| 49 | How many dissent at the next Fed meeting | 1.5 | ✓ | — | 0pp | -2pp |  |
| 50 | Iran Nuke in 2025? | 1.5 | ✓ | — | 0pp | -3pp |  |