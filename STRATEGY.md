# Polymarket Signal System (PSS) - Strategi C
## Cross-market konsistens og arbitrage

**Version:** 2.0 (erstatter Strategi A-baseret v1.0)
**Dato:** Maj 2026
**Status:** Research-fase

---

## Hvorfor strategi-skift fra A til C

Strategi A (base_rate_fade) blev frosset permanent efter at:

1. Backtest viste 70.7% suspect classification rate på 123 trades
2. Selv efter brutal refactor til kun Fed/ECB hold-templates, viste live-test at fair value-modellen var 80 procentpoint forskellig fra markedskonsensus på ECB juni 2026-marked
3. Analyse bekræftede at CB-rate-markeder er for velinformerede til retail-edge på mean-reversion-strategier

Beslutningen var ikke at modellen var bugget. Beslutningen var at strategi-konceptet selv ikke har edge på markedstyper hvor templates kunne klassificere pålideligt.

Strategi C har et fundamentalt anderledes edge-grundlag: ren matematisk inkonsistens mellem mutually exclusive markeder i samme event. Det kræver ikke forudsigelse. Det kræver ikke at slå markedet på information. Det kræver kun at identificere når markedet er internt inkonsistent.

---

## Edge-hypotese

### Kerne-koncept

Polymarket organiserer mange markeder i events. Et event har typisk flere markeder hvor outcomes er mutually exclusive (kun ét kan resolvere som YES).

Eksempler:
- Fed møde-event: separate markeder for "hold", "cut 25bp", "hike 25bp", "cut 50+bp"
- Valg-event: separate markeder per kandidat
- Sportsbegivenhed: separate markeder per mulig vinder

For mutually exclusive markeder gælder identiteten:

```
sum(P(yes)_leg_i for alle ben i) = 1.0
```

Hvis denne sum afviger materielt fra 1.0 efter friktion, eksisterer der ren arbitrage:

- **sum < 1.0 - friktion**: køb YES på alle ben. Garanteret payout af 1.0 ved resolution. Profit = (1.0 - sum) - friktion.
- **sum > 1.0 + friktion**: køb NO på alle ben (eller sælg YES kort). Garanteret payout af (n-1).0 for n ben. Profit = (sum - 1.0) - friktion.

### Hvorfor edge sandsynligvis eksisterer

Tre strukturelle grunde til at Polymarket har konsistens-fejl:

**Likviditetsfragmentering.** Markedet behandler hvert ben som separat. En sælger på "cut 25bp"-benet er ikke nødvendigvis den samme aktør som køber på "hold"-benet. Lokale ubalancer kan ikke uden videre udlignes.

**Ingen automatisk arbitrage-bot dominans.** I modsætning til crypto-markedsplatforme hvor MEV-bots tager arbitrage-muligheder inden for millisekunder, har Polymarket begrænset systematisk arbitrage-konkurrence. Større aktører kan ignorere små inkonsistenser fordi friktion æder deres profit.

**Friktion-asymmetri.** Markets-makere kvoter typisk bredere spreads på mindre likvide ben. Et event med 4 ben kan have 1-2% spread på likvide ben og 5-8% spread på illikvide ben. Sum af mid-prices kan derfor afvige fra 1.0 uden at det er reel arbitrage, men hvis afvigelsen er stor nok til at overstige worst-case spread, er der reel mulighed.

### Hvorfor edge ikke arbitrageres væk

Selv hvis edge eksisterer, kan den persistere af flere grunde:

- Skala-grænser: arbitrage på $100-500 niveau er for småt til professionelle aktører
- Capital efficiency: at låse kapital i flere ben i uger eller måneder har høj alternative omkostning for større aktører
- Resolution-risk: oracle disputes via UMA kan forstyrre arbitrage selv om matematik er korrekt
- Eksekvering-risk: partial fills kan efterlade dig med ubalanceret position

Disse forhindringer er præcis hvad der efterlader plads til en disciplineret retail-aktør med begrænset bankroll.

### Hvad edge IKKE er

Strategi C er ikke forudsigelse. Vi tager ingen position på hvilket outcome der vinder. Vi tager position på at outcomes samlet skal summere til 1.0 ved resolution.

Hvis vi ikke kan eksekvere ren arbitrage med positiv forventet værdi efter friktion, så er der ingen handel. Vi forsøger ikke at "gætte" hvilken vej inkonsistensen vil bevæge sig.

---

## Rule Roadmap

PSS har et langsigtet regelsæt for 20 typer probability inconsistencies på Polymarket. Det er dokumenteret i [docs/strategy_c_rules.md](docs/strategy_c_rules.md) og fungerer som roadmap — ikke som noget vi implementerer i én omgang.

**Fase 1 fokuserer udelukkende på rule #8:** exhaustive mutually exclusive outcomes skal summere til ca. 100% (`sum(P(yes)) ≈ 1.0` inden for samme neg_risk-event). Event discovery, event snapshots og inconsistency-scanning i Fase 1 er bygget til netop det mønster.

**Fase 2-prioritering** (hvilke yderligere rules vi bygger) afhænger af Fase 1-rapporten: frekvens, persistens, likviditet og eksekverbarhed for sum-to-100%-inkonsistenser.

**Rules 1–7** (deadline-monotonicitet, threshold-monotonicitet, count-monotonicitet, sub-event vs. parent, osv.) har sandsynligvis bedre retail-edge end ren sum-arbitrage, men kræver markant mere sofistikeret semantisk parsing, dato/threshold-ekstraktion og validering af at to markeder faktisk refererer til samme underlying event. De er bevidst udskudt til efter Fase 1.

---

## Empirisk grundlag (skal verificeres før implementering)

Før vi bygger trading-logik, skal vi besvare disse spørgsmål med data:

1. Hvor mange aktive events på Polymarket har 3+ mutually exclusive ben?
2. Hvor ofte afviger sum(YES) fra 1.0 med mere end 3 procentpoint?
3. Hvor længe persisterer inkonsistenser (sekunder, minutter, timer, dage)?
4. Hvor stor er likviditeten på det mindst likvide ben? Det er flaskehalsen for arbitrage-størrelse.
5. Hvor mange inkonsistens-muligheder per uge passerer en realistisk friktion-threshold (eksempelvis 4-6 procentpoint efter spread og fees)?

Forventet resultat baseret på almindelige prediction market-strukturer: 2-10 reelle arbitrage-muligheder per måned med realistisk størrelse $50-500 per trade.

Hvis empirisk research viser 0 muligheder efter friktion: Strategi C er heller ikke en levedygtig retning. Vi har lært det med sikkerhed, og kan tage en kvalificeret beslutning om at parkere projektet.

---

## Realistiske forventninger

### Indkomst

Med 5.000-10.000 USD bankroll, realistisk forventning er:
- Frekvens: 2-10 trades per måned
- Edge per trade efter friktion: 2-6 procentpoint
- Average trade-størrelse: 100-500 USD (begrænset af min-leg-likviditet)
- Forventet månedlig indkomst: 50-400 USD

Det er beskedent. Det er IKKE en strategi der erstatter en indkomst. Det er en strategi der kan generere supplerende afkast med relativt lav strategi-risiko (ingen forudsigelses-risiko).

### Tidsforbrug

- Aktiv monitoring: 30-60 min/dag
- Eksekvering pr. trade: 5-15 min (multi-leg kræver omhu)
- Vedligehold og review: 2-4 timer/uge

Total: 5-10 timer/uge ved aktiv brug.

### Skalering

Strategi C skalerer ikke godt opad. Likviditet på Polymarket sætter en hård grænse omkring $1000-3000 per trade. Selv om du havde en større bankroll, ville du ikke kunne deploye den meningsfuldt.

Det er en feature, ikke en bug. Det er præcis hvorfor inkonsistenser persisterer: store aktører kan ikke meningsfuldt skalere ind i dem.

---

## Risici

### Strategi-specifikke risici

**Partial fill-risiko.** Hvis du eksekverer ben 1 og 2 men ben 3 ikke kan fyldes med fuld size, har du ubalanceret eksponering. Mitigation: konservativ size-targeting (50-70% af min-leg-depth), aldrig fyld én leg ad gangen i lav-likviditet markeder, accept at nogle muligheder slipper fordi du ikke kan fylde alle ben.

**Spread-konvergens før eksekvering.** En sum-afvigelse på 5 procentpoint målt på mid-priser kan have eksekveringspris på 2 procentpoint efter spread. Vi skal måle inkonsistens på "executable" priser (bid for at sælge, ask for at købe), ikke på mid.

**Resolution-uklarhed.** Hvis Polymarket's resolution-kriterier er vage, kan flere ben "vinde" eller ingen vinde, hvilket bryder vores antagelse om mutually exclusive. Mitigation: undgå markeder med vage formuleringer, hold sig til events med klare offentlige resolution-kilder.

### Operationelle risici

**Eksekvering-timing.** Tre-bens trade kræver tre separate order placements. Hvis priser bevæger sig mellem trades, mister du noget edge. Mitigation: brug limit orders med passende slippage tolerance, eller batched market orders hvor det er muligt.

**Oracle dispute.** UMA-baseret resolution kan blive disputeret. Hvis ét ben resolverer "anderledes end forventet", bryder hele arbitrage. Mitigation: undgå events med kendt kontrovers, diversificér resolutions over tid.

**Kapital-binding.** Multi-leg arbitrage låser kapital indtil event resolverer. Et FOMC-event kan låse kapital i 1-4 uger. Et valg-event kan låse kapital i måneder. Mitigation: ikke mere end 30% af bankroll allokeret samtidigt.

### Modelfejl-risici

**Falsk inkonsistens fra dårlig leg-identifikation.** Hvis vores system fejlagtigt grupperer ikke-mutually-exclusive markeder, beregner vi inkonsistens forkert. Mitigation: streng template-baseret identifikation af events, manuel verifikation af første 50 detected events.

**Conditional probabilities.** Hvis to "ben" i virkeligheden er betingede begivenheder ("Will Fed cut AND market rise"), så er P(yes_a) + P(yes_b) ikke nødvendigvis 1.0. Mitigation: kun stol på events hvor Polymarket eksplicit markerer dem som neg_risk eller mutually exclusive.

---

## Sammenhæng med eksisterende kode

Hvad fra det eksisterende projekt der genbruges:

**Genbruges direkte:**
- DB-infrastructure (markets, snapshots, positions)
- Gamma og CLOB klienter
- Market discovery og price snapshot pipeline
- Scheduler
- Telegram notifications
- Logging og health-server
- Dashboard skelet
- Risk sizing-modul (modificeres)

**Bygges nyt:**
- Event discovery pipeline (identificering af multi-leg events)
- Inconsistency detection-engine
- Multi-leg signal-generator
- Eksekvering-koordinator (samtidig multi-leg eksekvering)
- Arbitrage-specifik backtesting
- Tilpasset dashboard for multi-leg visning

**Fjernes:**
- Hele base_rates/-mappen
- base_rate_fade strategi
- FRED-integration
- Eksisterende backtesting (Strategi A-specifik)

Se CLEANUP.md for konkret oprydningsplan.

---

## Faser

### Fase 0: Cleanup (1 uge)

Fjern Strategi A-kode, opdater DB-schema, refactor scheduler. Beskrevet i CLEANUP.md.

### Fase 1: Empirisk research (2-3 uger)

Mål: verificér at inkonsistenser overhovedet eksisterer på Polymarket i meningsfuldt omfang.

Implementér kun event-discovery og event-snapshot pipeline. Ingen trading-logik.

Track inkonsistenser dagligt i 2-3 uger. Generer rapport:
- Antal aktive multi-leg events
- Frekvens af inkonsistenser over forskellige thresholds (1pp, 3pp, 5pp)
- Persistens-tid af inkonsistenser
- Likviditets-distribution per ben

Beslutning efter Fase 1: gå videre til Fase 2, eller acceptér at edge ikke eksisterer i målbar form.

### Fase 2: Signal-engine (2 uger, kun hvis Fase 1 validerer hypotesen)

Byg `InconsistencyArbitrageStrategy` der:
- Scanner events for sum-afvigelser
- Bekræfter at afvigelser overlever friktion-test
- Beregner optimal size per ben baseret på min-leg-likviditet
- Genererer multi-leg signal

### Fase 3: Eksekvering og paper trading (2 uger)

Byg eksekvering-koordinator med samtidig multi-leg placement. Paper trade i 2 uger.

### Fase 4: Live capital med begrænset bankroll (8+ uger)

Start med 1000-2000 USD. Track real performance vs paper. Skaler op kun hvis live matcher paper.

Total tid fra cleanup til live: cirka 3 måneder med 10 timer/uge.

---

## Hvad denne strategi IKKE er

For at undgå at fælder vi gentager:

Den er ikke en mean-reversion-strategi baseret på fair value-modeller. Vi har lært at fair value-modeller mod velinformerede markeder ikke virker.

Den er ikke afhængig af forudsigelse. Vi tager ingen view på hvilket outcome der vinder.

Den er ikke skalerbar til store summer. Forvent ikke at gå fra 5k til 50k bankroll i denne strategi.

Den er ikke "set and forget". Inkonsistenser opstår og forsvinder. Manuel triage er stadig nødvendig.

---

## Stop-kriterier for hele projektet

Hvis efter Fase 1 (3 uger empirisk research):
- 0 inkonsistenser over 4 procentpoint efter friktion er observeret
- Eller alle inkonsistenser persisterer i under 5 minutter (umuligt at eksekvere på)
- Eller min-leg-likviditet er konsistent under $50 (ingen meningsfuld størrelse)

Så stoppes projektet, og Polymarket arbitrage konstateres ikke at være levedygtig retail-strategi.

Hvis efter Fase 4 (8 uger live):
- Realiseret PnL er negativ efter friktion og kapital-omkostning
- Eller drawdown overstiger 25% af bankroll
- Eller fill rate er under 60% (kan ikke pålideligt eksekvere)

Så stoppes live trading og projektet pauses for vurdering.

Disse stop-kriterier er ikke valgfri. De er forsikring mod sunk cost fallacy.
