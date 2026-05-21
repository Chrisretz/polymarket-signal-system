# Arkiveret backtest-baseline (Strategi A)

**Arkiveret:** maj 2026  
**Kontekst:** Uge 7 walk-forward backtest af `base_rate_fade` mod macro/eu_politics-markeder.

## Hvorfor arkiveret

- Classifier/templates matchede ~70% af markeder forkert (inflation/GDP-brackets m.fl.).
- Fase 2 templates (kun Fed/ECB meeting hold) var teknisk korrekte, men fair value-modellen (FRED 3M-proxy + Gaussisk kerne) gav absurde signaler vs. velinformerede CB-markeder.
- Strategi A er permanent frosset; projektet pivoterer til **Strategi C** (cross-market konsistens).

## Indhold

- `backtest_week7_trades.csv` — rå simulerede trades fra den ugyldige baseline (pre-template scope).

## Brug

Kun historisk reference. **Kør ikke** som grundlag for beslutninger eller ny backtest uden at læse CLEANUP.md og STRATEGY.md.
