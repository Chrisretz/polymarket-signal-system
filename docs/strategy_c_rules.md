# Polymarket Probability Inconsistency Scanner  
## Recommended Rules for Retail Edge Detection

This document defines a practical rule set for detecting internal probability inconsistencies across Polymarket markets.  
The focus is **internal Polymarket-only arbitrage / relative-value logic**, without using external data sources such as FedWatch, prediction models, betting odds, or macro data.

Priorities are assigned based on two criteria:

1. **Potential retail edge**: likelihood that the rule can identify tradable mispricings not instantly captured by professional bots.
2. **Automation feasibility**: how easily the rule can be coded, tested, and scaled across markets.

Priority scale:

- **High**: build first. Strong combination of edge potential and automation feasibility.
- **Medium**: useful, but requires more careful semantic matching or has more false positives.
- **Low**: relevant, but either harder to automate, lower edge, or higher resolution/interpretation risk.

---

## 1. Later deadline must be greater than or equal to earlier deadline

**Priority:** High

### Rule

If the same event can happen before two different deadlines, the later deadline must have at least the same probability as the earlier deadline.

```text
P(Event happens by later date) >= P(Event happens by earlier date)
```

### Example

```text
Fed cuts by June: 35%
Fed cuts by September: 31%
```

This is inconsistent. If the event happens by June, it has also happened by September.

### Trade logic

```text
If P(later) < P(earlier):
    Buy YES on later event
    Optionally short / buy NO on earlier event if executable
```

### Why this matters

This is one of the best rules to build first. It is logically clean, common across markets, and relatively easy to automate when market titles contain dates or deadlines.

### Automation difficulty

Medium. Requires reliable parsing of dates and identifying that two markets refer to the same underlying event.

---

## 2. Earlier NO must be greater than or equal to later NO

**Priority:** High

### Rule

For the inverse of a deadline event:

```text
P(No event by earlier date) >= P(No event by later date)
```

### Example

```text
No Fed cut by June: 55%
No Fed cut by September: 62%
```

This is inconsistent. It should be easier for no event to happen by June than by September.

### Trade logic

```text
If P(No later) > P(No earlier):
    Buy NO-equivalent on earlier event
    Or buy YES-equivalent on later event, depending on market structure
```

### Why this matters

This catches the inverse version of deadline inconsistencies and can identify opportunities missed by scanners that only look at YES probabilities.

### Automation difficulty

Medium. Requires correct interpretation of YES/NO semantics.

---

## 3. Higher threshold must be less than or equal to lower threshold

**Priority:** High

### Rule

For “above”, “at least”, “greater than”, or “over” markets:

```text
P(X >= high threshold) <= P(X >= low threshold)
```

### Example

```text
Bitcoin above $200k in 2026: 28%
Bitcoin above $150k in 2026: 22%
```

This is inconsistent. If Bitcoin exceeds $200k, it necessarily exceeds $150k.

### Trade logic

```text
If P(high threshold) > P(low threshold):
    Buy YES on lower threshold
    Optionally buy NO / short YES on higher threshold
```

### Why this matters

This is one of the most automatable and robust rules. Threshold markets are common in crypto, sports, macro, elections, viewership, revenue, app rankings, and other measurable categories.

### Automation difficulty

Medium. Requires parsing numerical thresholds and ensuring the measurement period/source is the same.

---

## 4. Lower “below” threshold must be less than or equal to higher “below” threshold

**Priority:** High

### Rule

For “below”, “under”, or “less than” markets:

```text
P(X <= low threshold) <= P(X <= high threshold)
```

### Example

```text
S&P 500 below 4,000: 30%
S&P 500 below 4,500: 24%
```

This is inconsistent. If S&P 500 is below 4,000, it is also below 4,500.

### Trade logic

```text
If P(below lower threshold) > P(below higher threshold):
    Buy YES on higher threshold
    Optionally buy NO / short YES on lower threshold
```

### Why this matters

This is the inverse of the “higher threshold” rule and is highly relevant across finance, crypto, sports, politics, and economic data-style markets.

### Automation difficulty

Medium. Requires parsing thresholds and confirming identical measurement dates and sources.

---

## 5. Sub-event must be less than or equal to parent event

**Priority:** High

### Rule

If event A can only happen if event B also happens, then:

```text
If A implies B:
    P(A) <= P(B)
```

### Example

```text
Team wins championship: 38%
Team reaches final: 32%
```

This is inconsistent. A team cannot win a championship without reaching the final.

### Other examples

```text
Candidate wins election <= Candidate wins nomination
Company IPOs in 2026 <= Company IPOs by 2027
Bitcoin above $200k by Dec 31 <= Bitcoin above $100k by Dec 31
```

### Trade logic

```text
If P(sub-event) > P(parent event):
    Buy YES on parent event
    Optionally buy NO / short YES on sub-event
```

### Why this matters

This rule has strong edge potential because it captures “second-order” inconsistencies that simple sum-to-100 arbitrage scanners may miss.

### Automation difficulty

Medium to High. Requires building or inferring logical event hierarchies.

---

## 6. Count thresholds must be monotonic

**Priority:** High

### Rule

For count-based events:

```text
P(Number >= 3) <= P(Number >= 2) <= P(Number >= 1)
```

and:

```text
P(Number <= 1) <= P(Number <= 2) <= P(Number <= 3)
```

### Example

```text
At least 3 rate cuts: 40%
At least 2 rate cuts: 35%
```

This is inconsistent.

### Trade logic

```text
If higher count threshold has higher probability than lower count threshold:
    Buy YES on lower threshold
    Optionally buy NO / short YES on higher threshold
```

### Why this matters

This is highly useful because count markets are common and often fragmented across multiple Polymarket markets.

### Automation difficulty

Medium. Requires parsing “at least”, “more than”, “fewer than”, “exactly”, etc.

---

## 7. Exact count can be derived from cumulative count probabilities

**Priority:** High

### Rule

If cumulative probabilities are available:

```text
P(exactly 1) = P(>=1) - P(>=2)
P(exactly 2) = P(>=2) - P(>=3)
```

Any negative implied exact probability indicates inconsistency.

### Example

```text
P(>=1 rate cut) = 50%
P(>=2 rate cuts) = 55%
```

This implies:

```text
P(exactly 1 cut) = -5%
```

That is impossible.

### Trade logic

```text
If P(>=n+1) > P(>=n):
    Buy YES on >=n
    Optionally buy NO / short YES on >=n+1
```

### Why this matters

This is a strong systematic rule for structured markets where multiple thresholds exist.

### Automation difficulty

Medium.

---

## 8. Exhaustive mutually exclusive outcomes must sum to approximately 100%

**Priority:** Medium to High

### Rule

If one and only one outcome can happen, and all possible outcomes are included:

```text
P(A) + P(B) + P(C) + ... ~= 100%
```

### Example

```text
Candidate A wins: 40%
Candidate B wins: 35%
Candidate C wins: 20%

Sum = 95%
```

If these are exhaustive, buying all YES outcomes theoretically locks a 5% gross profit before spread and fees.

### Trade logic

```text
If sum of executable YES asks < 100%:
    Buy all YES outcomes

If sum of executable YES bids > 100%:
    Sell all YES outcomes / buy all NO equivalents, if possible
```

### Why this matters

This is the classic arbitrage rule. It is easy to understand and can be profitable when available.

### Why not always High?

Simple underround/overround opportunities are likely to be heavily competed by bots. Retail edge is still possible, especially in smaller or poorly linked markets, but the obvious opportunities may disappear quickly.

### Automation difficulty

Medium. Requires correctly identifying complete outcome sets.

---

## 9. Binary market internal sanity check

**Priority:** Medium to High

### Rule

Within a single binary market:

```text
YES ask + NO ask >= 100%
YES bid + NO bid <= 100%
```

### Example

```text
YES ask = 46%
NO ask = 51%

Total = 97%
```

In theory, buying both sides locks a gross arbitrage.

### Trade logic

```text
If YES ask + NO ask < 100%:
    Buy YES and NO

If YES bid + NO bid > 100%:
    Sell YES and NO, if possible
```

### Why this matters

This is highly automatable and very clean logically.

### Why not always High?

These opportunities are usually very short-lived and likely to be competed away quickly.

### Automation difficulty

Low.

---

## 10. “At least one” must be greater than or equal to each component

**Priority:** Medium

### Rule

For union events:

```text
P(A or B or C) >= max(P(A), P(B), P(C))
```

### Example

```text
Trump or Vance nominee: 45%
Trump nominee: 52%
```

This is inconsistent.

### Trade logic

```text
If P(A or B) < P(A):
    Buy YES on A or B
    Optionally buy NO / short YES on A
```

### Why this matters

Useful for political, sports, corporate, and “which of these will happen” style markets.

### Automation difficulty

High. Requires semantic matching of component events and combined events.

---

## 11. “All happen” must be less than or equal to each component

**Priority:** Medium

### Rule

For intersection events:

```text
P(A and B and C) <= min(P(A), P(B), P(C))
```

### Example

```text
Fed cuts and S&P hits all-time high: 40%
Fed cuts: 35%
```

This is inconsistent.

### Trade logic

```text
If P(A and B) > P(A):
    Buy YES on A
    Optionally buy NO / short YES on A and B
```

### Why this matters

Good theoretical rule, but combined-event markets are less common and harder to parse safely.

### Automation difficulty

High.

---

## 12. Union bounds

**Priority:** Medium

### Rule

For two events A and B:

```text
max(P(A), P(B)) <= P(A or B) <= min(100%, P(A) + P(B))
```

### Example

```text
A happens: 40%
B happens: 35%
A or B happens: 30%
```

This is inconsistent because A or B must be at least 40%.

### Trade logic

```text
If P(A or B) < max(P(A), P(B)):
    Buy YES on A or B
    Optionally hedge with the overpriced single component
```

### Why this matters

Useful, but requires strong semantic matching and clean understanding of overlap.

### Automation difficulty

High.

---

## 13. Intersection bounds

**Priority:** Medium

### Rule

For two events A and B:

```text
max(0, P(A) + P(B) - 100%) <= P(A and B) <= min(P(A), P(B))
```

### Example

```text
A happens: 70%
B happens: 60%
A and B happens: 20%
```

This is inconsistent because the lower bound is:

```text
70% + 60% - 100% = 30%
```

### Trade logic

```text
If P(A and B) < lower bound:
    Buy YES on A and B
    Potentially hedge with A and B singles
```

### Why this matters

Powerful mathematically, but harder to trade in practice.

### Automation difficulty

High.

---

## 14. Exact interval decomposition

**Priority:** Medium

### Rule

If a continuous variable is split into non-overlapping, exhaustive intervals:

```text
P(X in interval A) + P(X in interval B) + P(X in interval C) + ... ~= 100%
```

### Example

```text
BTC ends 2026:
0-50k: 10%
50k-100k: 30%
100k-150k: 35%
150k+: 20%

Sum = 95%
```

If exhaustive, this is an underround.

### Trade logic

```text
If sum of executable YES asks < 100%:
    Buy all intervals

If sum of executable YES bids > 100%:
    Sell all intervals / buy NO equivalents, if possible
```

### Why this matters

Very useful for range markets, but only if all intervals are truly exhaustive and non-overlapping.

### Automation difficulty

Medium to High.

---

## 15. Duplicate / same-event price divergence

**Priority:** Medium

### Rule

Two markets resolving to the same event should trade at approximately the same probability.

```text
If Market A and Market B resolve on the same objective event:
    P(A) ~= P(B)
```

### Example

```text
“Will BTC hit $100k by Dec 31?”
vs.
“Bitcoin to reach $100,000 before 2027?”
```

If both resolve identically but trade far apart, there may be edge.

### Trade logic

```text
If Market A materially cheaper than Market B:
    Buy cheaper equivalent
    Optionally short / buy NO on expensive equivalent
```

### Why this matters

Can produce real retail opportunities because duplicate or near-duplicate markets may not be perfectly linked.

### Main risk

Resolution wording may differ in ways that matter.

### Automation difficulty

High. Requires semantic similarity matching and manual validation.

---

## 16. Candidate wins election must be less than or equal to candidate nomination

**Priority:** Medium

### Rule

Before a candidate has secured nomination:

```text
P(candidate wins election) <= P(candidate wins nomination)
```

### Example

```text
Candidate wins presidency: 22%
Candidate wins party nomination: 18%
```

This is inconsistent unless the market wording allows another route to victory.

### Trade logic

```text
If P(candidate wins election) > P(candidate nomination):
    Buy YES on nomination
    Optionally buy NO / short YES on election win
```

### Why this matters

Can be useful in political markets.

### Why not High?

It is domain-specific and can be affected by edge cases such as independent runs, party switches, replacement candidates, or ambiguous wording.

### Automation difficulty

Medium to High.

---

## 17. Party/candidate equivalence after nomination

**Priority:** Medium to Low

### Rule

If a party has exactly one confirmed nominee and the market structure is equivalent:

```text
P(candidate wins election) ~= P(party wins election)
```

### Example

```text
Democratic nominee wins presidency: 48%
Named Democratic candidate wins presidency: 44%
```

If the candidate is officially the nominee and no replacement edge case exists, these should be close.

### Trade logic

```text
Buy cheaper equivalent
Optionally hedge against more expensive equivalent
```

### Why this matters

Can be profitable around transition periods after nominations.

### Why not higher?

Resolution risk and edge cases can be substantial.

### Automation difficulty

High.

---

## 18. “Before date X” + “after date X” + “never” decomposition

**Priority:** Medium to Low

### Rule

If event timing is divided into complete buckets:

```text
P(event before X) + P(event after X) + P(event never happens) = 100%
```

### Example

```text
Company IPOs before June: 20%
Company IPOs after June: 50%
Company does not IPO: 20%

Sum = 90%
```

If exhaustive and correctly defined, this is inconsistent.

### Trade logic

```text
If sum of executable YES asks < 100%:
    Buy all exhaustive timing buckets
```

### Why this matters

Useful, but only if the buckets are genuinely exhaustive and non-overlapping.

### Automation difficulty

High.

---

## 19. Settlement source consistency

**Priority:** Low to Medium

### Rule

Markets with the same settlement source, same event, and same measurement should trade similarly.

```text
If source, date, metric, and threshold are equivalent:
    P(A) ~= P(B)
```

### Example

```text
“Will CPI YoY be above 3.0%?”
vs.
“Will inflation be 3.1% or higher?”
```

These may look similar, but the exact decimal, source, release date, and revision policy can matter.

### Trade logic

```text
Buy cheaper equivalent only after manual review
```

### Why this matters

Potentially useful, but false positives are common.

### Automation difficulty

High.

---

## 20. Mutually exclusive exact outcomes cannot sum above 100%

**Priority:** Medium

### Rule

If exact outcomes are mutually exclusive but not necessarily exhaustive:

```text
P(X = 1) + P(X = 2) + P(X = 3) + ... <= 100%
```

If they are exhaustive:

```text
Sum ~= 100%
```

### Example

```text
Number of Fed cuts:
0 cuts: 25%
1 cut: 30%
2 cuts: 28%
3+ cuts: 25%

Sum = 108%
```

This is inconsistent if the outcome set is complete.

### Trade logic

```text
If sum materially > 100%:
    Buy NO on all outcomes, if executable
```

### Why this matters

Useful for exact count markets, but often harder to trade than underrounds because selling/NO-side execution may be more constrained.

### Automation difficulty

Medium.

---

# Recommended Build Order

## Phase 1: Build first

These are the best initial rules based on edge potential and automation feasibility.

1. Later deadline >= earlier deadline
2. Earlier NO >= later NO
3. Higher threshold <= lower threshold
4. Lower below-threshold <= higher below-threshold
5. Count threshold monotonicity
6. Exact count derived from cumulative probabilities
7. Binary market sanity check

## Phase 2: Add next

These are valuable but require better grouping and semantic parsing.

8. Sub-event <= parent event
9. Exhaustive mutually exclusive outcome sums
10. Exact interval decomposition
11. Mutually exclusive exact outcomes cannot sum above 100%
12. Duplicate / same-event price divergence

## Phase 3: Advanced rules

These have strong theoretical value but are more exposed to false positives and semantic/resolution risk.

13. At least one >= each component
14. All happen <= each component
15. Union bounds
16. Intersection bounds
17. Candidate election win <= nomination win
18. Party/candidate equivalence after nomination
19. Before/after/never decomposition
20. Settlement source consistency

---

# Execution Filters

A scanner should not output every theoretical inconsistency. It should rank only those that are executable.

## Minimum suggested filters

```text
Minimum gross inconsistency: 3.0%
Minimum estimated net edge: 1.5-2.0%
Minimum executable size: enough to justify time and gas/friction
Maximum spread: ideally below 3-5%
Use bid/ask, not last price or midpoint
```

For manual trading, use a stricter threshold:

```text
Minimum gross inconsistency: 5.0%
```

---

# Important Implementation Notes

## 1. Always use executable prices

Do not calculate opportunities using displayed probability, last trade, or midpoint unless only for rough screening.

Use:

```text
Buy decisions: use best ask
Sell decisions: use best bid
```

## 2. Include depth

A theoretical edge is not useful if only $5 can be traded.

Output should include:

```text
Available size at best ask
Available size across next price levels
Estimated weighted average execution price
Net edge after slippage
```

## 3. Flag resolution risk

Each opportunity should receive a resolution risk score:

```text
Low: objective official result / clear binary outcome
Medium: clear but wording-sensitive
High: subjective, semantic, governance/dispute-prone
```

## 4. Require same measurement basis

Many false positives come from markets that look similar but differ by:

```text
Settlement date
Timezone
Data source
Rounding convention
Intraday vs close price
Official announcement vs effective date
Revisions
Definition of “wins”, “announces”, “launches”, “reaches”
```

## 5. Rank opportunities by net executable edge

Suggested ranking score:

```text
Score =
    Net executable edge
    x Confidence in logical relationship
    x Liquidity score
    x Resolution clarity score
    x Time-to-expiry adjustment
```

---

# Suggested Output Format for Scanner

```text
Opportunity ID
Rule triggered
Market A
Market B / Market group
Relationship type
Executable prices used
Gross inconsistency
Estimated net edge
Available size
Resolution risk
Reason for signal
Suggested action
Manual review required: Yes/No
```

---

# Practical Conclusion

The most promising retail strategy is not to search for obvious “sum not equal to 100%” arbitrage alone. Those opportunities are likely to be competed away quickly.

The better retail edge is likely to come from:

```text
1. Deadline monotonicity
2. Threshold monotonicity
3. Count monotonicity
4. Parent/sub-event relationships
5. Duplicate or poorly linked equivalent markets
```

These are more likely to produce second-order inconsistencies that are not instantly captured by simple arbitrage bots.
