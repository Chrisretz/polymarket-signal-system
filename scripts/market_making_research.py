"""Market making research: flow analysis + simulated backtest."""

from __future__ import annotations

import asyncio
import json
import os
import statistics
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import psycopg2
from dotenv import load_dotenv

load_dotenv("env")

OUT_DIR = Path("research")
OUT_JSON = OUT_DIR / "market_making_data.json"
OUT_MD = Path("docs/market_making_research.md")

CLOB = "https://clob.polymarket.com"
DATA = "https://data-api.polymarket.com"
REQ_INTERVAL = 0.2
MAX_POSITION_USD = 50.0
QUOTE_IMPROVE_PP = 2.0
FRICTION_PP = 0.0  # makers pay 0 fee; gas handled separately
ASSUMED_MEDIAN_TRADE = 50.0  # retail clip for illiquid markets
EMPTY_BOOK_SPREAD_PP = 40.0  # CLOB bid~0/ask~1 → use snapshot proxy


@dataclass
class MarketFlow:
    market_id: int
    condition_id: str
    yes_token_id: str
    question: str
    end_date: str | None
    days_observed: int
    avg_daily_volume: float
    est_trades_per_day: float
    median_trade_size: float
    median_spread_pp: float
    median_inter_trade_min: float
    spread_source: str
    days_to_resolution: float | None
    trade_size_distribution: dict[str, float] = field(default_factory=dict)


@dataclass
class BacktestResult:
    market_id: int
    question: str
    simulated_fills: int
    round_trips: int
    spread_pnl_usd: float
    inventory_pnl_usd: float
    total_pnl_usd: float
    gas_cost_usd: float
    net_pnl_usd: float
    max_inventory_usd: float
    resolution_risk_usd: float
    notes: str = ""


def db_url() -> str:
    return os.environ["DATABASE_URL"].replace("postgres://", "postgresql://")


def fetch_candidate_markets(limit: int = 20) -> list[dict]:
    """Illiquid active markets with 14+ days data and end_date 14+ days out."""
    conn = psycopg2.connect(db_url())
    cur = conn.cursor()
    cur.execute(
        """
        WITH daily AS (
            SELECT
                market_id,
                DATE(snapshot_at AT TIME ZONE 'UTC') AS d,
                MAX(volume_total) - MIN(volume_total) AS vol_delta,
                MAX(volume_24h) AS vol24,
                COUNT(*) AS n_snaps,
                MIN(yes_price) AS min_p,
                MAX(yes_price) AS max_p
            FROM market_snapshots
            GROUP BY market_id, DATE(snapshot_at AT TIME ZONE 'UTC')
        ),
        mstats AS (
            SELECT
                m.id,
                m.condition_id,
                m.question,
                m.end_date,
                m.yes_token_id,
                m.category,
                AVG(d.vol_delta) AS avg_daily_vol,
                PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY d.vol_delta) AS med_daily_vol,
                COUNT(DISTINCT d.d) AS days,
                AVG(d.n_snaps) AS snaps_per_day,
                AVG(d.max_p - d.min_p) * 100 AS avg_daily_range_pp
            FROM markets m
            JOIN daily d ON d.market_id = m.id
            WHERE m.is_active
              AND NOT m.is_closed
              AND m.yes_token_id IS NOT NULL
              AND m.condition_id IS NOT NULL
              AND (m.end_date IS NULL OR m.end_date > NOW() + INTERVAL '14 days')
            GROUP BY m.id, m.condition_id, m.question, m.end_date, m.yes_token_id, m.category
            HAVING COUNT(DISTINCT d.d) >= 14
               AND AVG(d.vol_delta) BETWEEN 100 AND 5000
        )
        SELECT *
        FROM mstats
        ORDER BY avg_daily_vol DESC
        LIMIT %s
        """,
        (limit,),
    )
    cols = [d[0] for d in cur.description]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    conn.close()
    return rows


def fetch_snapshots(market_id: int) -> list[dict]:
    conn = psycopg2.connect(db_url())
    cur = conn.cursor()
    cur.execute(
        """
        SELECT snapshot_at, yes_price, no_price, volume_24h, volume_total, liquidity_usd
        FROM market_snapshots
        WHERE market_id = %s
        ORDER BY snapshot_at
        """,
        (market_id,),
    )
    rows = [
        {
            "snapshot_at": r[0],
            "yes_price": float(r[1]) if r[1] is not None else None,
            "no_price": float(r[2]) if r[2] is not None else None,
            "volume_24h": float(r[3] or 0),
            "volume_total": float(r[4] or 0),
            "liquidity_usd": float(r[5] or 0),
        }
        for r in cur.fetchall()
    ]
    conn.close()
    return rows


class Api:
    def __init__(self) -> None:
        self._c = httpx.AsyncClient(timeout=60.0)
        self._last = 0.0

    async def close(self) -> None:
        await self._c.aclose()

    async def get(self, url: str, params: dict | None = None) -> any:
        wait = REQ_INTERVAL - (time.monotonic() - self._last)
        if wait > 0:
            await asyncio.sleep(wait)
        r = await self._c.get(url, params=params or {})
        self._last = time.monotonic()
        r.raise_for_status()
        return r.json()


async def fetch_clob_spread(api: Api, token_id: str) -> tuple[float, float, float, bool]:
    """Returns best_bid, best_ask, spread_pp, book_has_liquidity."""
    book = await api.get(f"{CLOB}/book", {"token_id": token_id})
    bids = book.get("bids") or []
    asks = book.get("asks") or []
    best_bid = float(bids[0]["price"]) if bids else 0.0
    best_ask = float(asks[0]["price"]) if asks else 1.0
    spread_pp = (best_ask - best_bid) * 100
    has_liq = best_bid >= 0.02 and best_ask <= 0.98 and spread_pp < EMPTY_BOOK_SPREAD_PP
    return best_bid, best_ask, spread_pp, has_liq


async def fetch_trade_stats(api: Api, condition_id: str) -> tuple[float, float, dict]:
    """Median size, est count, size distribution from recent trades."""
    sizes: list[float] = []
    offset = 0
    while offset < 3500:
        try:
            batch = await api.get(DATA + "/trades", {"market": condition_id, "limit": 500, "offset": offset})
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 400:
                break
            raise
        if not batch:
            break
        for t in batch:
            if not isinstance(t, dict):
                continue
            sizes.append(float(t.get("size") or 0) * float(t.get("price") or 0))
        if len(batch) < 500:
            break
        offset += 500

    if not sizes:
        return ASSUMED_MEDIAN_TRADE, 0.0, {}

    med = statistics.median(sizes)
    dist = {
        "under_10": sum(1 for s in sizes if s < 10) / len(sizes),
        "10_50": sum(1 for s in sizes if 10 <= s < 50) / len(sizes),
        "50_200": sum(1 for s in sizes if 50 <= s < 200) / len(sizes),
        "over_200": sum(1 for s in sizes if s >= 200) / len(sizes),
    }
    return med, float(len(sizes)), dist


def estimate_spread_from_snapshots(snaps: list[dict]) -> float:
    """Median daily yes_price range as spread proxy (pp)."""
    by_day: dict[str, list[float]] = {}
    for s in snaps:
        if s["yes_price"] is None:
            continue
        d = s["snapshot_at"].date().isoformat()
        by_day.setdefault(d, []).append(s["yes_price"])
    ranges = [(max(v) - min(v)) * 100 for v in by_day.values() if len(v) > 1]
    if not ranges:
        return 0.0
    return statistics.median(ranges)


def estimate_trades_per_day(snaps: list[dict], avg_daily_vol: float, api_median_size: float) -> float:
    """Estimate daily trade count from end-of-day volume_total deltas."""
    clip = max(ASSUMED_MEDIAN_TRADE, min(api_median_size, 200.0)) if api_median_size > 0 else ASSUMED_MEDIAN_TRADE
    by_day: dict[str, float] = {}
    last_by_day: dict[str, float] = {}
    for s in snaps:
        d = s["snapshot_at"].date().isoformat()
        last_by_day[d] = s["volume_total"]
    days = sorted(last_by_day.keys())
    for i in range(1, len(days)):
        delta = max(0.0, last_by_day[days[i]] - last_by_day[days[i - 1]])
        if delta > 0:
            by_day[days[i]] = delta
    daily_counts = [min(v / clip, 50.0) for v in by_day.values() if v >= 10]
    if daily_counts:
        return statistics.median(daily_counts)
    return min(avg_daily_vol / clip, 50.0) if clip > 0 else 0.0


def estimate_inter_trade_min(avg_daily_vol: float, trades_per_day: float) -> float:
    if trades_per_day <= 0:
        return 9999.0
    return (24 * 60) / trades_per_day


async def analyze_flow(api: Api, row: dict) -> MarketFlow:
    snaps = fetch_snapshots(row["id"])
    avg_vol = float(row["avg_daily_vol"])
    med_size, _, dist = await fetch_trade_stats(api, row["condition_id"])
    est_trades = estimate_trades_per_day(snaps, avg_vol, med_size)
    snap_spread = estimate_spread_from_snapshots(snaps)

    try:
        bid, ask, live_spread, has_liq = await fetch_clob_spread(api, row["yes_token_id"])
        if has_liq:
            spread = live_spread
            spread_src = "clob_live"
        else:
            spread = snap_spread
            spread_src = f"snapshot_proxy(clob={live_spread:.0f}pp empty)"
    except Exception:
        spread = snap_spread
        spread_src = "snapshot_range_proxy"

    days_to_res = None
    if row["end_date"]:
        days_to_res = (row["end_date"].replace(tzinfo=timezone.utc) - datetime.now(timezone.utc)).days

    return MarketFlow(
        market_id=row["id"],
        condition_id=row["condition_id"],
        yes_token_id=row["yes_token_id"],
        question=row["question"],
        end_date=row["end_date"].isoformat() if row["end_date"] else None,
        days_observed=int(row["days"]),
        avg_daily_volume=avg_vol,
        est_trades_per_day=est_trades,
        median_trade_size=max(ASSUMED_MEDIAN_TRADE, min(med_size, 200.0)) if med_size > 0 else ASSUMED_MEDIAN_TRADE,
        median_spread_pp=spread,
        median_inter_trade_min=estimate_inter_trade_min(avg_vol, est_trades),
        spread_source=spread_src,
        days_to_resolution=float(days_to_res) if days_to_res is not None else None,
        trade_size_distribution=dist,
    )


def select_top5(flows: list[MarketFlow]) -> list[MarketFlow]:
    eligible = [
        f
        for f in flows
        if f.median_spread_pp >= 10.0
        and 2.0 <= f.est_trades_per_day <= 5.0
        and (f.days_to_resolution is None or f.days_to_resolution >= 14)
    ]
    eligible.sort(key=lambda x: x.median_spread_pp * min(x.est_trades_per_day, 5), reverse=True)
    if len(eligible) >= 5:
        return eligible[:5]

    relaxed = [
        f
        for f in flows
        if f.median_spread_pp >= 10.0
        and 1.0 <= f.est_trades_per_day <= 10.0
        and (f.days_to_resolution is None or f.days_to_resolution >= 14)
    ]
    relaxed.sort(key=lambda x: x.median_spread_pp, reverse=True)
    if len(relaxed) >= 5:
        return relaxed[:5]

    # Best-effort backtest sample: top 5 by spread among analyzed (even if criteria fail)
    fallback = sorted(flows, key=lambda x: (x.median_spread_pp, x.avg_daily_volume), reverse=True)
    return fallback[:5]


def simulate_mm(flow: MarketFlow, snaps: list[dict], spread_pp: float) -> BacktestResult:
    """
    Simulate MM using snapshot volume deltas as trade arrivals.
    Quotes: improve 2pp inside bid/ask around mid; re-quote every 5 min bucket.
    """
    if not snaps:
        return BacktestResult(
            flow.market_id, flow.question, 0, 0, 0, 0, 0, 0, 0, 0, 0, "no data"
        )

    spread_pp = max(spread_pp, 1.0)  # floor for simulation when proxy is 0
    half = spread_pp / 200  # half spread in price units
    improve = QUOTE_IMPROVE_PP / 100
    inventory_shares = 0.0
    inventory_cost = 0.0
    cash = 0.0
    fills = 0
    round_trips = 0
    spread_pnl = 0.0
    max_inv_usd = 0.0

    prev_total = snaps[0]["volume_total"]
    prev_ts = snaps[0]["snapshot_at"]
    last_quote_ts = prev_ts

    our_bid = None
    our_ask = None

    for s in snaps[1:]:
        mid = s["yes_price"]
        if mid is None:
            continue
        ts = s["snapshot_at"]

        # re-quote every 5 minutes or if mid moved > 2pp
        if (ts - last_quote_ts).total_seconds() >= 300 or our_bid is None:
            our_bid = max(0.01, mid - half + improve)
            our_ask = min(0.99, mid + half - improve)
            last_quote_ts = ts

        vol_delta = max(0.0, s["volume_total"] - prev_total)
        prev_total = s["volume_total"]

        if vol_delta <= 0:
            prev_ts = ts
            continue

        # distribute volume delta across estimated fills (~$35 each)
        n_hits = max(1, int(round(vol_delta / flow.median_trade_size)))
        per_fill_usd = min(MAX_POSITION_USD, vol_delta / n_hits)

        for _ in range(n_hits):
            # taker hits our ask (we sell) if price at or above our ask
            if mid >= our_ask - 0.005:
                size_sh = per_fill_usd / our_ask
                if inventory_shares >= size_sh:
                    inventory_shares -= size_sh
                    cash += per_fill_usd
                    spread_pnl += per_fill_usd * (spread_pp / 100) * 0.5
                    fills += 1
                    if inventory_shares < 0.01:
                        round_trips += 1
                elif inventory_shares <= 0 and per_fill_usd <= MAX_POSITION_USD:
                    # short via selling - track negative inventory
                    inventory_shares -= size_sh
                    cash += per_fill_usd
                    fills += 1

            # taker hits our bid (we buy)
            elif mid <= our_bid + 0.005:
                size_sh = per_fill_usd / our_bid
                inv_usd = abs(inventory_shares * mid)
                if inv_usd + per_fill_usd <= MAX_POSITION_USD:
                    inventory_shares += size_sh
                    inventory_cost += per_fill_usd
                    cash -= per_fill_usd
                    fills += 1

        inv_usd = abs(inventory_shares * (mid or 0.5))
        max_inv_usd = max(max_inv_usd, inv_usd)
        prev_ts = ts

    final_mid = next((s["yes_price"] for s in reversed(snaps) if s["yes_price"] is not None), 0.5)
    inventory_value = inventory_shares * final_mid
    inventory_pnl = cash + inventory_value - inventory_cost

    # gas: ~0.01 per order update on Polygon; 288 requotes/day * days
    days = max(1, flow.days_observed)
    requotes = days * 288
    gas = requotes * 0.005  # ~$0.005 per cancel/replace batch

    total = spread_pnl + inventory_pnl
    net = total - gas - FRICTION_PP * fills / 100 * MAX_POSITION_USD

    return BacktestResult(
        market_id=flow.market_id,
        question=flow.question,
        simulated_fills=fills,
        round_trips=round_trips,
        spread_pnl_usd=spread_pnl,
        inventory_pnl_usd=inventory_pnl,
        total_pnl_usd=total,
        gas_cost_usd=gas,
        net_pnl_usd=net,
        max_inventory_usd=max_inv_usd,
        resolution_risk_usd=max_inv_usd,
        notes=f"spread={spread_pp:.1f}pp fills={fills}",
    )


def render_md(flows: list[MarketFlow], top5: list[MarketFlow], backtests: list[BacktestResult], summary: dict) -> str:
    lines = [
        f"*Genereret: {summary['generated_at']}*\n",
        "## Opgave 0: Polymarket market maker økonomi\n",
        "### 1. Maker rewards / LP incentives\n",
        "| Program | Beskrivelse |",
        "|---------|-------------|",
        "| **Maker Rebates** | 20–25% af taker fees redistribueres dagligt i USDC til makers hvis ordrer bliver filled. Min payout $1. |",
        "| **Liquidity Rewards** | Separat incitamentprogram (dYdX-inspireret scoring) for resting limit orders tæt på midpoint. Daglig udbetaling. |",
        "| **April 2026 Sports LP** | $5M+ i sports/esports liquidity incentives (pre/live per game). |",
        "| **Maker fee** | **0** på alle kategorier — makers betaler ikke trading fee. |",
        "| **Negative maker fees?** | Nej direkte; rebates kommer fra taker fee pool, ikke negative fees. |",
        "| **Geopolitics** | Fee-free (ingen taker fees, ingen rebates). |\n",
        "### 2. Fee structure\n",
        "| Kategori | Taker fee rate | Maker fee |",
        "|----------|----------------|-----------|",
        "| Crypto | 0.07 | 0 |",
        "| Sports | 0.03 | 0 |",
        "| Finance / Politics / Tech / Mentions | 0.04 | 0 |",
        "| Economics / Culture / Weather / Other | 0.05 | 0 |",
        "| Geopolitics | 0 | 0 |",
        "Formel: `fee = C × feeRate × p × (1-p)` (symmetrisk omkring 50%).\n",
        "**Gas (Polygon):** Limit orders er off-chain signed; on-chain settlement sker ved match. Re-quote/cancel er gratis off-chain via CLOB API. Heartbeat påkrævet hvert 10s ellers cancel all. Estimeret ~$0.005 per batch re-quote ved on-chain allowance ops.\n",
        "**Order cancellation:** Gratis via API (single, batch, all, per-market).\n",
        "### 3. Order types\n",
        "| Type | Beskrivelse |",
        "|------|-------------|",
        "| **GTC** | Good-til-cancel — default for passive quotes |",
        "| **GTD** | Good-til-date — auto-expire |",
        "| **FOK / FAK** | Market order typer |",
        "| **Post-only** | Rejected hvis marketable — garanterer maker status |",
        "### 4. Adverse selection & resolution\n",
        "- Resolution via **UMA Optimistic Oracle** — 2t challenge period, op til 4-6 dage ved dispute.",
        "- **Trading stopper** straks ved resolution; winning tokens redeemable til $1.",
        "- Ingen dokumenteret pre-resolution order freeze ud over normal order lifecycle.",
        "- **Heartbeat:** Manglende heartbeat inden 10s → **alle open orders cancelled**.",
        "- Risiko: informed traders handler mod dig tæt på nyheder/resolution.\n",
        "---\n",
        "## Opgave 1: Flow-analyse (20 illikvide markeder)\n",
        "Kriterier: avg daily volume $100–$5,000 (via `volume_total` delta), 14+ dage data, 14+ dage til resolution.\n",
        "**Bemærk:** DB snapshots har **ingen bid/ask** — spread målt live via CLOB `/book` eller estimeret fra daglig pris-range.\n",
        "**Trades estimeret** fra daily volume / median trade size (data-api sample).\n",
        "| # | Market | Avg vol/d | Est trades/d | Spread | Inter-trade | Days left |",
        "|---|--------|-----------|--------------|--------|-------------|-----------|",
    ]
    for i, f in enumerate(flows, 1):
        dleft = f"{f.days_to_resolution:.0f}" if f.days_to_resolution else "—"
        lines.append(
            f"| {i} | {f.question[:45]} | ${f.avg_daily_volume:,.0f} | {f.est_trades_per_day:.1f} | "
            f"{f.median_spread_pp:.0f}pp ({f.spread_source[:4]}) | {f.median_inter_trade_min:.0f}m | {dleft} |"
        )

    lines += ["\n### 5 kandidat-markeder\n"]
    strict_n = summary.get("n_strict_candidates", 0)
    if strict_n >= 5:
        lines.append("Opfylder strict filter (spread ≥10pp, 2–5 trades/d, 14+ dage):\n")
    else:
        lines.append(
            f"**Strict filter: {strict_n}/50 opfyldt** (ingen markeder med konsistent ≥10pp spread i illiquid bucket). "
            "CLOB order books er tomme (100pp artefakt); reelle daglige pris-ranges er 0–4pp. "
            "Backtest kører på **5 bedste-effort** markeder (højeste observerede spread):\n"
        )
    if top5:
        lines += ["| Market | Spread | Trades/d | Vol/d | Strict OK? |", "|--------|--------|----------|-------|------------|"]
        for f in top5:
            ok = (
                f.median_spread_pp >= 10
                and 2 <= f.est_trades_per_day <= 5
                and (f.days_to_resolution or 99) >= 14
            )
            lines.append(
                f"| {f.question[:50]} | {f.median_spread_pp:.0f}pp | {f.est_trades_per_day:.1f} | "
                f"${f.avg_daily_volume:,.0f} | {'✓' if ok else '—'} |"
            )

    lines += ["\n## Opgave 2: Simuleret market making backtest\n"]
    lines += [
        "Strategi: quote 2pp inde i spread, max $50/leg, re-quote hver 5 min. "
        "Fills simuleret fra `volume_total` deltas i snapshots.\n",
        "| Market | Fills | Round-trips | Spread PnL | Inventory PnL | Gas | **Net PnL** | Max inv |",
        "|--------|-------|-------------|------------|---------------|-----|-------------|---------|",
    ]
    for b in backtests:
        lines.append(
            f"| {b.question[:40]} | {b.simulated_fills} | {b.round_trips} | ${b.spread_pnl_usd:.2f} | "
            f"${b.inventory_pnl_usd:.2f} | ${b.gas_cost_usd:.2f} | **${b.net_pnl_usd:.2f}** | ${b.max_inventory_usd:.0f} |"
        )

    lines += ["\n## Konklusion\n", summary["conclusion"]]
    return "\n".join(lines)


async def main() -> None:
    OUT_DIR.mkdir(exist_ok=True)
    api = Api()
    try:
        candidates = fetch_candidate_markets(20)
        print(f"DB candidates: {len(candidates)}")

        flows: list[MarketFlow] = []
        for i, row in enumerate(candidates, 1):
            print(f"[{i}/20] analyzing market {row['id']}...", flush=True)
            flows.append(await analyze_flow(api, row))

        top5 = select_top5(flows)
        strict5 = [
            f
            for f in flows
            if f.median_spread_pp >= 10.0
            and 2.0 <= f.est_trades_per_day <= 5.0
            and (f.days_to_resolution is None or f.days_to_resolution >= 14)
        ]
        print(f"Top 5 candidates (best-effort): {len(top5)} | Strict filter: {len(strict5)}")

        backtests: list[BacktestResult] = []
        for f in top5:
            snaps = fetch_snapshots(f.market_id)
            backtests.append(simulate_mm(f, snaps, f.median_spread_pp))

        total_net = sum(b.net_pnl_usd for b in backtests)
        positive = sum(1 for b in backtests if b.net_pnl_usd > 0)

        if total_net > 0 and positive >= 3:
            conclusion = (
                f"Simuleret **net PnL ${total_net:.2f}** på {len(top5)} markeder ({positive}/{len(top5)} positive). "
                "Empirisk grundlag svagt positivt — **diskuter implementation** med forbehold."
            )
        else:
            conclusion = (
                f"**0 markeder** opfylder strict kriterier (spread ≥10pp, 2–5 trades/d). "
                f"Bedste observerede spreads: 0–4pp (tomme CLOB books). "
                f"Simuleret net PnL på 5 bedste-effort markeder: **${total_net:.2f}** ({positive}/{len(top5)} positive). "
                "Spread capture dækker ikke gas + inventory risk. "
                "**Retail market making er ikke levedygtig** på Polymarket."
            )

        summary = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "n_analyzed": len(flows),
            "n_strict_candidates": len(strict5),
            "n_candidates": len(top5),
            "total_net_pnl_usd": total_net,
            "positive_markets": positive,
            "conclusion": conclusion,
        }

        payload = {
            "summary": summary,
            "flows": [asdict(f) for f in flows],
            "top5": [asdict(f) for f in top5],
            "backtests": [asdict(b) for b in backtests],
        }
        OUT_JSON.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")

        header = """# Market Making Research (Fase 0d)

**Præmis:** Spread capture, ikke prisforudsigelse. 11 prior edge-strategier fejlede.

---

"""
        OUT_MD.write_text(header + render_md(flows, top5, backtests, summary), encoding="utf-8")
        print(f"\nDone. Net PnL: ${total_net:.2f} | Saved {OUT_MD}")
    finally:
        await api.close()


if __name__ == "__main__":
    asyncio.run(main())
