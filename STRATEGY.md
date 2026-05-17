# Polymarket Kvantitativt Tradingsystem
## Strategi og implementeringsplan

**Version:** 1.0
**Dato:** Maj 2026
**Ejer:** Christoffer
**Status:** Draft, klar til iteration i Cursor

---

## 0. Executive summary

Dette dokument beskriver opbygningen af et kvantitativt tradingsystem til Polymarket med fokus på makro-events og europæisk politik som primær vertikal. Målet er ikke at automatisere væk fra dømmekraft, men at bygge et systematisk fundament der reducerer adfærdsmæssige fejl, identificerer mispricing systematisk, og gør beslutningskvaliteten målbar over tid.

Realistisk forventning: 6-12 måneder før reel kapital allokeres med tillid. Edge er sandsynlig men ikke garanteret. Hvis paper trading efter 3 måneder ikke viser konsistent positiv forventning efter friktion, skal hele tilgangen revurderes, ikke bare strategierne.

**Kerneantagelser**

| Antagelse | Værdi | Hvornår revurderes |
|-----------|-------|--------------------|
| Bankroll fase 1 | 5.000-10.000 USD | Efter 3 måneder paper trading |
| Bankroll fase 2 (live) | 10.000-25.000 USD | Hvis paper-edge bekræftet |
| Bankroll cap | 50.000 USD | Likviditet sætter naturligt loft |
| Primær vertikal | Makro + europæisk politik | Efter 6 måneder, evt. udvide |
| Eksekvering | Signal-generation + manuel exec | Auto først efter dokumenteret edge |
| Tidsallokering | 10 timer/uge | Vedvarende minimum |
| Horisont | Minimum 24 måneder | Kortere = sandsynligvis spildt arbejde |

**Stop-kriterier**

Projektet stoppes eller pivoteres hvis:
1. Paper trading efter 12 uger viser negativt forventet afkast efter friktion
2. Live trading efter 6 måneder underperformer paper trading materielt (over 30 procent gap)
3. Realiseret max drawdown overstiger 25 procent af bankroll
4. Regulatoriske ændringer gør Polymarket utilgængelig fra Danmark

---

## 1. Edge-hypotese og rationale

### 1.1 Hvorfor edge er mulig på Polymarket

Tre strukturelle forhold gør Polymarket interessant for en seriøs privat aktør:

**Likviditetsfragmentering.** Store markeder (US-valg, Fed-beslutninger med høj coverage) er overraskende effektive. Likviditeten falder hurtigt for mellemstore markeder. Det betyder mispricing på 2-10 procentpoint kan eksistere i dage eller uger uden at blive arbitrageret væk, fordi der ikke er nok kapital til at flytte alle markeder samtidigt.

**Systematiske bettor-biases.** Akademisk litteratur på sportsbetting og prediction markets dokumenterer konsistente biases: favorit-longshot bias, recency bias efter store nyheder, narrative-driven mispricing, og home bias (US-fokuserede traders mispricer non-US events). Disse biases er stabile over tid fordi de er menneskelige, ikke strategiske.

**Begrænset institutionel kapital.** I modsætning til aktier og optioner er Polymarket ikke fyldt med kvant-fonde. Reguleringsmæssige restriktioner blokerer US-residents, og markedsstørrelse gør det uinteressant for større fonde. Konkurrencen er informerede privatpersoner og mindre dedikerede grupper, ikke Renaissance.

### 1.2 Hvorfor edge er sværere end det lyder

**Resolution risk.** UMA-oracle systemet kan resolve markeder på måder der overrasker. Det er en strukturel risiko der ikke kan modelleres væk og som skal indgå i edge-beregningen.

**Friktion æder edge.** Markets-makers tager 1-3 procent spread, plus gas på Polygon-netværket. Strategier skal have edge større end den friktion før de er handlebare.

**Adverse selection.** Hvis du kan handle på en pris, kan andre også. De markeder hvor du ser klarest mispricing er ofte hvor du har mindst information sammenlignet med modparten.

**Drift i bettor-population.** Mediedækning og virale momenter ændrer hvem der handler. En strategi der virkede i Q1 kan dø i Q2 fordi populationen skiftede.

### 1.3 Edge-kilder for dig specifikt

Asymmetrisk fordel for dig versus typisk Polymarket-bettor:

**Finansiel baggrund.** Forståelse af options-prissætning, probabilistisk tænkning, base rates, og Bayesian opdatering. De fleste bettors tænker narrativt, ikke probabilistisk.

**Makro-fluency.** Du kan læse FOMC-statements, ECB-pressekonferencer, og økonomiske data uden friktion. Det er en faktisk informationsedge versus general-purpose bettors.

**Europæisk perspektiv.** Polymarket er US-domineret. Europæiske politiske events (valg, ECB, EU-beslutninger) er systematisk mispriced fordi US-bettors mangler kontekst.

**Disciplineret tilgang.** Hvis systemet bygges ordentligt og du følger det, undgår du de adfærdsmæssige fejl der spiser de fleste bettors edge (FOMO, sunk cost fallacy, overtrading).

---

## 2. Marked- og konkurrentanalyse

### 2.1 Platforme

| Platform | Likviditet | Fokus | Tilgængelig fra DK |
|----------|-----------|-------|---------------------|
| Polymarket | Højeste | Bredt, US-skæv | Ja (verificér) |
| Kalshi | Mellem | US-regulert, smal | Nej (US-only) |
| Manifold | Lav | Play money + real money | Ja |
| PredictIt | Lav | US-politik | Begrænset |
| Limitless | Lav | Crypto-native, voksende | Ja |

Polymarket er primær platform. Andre overvåges for cross-market arbitrage og som datakilde til prissammenligning.

### 2.2 Konkurrenter (andre systematiske aktører)

**Domus.fi, Polymarket Analytics, Polysights.** Eksisterende dashboards der viser likviditet, odds-bevægelser og volume. Bruges af mange bettors men giver ikke signaler eller edge. Konkurrence på "data visualization" er tabt.

**Domain-specifikke specialister.** Anonyme bettors med dyb edge på specifikke vertikaler (US-politik, sport, crypto-events). De handler aggressivt og er din primære konkurrence i deres niche. Undgå deres territorier.

**Arbitrageurs.** Aktører der cross-market arbitragerer mellem Polymarket og andre platforme. Ofte ren ren arbitrage er væk inden for minutter, men statistisk arbitrage holder længere.

**General retail.** Sentiment-drevne handlende, FOMO-traders, fan-bettors. Det er disse du vinder fra over tid, ikke fra specialisterne.

### 2.3 Markedsstørrelse og kapacitet

Aktive markeder på Polymarket: typisk 100-300 likvide markeder samtidigt. Total daglig volume varierer fra 5-100 mio USD afhængig af events.

Realistisk kapacitet for én strategi: 50-500 USD per position i niche-markeder, 1.000-10.000 USD i likvide markeder uden at flytte prisen mere end 1 procent. Det er din primære skalerings-constraint.

---

## 3. System-arkitektur

### 3.1 Arkitektur-overblik

```
[Polymarket API] ──┐
[Kalshi API]   ────┼──> [Data ingestion] ──> [PostgreSQL]
[News feeds]   ────┘                              │
                                                  │
                                                  ▼
[Manuel input] ────────────────────────────> [Strategy engine]
                                                  │
                                                  ▼
                                          [Signal generation]
                                                  │
                                                  ▼
                                     [Risk + sizing engine]
                                                  │
                                                  ▼
                                          [Trade dashboard]
                                                  │
                                                  ▼
                                       Manuel eksekvering
                                                  │
                                                  ▼
                                          [Position tracker]
                                                  │
                                                  ▼
                                        [Performance log]
```

### 3.2 Tech stack

Holdt simpelt og pragmatisk. Mål er hurtigt at få noget der virker, ikke arkitektonisk renhed.

**Backend:** Python 3.11+, FastAPI for evt. interne endpoints, asyncio for parallel data-fetch.

**Data storage:** PostgreSQL for produktion (timeseries-data, markets, positions). SQLite for prototyping. TimescaleDB-extension hvis volumen vokser.

**Data libraries:** httpx for async HTTP, pandas + polars for analyse, numpy + scipy for statistik, requests for synkrone calls.

**Backtesting:** Custom rammeværk i Python. Vector-baseret hvor muligt. Ingen brug af færdige biblioteker som backtrader eller zipline, fordi prediction markets ikke ligner aktier nok.

**Frontend / dashboard:** Streamlit til version 1. Hurtigt at bygge, godt til personligt brug. Skift til Next.js eller React kun hvis produktet skal sælges.

**Hosting:** Railway, Render eller Fly.io. Start med single-node setup, omkring 20-50 USD/md.

**Eksekvering:** Manuel via Polymarket UI i fase 1. Polymarket CLOB API til auto-eksekvering i senere fase.

**Notifications:** Telegram bot for alerts om signaler og positionsændringer. Simpelt og pålideligt.

### 3.3 Datamodel (PostgreSQL)

Kernetabeller:

`markets` - alle Polymarket-markeder med metadata
`market_snapshots` - tidsserier af odds, volume, likviditet (hver 5-15 min)
`market_trades` - faktiske handler fra orderbook hvis tilgængelige
`base_rates` - manuel og automatisk database over historiske sandsynligheder
`signals` - genererede handelssignaler med metadata
`positions` - aktive og historiske positioner
`trades` - eksekverede handler med priser, gebyrer, slippage
`decisions_journal` - struktureret journal for hver position med tese, edge-kilde, exit-kriterier
`performance` - daglig PnL, drawdown, win rate, edge realisation

---

## 4. Data-pipeline

### 4.1 Polymarket API

Polymarket eksponerer to primære interfaces:

**Gamma API** for markedsdata, metadata, og priser. REST-baseret, ingen authentication krævet for read-only data. Rate limits er overkommelige til polling hver 5-15 min.

**CLOB API** for orderbook-data og handelseksekvering. Kræver wallet-signing for eksekvering, men read-only adgang til orderbook er åbent.

Verificér aktuelle endpoints og rate limits på `docs.polymarket.com` før implementering, fordi de ændrer sig løbende.

### 4.2 Ingestion-jobs

| Job | Frekvens | Indhold |
|-----|----------|---------|
| Market discovery | Hver time | Find nye markeder, opdater metadata |
| Price snapshot | Hver 5 min for aktive, hver 30 min for thin | Odds, volume, likviditet |
| Orderbook depth | Hver 15 min for fokus-markeder | Bid/ask spread, depth |
| Resolution check | Hver dag | Fang nyligt afgjorte markeder |
| Cross-platform sync | Hver 30 min | Sammenlign med Kalshi/Manifold hvor relevant |

### 4.3 Eksterne data-kilder

**Politisk/makro:**
- FRED (Federal Reserve Economic Data) - gratis, dækker US-makro
- Eurostat API - gratis, dækker EU-makro
- ECB Statistical Data Warehouse - gratis
- Danmarks Statistik API - gratis
- Polymarket-specifikke kilder: PolitiFact, RealClearPolitics polling-aggregater

**News flow:**
- RSS-aggregator over Reuters, Bloomberg politics, FT, Politico, Axios
- Twitter/X firehose (kræver API-adgang, 200 USD/md for basic) for breaking-news detection
- Google News API som fallback

**Cross-checks:**
- Manifold Markets API for "wisdom of crowds" sammenligning
- Metaculus for langsigtede forecasts

---

## 5. Strategi-bibliotek

Fire konkrete strategier at starte med. Hver strategi har klar hypotese, eksplicitte entry/exit-kriterier, og målbar edge-kilde. Hvis en strategi ikke kan formuleres så skarpt, bygges den ikke.

### 5.1 Strategi A: Base rate fade

**Operativ dokumentation (v0):** [docs/strategies/base_rate_fade.md](docs/strategies/base_rate_fade.md) — parametre, afvisningsregler og uge 6-review.

**Hypotese:** Polymarket overreagerer på nylige nyheder og priser markeder længere fra historiske base rates end fundamentet retfærdiggør. Mean-reversion mod base rate over 2-14 dage.

**Edge-kilde:** Behavioral. Recency bias og narrative-driven mispricing.

**Marked-type:** Politiske og makro-events med klare historiske base rates.

**Entry:** Marked priser begivenhed mere end 15 procentpoint væk fra base rate, og base rate er etableret på minimum 10 historiske observationer.

**Exit:** Marked nærmer sig base rate inden for 5 procentpoint, eller fundamental information ændrer base rate-estimatet, eller 30 dage uden bevægelse.

**Position size:** 1-3 procent af bankroll per position.

**Forventet edge:** 3-8 procent per trade efter friktion, hit rate 55-65 procent.

### 5.2 Strategi B: Likviditet-screen for stale prices

**Hypotese:** Thin liquidity markeder bevæger sig langsomt på nye informationer fordi der ikke er nok markeds-deltagere. Hurtig informationsindsamling giver edge i de første 2-12 timer efter relevant nyhed.

**Edge-kilde:** Informational + speed.

**Marked-type:** Niche-events, europæiske politiske begivenheder, makro-events uden for prime trading hours.

**Entry:** Triggeret af news-detection system. Marked har ikke bevæget sig markant (mindre end 5 procentpoint) efter relevant nyhed identificeret minimum 1 time tidligere.

**Exit:** Pris bevæger sig 50-80 procent af forventet justering, eller efter 48 timer.

**Position size:** 0,5-2 procent af bankroll. Mindre fordi exit-likviditet er begrænset.

**Forventet edge:** 5-15 procent per trade når den udløses. Lav frekvens (5-15 trades/måned).

### 5.3 Strategi C: Cross-market konsistens

**Hypotese:** Logisk relaterede markeder på Polymarket eller på tværs af platforme er ikke altid internt konsistente. Når priser brydes med matematik (P(A) + P(not A) > 1, eller P(A og B) > P(A)), eksisterer der ren eller statistisk arbitrage.

**Edge-kilde:** Strukturel. Ren matematik, ingen forudsigelse krævet.

**Marked-type:** Multi-leg events, conditional markets, samme event på flere platforme.

**Entry:** Pris-inkonsistens over 3 procentpoint efter friktion.

**Exit:** Konsistens genoprettet eller markeder resolverer.

**Position size:** Op til 5 procent af bankroll fordi risiko er lavere.

**Forventet edge:** 2-5 procent per trade efter friktion. Lav frekvens men høj sandsynlighed.

### 5.4 Strategi D: Volatility crush før resolution

**Hypotese:** Markeder med uger til resolution ofte ikke fuldt indpriser tidsdiskontering og volatilitet. Specifikke positioner kan tages for at fange tidsforfald lignende options theta.

**Edge-kilde:** Strukturel + behavioral.

**Marked-type:** Markeder hvor en hændelse er højst sandsynlig (P > 90 eller P < 10) men prises langt fra extreme.

**Entry:** Fundamentalt højkonfidens estimat (over 90 procent eller under 10 procent) men marked priser i 75-90 procent eller 10-25 procent range, og resolution er inden for 30 dage.

**Exit:** Pris konvergerer mod fundamentalt estimat, eller fundamental ændres.

**Position size:** 1-2 procent af bankroll.

**Forventet edge:** Moderat (3-7 procent) men konsistent hvis kalibrering er ordentlig.

### 5.5 Strategi-uafhængige regler

For alle strategier gælder:

Ingen position før eksplicit pre-trade tjekliste udfyldes i decisions journal.

Ingen position over 5 procent af bankroll uanset edge-estimat.

Ingen samlet eksponering over 30 procent af bankroll mod én korreleret begivenhed (alle Trump-relaterede markeder tæller som én korreleret position).

Stopper trading i en strategi efter 3 konsekutive negative måneder, indtil årsag er forstået.

---

## 6. Backtesting-metodologi

### 6.1 Princip

Backtesting på prediction markets er sværere end på aktier fordi:

Markedet er ungt (Polymarket meningsfuld likviditet kun siden 2023-2024)
Historiske orderbook-data er svære at få
Resolutions er hændelses-specifikke, ikke kontinuerlige
Survivorship bias er reel (mange markeder lukkes uden resolution)

Det betyder backtest skal være konservativ. Forvent at live performance er 30-50 procent dårligere end backtest pga ovenstående.

### 6.2 Walk-forward design

Periode opdeles i:

`In-sample` (training): bruges til strategi-formulering og parameter-valg
`Out-of-sample` (validation): bruges til at validere strategi efter formulering
`Holdout`: rør ikke før strategien er færdigformuleret

Eksempel split: 2023 Q1-Q3 in-sample, 2023 Q4 - 2024 Q2 out-of-sample, 2024 Q3 - 2025 holdout.

### 6.3 Realistiske friktion-antagelser

| Friktion | Antagelse | Note |
|----------|-----------|------|
| Bid-ask spread | 1-3% | Konservativt, antag du tager spread |
| Slippage | 0,5-2% | Større i thin liquidity |
| Gas fees | 0,1-0,5 USD per trade | Polygon network |
| Resolution disputes | 2-5% af forventet edge | Forsikring mod oracle-risk |
| Total friction | 3-7% per round trip | Realistisk for fase 1 |

### 6.4 Statistisk signifikans

For at konkludere edge er reel kræves:

Minimum 30 trades per strategi før konklusioner
Sharpe ratio over 1.0 efter friktion (over 1.5 hvis lav frekvens)
Eksplicit hypotese-test med p-værdi under 0.05 (ikke fishing)
Sanity check: kan edge forklares af lookahead bias, survivorship, eller cherry-picking

Vær brutal her. De fleste backtests viser falsk edge fordi metodologien er sloppy.

---

## 7. Risk management

### 7.1 Tre niveauer af risiko

**Position-niveau:** Maks 5 procent af bankroll per position. Mindre i thin markets (1-2 procent).

**Korrelations-niveau:** Maks 30 procent af bankroll mod én underliggende begivenhed eller stærkt korrelerede begivenheder. Klassifikation manuelt, ikke automatisk.

**Portefølje-niveau:** Maks 60 procent allokeret samtidigt. Resten er tørt krudt for nye muligheder.

### 7.2 Drawdown-regler

| Drawdown fra peak | Handling |
|-------------------|----------|
| 10% | Review notater, identificer fejl |
| 15% | Reducer position sizes med 50% |
| 20% | Stop nye positioner, kun lukning |
| 25% | Hård stop, fuld revurdering |

Drawdown-regler er ikke valgfri. De er den vigtigste del af systemet fordi de begrænser fatal risk når strategi-edge midlertidigt forsvinder.

### 7.3 Resolution-risk håndtering

Læs UMA oracle-dokumentation og kig på historiske disputes før hver position. Visse markeder har strukturel resolution-risk (vagt formulerede betingelser, kontroversielle outcomes). Disse undgås uanset edge-estimat.

Allokér maksimalt 10 procent af bankroll mod markeder der resolveres inden for samme 7-dages vindue. Det beskytter mod systemic oracle-fejl.

### 7.4 Operationel risk

Wallet-sikkerhed: brug dedicated hardware wallet eller separat hot wallet med kun aktiv kapital. Aldrig hele bankroll i hot wallet.

Backup af signal-historik og positioner ud over Polymarket selv. Hvis platformen går ned permanent, skal du have egen record.

Skat: track alle trades og resolutions for skatteregnskab. Konsultér revisor om dansk skattebehandling før første live trade.

---

## 8. Position sizing

### 8.1 Modificeret Kelly

Klassisk Kelly criterion overestimerer optimal size pga model-usikkerhed. Brug fractional Kelly med fraction = 0.25 (kvart-Kelly).

Formula for binary outcome:

```
f* = (b*p - q) / b
hvor:
  f* = fraction af bankroll
  b = nettoodds (payout / risk)
  p = sandsynlighed for win
  q = 1 - p

Anvendt size = max(0, min(0.25 * f*, 0.05))
```

5 procent cap uanset Kelly-output. Det er hård regel.

### 8.2 Edge-justering

Hvis edge-estimat er over 10 procentpoint, brug fuld kvart-Kelly. Hvis edge er 5-10 procentpoint, halver. Hvis under 5 procent, handl ikke (efter friktion er edge for lille).

### 8.3 Likviditet-justering

Position size må ikke flytte prisen mere end 1 procent. Tjek orderbook depth før hver entry. Hvis fuld position kræver flere fills over timer, accepter mindre position frem for at jage likviditet.

---

## 9. Eksekverings-workflow

### 9.1 Daglig rutine (estimeret 1-2 timer/dag aktiv)

**Morgen (30 min):**
Tjek dashboard for nye signaler.
Læs nyheds-aggregator for relevante events.
Opdater base rates hvis nye data.

**Midt på dagen (15-30 min):**
Tjek aktive positioner mod exit-kriterier.
Vurder nye signaler genereret af strategi-engine.
Eksekver eventuelle entries eller exits manuelt.

**Aften (30 min):**
Log dagens trades i decision journal.
Review eventuelle resolutions.
Opdater performance-tabel.

### 9.2 Pre-trade tjekliste (gennemgås før hver position)

1. Hvilken strategi udløser dette signal?
2. Hvad er min eksplicitte edge-tese i én sætning?
3. Hvad er base rate-estimat og min konkrete sandsynlighedsvurdering?
4. Hvad er forventet edge i procentpoint efter friktion?
5. Hvad er position size baseret på Kelly + cap + likviditet?
6. Hvad er eksplicit exit-kriterium (pris, tid, eller event)?
7. Hvilke scenarier får mig til at lukke positionen før exit-kriterium?
8. Hvad er den stærkeste counter-argument mod min tese?
9. Hvilken bias kunne forklare hvorfor jeg ser edge her?
10. Hvis denne handel taber maksimalt, hvad er PnL-impact?

Hvis nogen af de 10 spørgsmål ikke kan besvares præcist, handles der ikke.

### 9.3 Post-trade journal

Hver position dokumenteres ved entry og ved exit. Ved exit også:

Var udfaldet i overensstemmelse med tesen?
Hvis ikke, var jeg uheldig eller var tesen forkert?
Hvad ville jeg gøre anderledes næste gang?
Var min sandsynlighedsvurdering kalibreret (sammenlign med base rate over tid)?

Journal review hver 4. uge for at identificere mønstre i fejl.

---

## 10. KPI'er og evaluering

### 10.1 Performance-metrics

| Metric | Mål fase 1 (paper) | Mål fase 2 (live) | Threshold |
|--------|--------------------|--------------------|-----------|
| Hit rate | >55% | >55% | <50% over 50 trades = problem |
| Average edge realiseret | >3% | >2% efter friktion | Negativt = stop |
| Sharpe ratio | >1.0 | >1.0 | <0.5 = revurder |
| Max drawdown | <20% | <20% | >25% = hård stop |
| Calibration error | <10% | <10% | Mål: predicted P matcher realiseret P |
| Trades per måned | 10-30 | 10-30 | <5 = ikke nok signal |

### 10.2 Kalibrerings-test

Hver måned: tag alle positioner hvor du estimerede P = 0.7. Hvor stor andel resolved positivt? Hvis tæt på 70 procent, er du kalibreret. Hvis under 60 procent, er du systematisk overconfident. Hvis over 80 procent, er du systematisk underconfident og lader edge ligge.

Kalibrering er vigtigere end hit rate. En velkalibreret estimator med 55 procent hit rate er værdifuld. En miskalibreret estimator med 65 procent hit rate er ikke.

### 10.3 Strategi-specifik review

Hver strategi reviewes individuelt hver 8. uge:

Genererer den signaler i forventet frekvens?
Er edge-estimat kalibreret mod realiseret performance?
Er der ændringer i markedstruktur der dræber edgen?
Skal parametre justeres, eller skal strategien pensioneres?

---

## 11. 12-ugers faseplan

### Uge 1-2: Setup og data-pipeline

Setup projekt-repo i Cursor med Python + PostgreSQL.
Implementer Polymarket Gamma API integration.
Bygge market discovery + snapshot jobs.
Setup database-schema for markets og snapshots.
Mål: Database med løbende opdatering af alle aktive markeder.

### Uge 3-4: Manuel research og første handler

Brug 20+ timer på Polymarket selv. Handl med 50-200 USD positioner.
Tag noter om markedsdynamik, friktion, orderbook adfærd.
Identificer 2-3 vertikaler hvor du føler intuitiv edge.
Mål: Dyb forståelse af markedets mekanik fra hands-on erfaring.

### Uge 5-6: Base rate database og første strategi

Byg base rate database for makro-events (Fed-beslutninger, GDP-prints, inflation prints, ECB-møder).
Implementer strategi A (base rate fade) som første konkrete strategi.
Setup signal-generation pipeline.
Mål: Første automatiserede signaler genereret dagligt.

### Uge 7-8: Backtesting-framework og strategi B

Byg backtesting-engine med walk-forward design.
Backtest strategi A på historisk data (2024).
Implementer strategi B (likviditet-screen).
Mål: Begge strategier backtestede, dokumenteret historisk performance.

### Uge 9-10: Dashboard og risk-system

Byg Streamlit dashboard for live signaler og positioner.
Implementer position sizing og risk-checks i kode.
Setup Telegram-alerts for signaler.
Implementer decision journal-flow.
Mål: Komplet workflow fra signal til journal.

### Uge 11-12: Strategi C, D og paper trading

Implementer strategi C (cross-market) og D (volatility crush).
Start systematisk paper trading af alle 4 strategier.
Track alle signaler og hypotetiske entries/exits.
Mål: 4 strategier kører paper i systematisk format, klar til 3 måneders paper trading-fase.

### Måned 4-6: Paper trading-fase

Fortsæt paper trading med alle 4 strategier.
Månedlige reviews af performance, kalibrering, og edge-realisering.
Iterér på strategier baseret på data.
Beslutning efter 12 uger paper: går nogle strategier live, eller stop.

### Måned 7+: Live trading (hvis paper validerer edge)

Start med 25 procent af planlagt bankroll.
Skaler op gradvis hvis live performance matcher paper.
Fortsæt journal, reviews, og kalibrerings-tests.

---

## 12. Risici og mitigation

### 12.1 Strategiske risici

**Overfitting i backtest.** Det største problem ved kvant-systemer. Mitigation: walk-forward validation, holdout-data, eksplicitte hypoteser formuleret før test, brutal ærlighed om edge-kilde.

**Edge-erosion over tid.** Markeder bliver mere effektive. Mitigation: løbende monitorering af edge-realisering, villighed til at pensionere strategier, dyb specialisering i niche-vertikaler.

**Behavioral drift hos dig selv.** Selv med systemet er der fristelse til at handle off-system. Mitigation: hård regel om at off-system trades trackes separat så du kan måle om de underpresterer (de gør altid).

### 12.2 Operationelle risici

**Platform-risk.** Polymarket kan blokere danske brugere, regulatoriske ændringer kan ramme. Mitigation: hold ikke mere end nødvendigt på platformen, brug egen wallet-custody hvor muligt, monitorer regulatorisk landskab.

**Oracle/resolution-risk.** UMA disputes kan koste penge. Mitigation: undgå vagt formulerede markeder, diversifér resolutions over tid, allokér ikke for meget mod én resolution-dato.

**Tech-risk.** Bugs i system kan generere falske signaler eller misse entries. Mitigation: alle trades manuel-confirmeret i fase 1, automatiseret kun efter dokumenteret track record.

### 12.3 Personlige risici

**Tid-commitment underskydes.** 10 timer/uge i 24 måneder er reel commitment. Hvis det skrider, dør systemet. Mitigation: gør tiden non-negotiable i kalender, monitorer hvor mange timer faktisk bruges.

**Tabsstrækninger demoraliserer.** Selv velbyggede systemer har drawdown-perioder på 20+ procent. Mitigation: forvent dem, præ-commit til drawdown-regler, læs Howard Marks' memos om random walks under tabstider.

**Confirmation bias om edge.** Du vil gerne tro systemet virker. Mitigation: brutal kalibrerings-test, ekstern accountability (skriv om performance offentligt, eller del med en betroet sparringspartner), villighed til at stoppe hvis data siger stop.

### 12.4 Regulatoriske og skattemæssige risici

**Dansk skatteforhold uklart.** Gevinster fra Polymarket kan klassificeres som spilgevinster, kapitalindkomst, eller næringsindkomst afhængig af aktivitetsniveau og hensigt. Konsultér revisor før første live-trade.

**EU regulering af crypto-prediction markets.** MiCA og lignende rammeværk udvikler sig. Monitorer.

**Polymarkets adgang fra Danmark.** Verificér løbende at brug er tilladt og overhold KYC/AML hvor relevant.

---

## 13. Næste skridt

### 13.1 Umiddelbart (denne uge)

1. Setup Polymarket-konto hvis ikke allerede. Lav 3-5 små test-handler (10-50 USD) for at forstå UX, fees og resolution-flow.
2. Setup Python-projekt i Cursor med struktur klar til implementation.
3. Verificér adgang til Polymarket Gamma API ved at lave første kald.
4. Konsultér revisor om skatteforhold for Polymarket-gevinster i Danmark.

### 13.2 Næste 2 uger

5. Implementer market discovery og snapshot pipeline (uge 1-2 plan).
6. Læs Polymarket-dokumentation grundigt og note begrænsninger.
7. Læs 3-5 akademiske papers om prediction markets og bettor-biases (forslag: Wolfers og Zitzewitz "Prediction Markets" Journal of Economic Perspectives 2004, og nyere papers om Polymarket specifikt).

### 13.3 Beslutninger der skal tages snart

Hvilken niche-vertikal vil du gå dybt på først? Forslag: makro-events (Fed, ECB, inflation prints) som primær, europæiske politiske events som sekundær.

Vil dette projekt være privat eller har du intention om at dele performance offentligt? Offentlig accountability har psykologisk værdi men også risici.

Hvad er smerte-pointen hvor du stopper? Skriv det ned nu, ikke når du er i drawdown.

---

## Appendix A: Anbefalet læsning

- *Thinking in Bets* af Annie Duke (decision-making under usikkerhed)
- *Superforecasting* af Philip Tetlock (kalibrering og forecasting)
- *The Signal and the Noise* af Nate Silver (probabilistisk tænkning)
- *Fortune's Formula* af William Poundstone (Kelly criterion historie)
- Wolfers og Zitzewitz "Prediction Markets" JEP 2004 (akademisk fundament)
- Howard Marks memos (mental modeller om markedscykler og risiko)

## Appendix B: Cursor-specifikke instruktioner

Når du arbejder med dette i Cursor, hold dokumentet som `STRATEGY.md` i repo-root. Brug det som kontekst i Cursor-chats ved at @-referere til det. Opdater løbende efterhånden som strategier itereres.

Lav også separate filer:
- `IMPLEMENTATION.md` for tekniske beslutninger og kode-struktur
- `JOURNAL.md` for løbende trading-noter og refleksioner
- `PERFORMANCE.md` for månedlige performance-reviews

Skift mellem dem efter behov, og lad Cursor have alle som kontekst når der ændres strategi-kode.
