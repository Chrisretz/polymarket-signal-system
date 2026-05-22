"""Fase 0b: PnL-leaderboard copy trading research + comon119 investigation."""

from __future__ import annotations

import asyncio
import json
import re
import statistics
import time
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import httpx

BASE = "https://data-api.polymarket.com"
OUT_DIR = Path("research")
OUT_JSON = OUT_DIR / "copy_trading_pnl_data.json"
OUT_MD = Path("docs/copy_trading_pnl_research.md")
COMON119 = "0xc3c3b3ef304ddbea39fa2246e683a71da5d0eec8"

REQ_INTERVAL = 0.12
PAGE_SIZE = 50
MAX_RETRIES = 5


def categorize(title: str, event_slug: str) -> str:
    t = (title + " " + event_slug).lower()
    rules = [
        ("Sports", r"\b(nfl|nba|mlb|nhl|ufc|soccer|premier league|champions league|win on|vs\.|match|goal|super bowl|world cup|tennis|f1|formula|spread:)\b"),
        ("Politics", r"\b(trump|biden|election|president|senate|house|governor|primary|nominee|congress|democrat|republican|vote|referendum|prime minister)\b"),
        ("Crypto", r"\b(bitcoin|btc|ethereum|eth|crypto|solana|token|defi|nft|binance)\b"),
        ("Economics", r"\b(fed|rate cut|inflation|gdp|cpi|unemployment|recession|tariff)\b"),
        ("Culture", r"\b(oscar|grammy|eurovision|movie|album|celebrity|twitter|tiktok)\b"),
        ("Tech", r"\b(openai|apple|google|meta|microsoft|ai model|spacex|ipo)\b"),
    ]
    for cat, pat in rules:
        if re.search(pat, t):
            return cat
    return "Other"


@dataclass
class WalletMetrics:
    rank: int
    address: str
    user_name: str
    leaderboard_vol_usd: float
    leaderboard_pnl_usd: float
    closed_positions_count: int
    first_ts: int | None = None
    last_ts: int | None = None
    total_realized_pnl_usd: float = 0.0
    wins: int = 0
    losses: int = 0
    breakeven: int = 0
    win_rate_pct: float = 0.0
    avg_trade_size_usd: float = 0.0
    median_trade_size_usd: float = 0.0
    size_q1_usd: float = 0.0
    size_q3_usd: float = 0.0
    trades_under_1000: int = 0
    trades_over_10000: int = 0
    category_diversity: int = 0
    avg_pnl_usd: float = 0.0
    sharpe_approx: float | None = None
    active_days: float = 0.0
    top_categories: list[str] = field(default_factory=list)
    category_counts: dict[str, int] = field(default_factory=dict)
    top10_pnl_share_pct: float = 0.0
    fetch_complete: bool = True
    fetch_note: str = ""


class DataApiClient:
    def __init__(self) -> None:
        self._client = httpx.AsyncClient(base_url=BASE, timeout=90.0)
        self._lock = asyncio.Lock()
        self._last_at = 0.0

    async def close(self) -> None:
        await self._client.aclose()

    async def get(self, path: str, params: dict | None = None) -> any:
        last_resp = None
        for attempt in range(MAX_RETRIES):
            async with self._lock:
                elapsed = time.monotonic() - self._last_at
                if elapsed < REQ_INTERVAL:
                    await asyncio.sleep(REQ_INTERVAL - elapsed)
                last_resp = await self._client.get(path, params=params or {})
                self._last_at = time.monotonic()
            if last_resp.status_code == 429:
                await asyncio.sleep(2 ** attempt + 1)
                continue
            last_resp.raise_for_status()
            return last_resp.json()
        if last_resp is not None:
            last_resp.raise_for_status()
        return []


async def fetch_leaderboard_pnl(client: DataApiClient) -> list[dict]:
    rows: list[dict] = []
    for offset in (0, 50):
        rows.extend(
            await client.get(
                "/v1/leaderboard",
                {"orderBy": "PNL", "timePeriod": "ALL", "category": "OVERALL", "limit": 50, "offset": offset},
            )
        )
    return rows[:100]


def vol_cap(vol: float) -> int:
    if vol >= 100_000_000:
        return 2500
    if vol >= 20_000_000:
        return 5000
    if vol >= 5_000_000:
        return 10000
    return 15000


async def fetch_closed(client: DataApiClient, address: str, cap: int) -> list[dict]:
    out: list[dict] = []
    offset = 0
    while offset < cap:
        batch = await client.get(
            "/closed-positions",
            {"user": address, "limit": PAGE_SIZE, "offset": offset, "sortBy": "TIMESTAMP", "sortDirection": "ASC"},
        )
        if not batch:
            break
        out.extend(batch)
        if len(batch) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
    return out


async def fetch_open_positions(client: DataApiClient, address: str) -> list[dict]:
    out: list[dict] = []
    offset = 0
    while offset < 10000:
        batch = await client.get(
            "/positions",
            {"user": address, "limit": 500, "offset": offset, "sizeThreshold": 0},
        )
        if not batch:
            break
        out.extend(batch)
        if len(batch) < 500:
            break
        offset += 500
    return out


def compute_metrics(entry: dict, positions: list[dict], cap: int) -> WalletMetrics:
    m = WalletMetrics(
        rank=int(entry["rank"]),
        address=entry["proxyWallet"],
        user_name=entry.get("userName") or "",
        leaderboard_vol_usd=float(entry.get("vol") or 0),
        leaderboard_pnl_usd=float(entry.get("pnl") or 0),
        closed_positions_count=len(positions),
    )
    if len(positions) >= cap:
        m.fetch_complete = False
        m.fetch_note = f"truncated at {cap} closed positions"

    if not positions:
        return m

    ts_list = [int(p["timestamp"]) for p in positions if p.get("timestamp")]
    m.first_ts = min(ts_list)
    m.last_ts = max(ts_list)
    m.active_days = (m.last_ts - m.first_ts) / 86400

    costs: list[float] = []
    returns: list[float] = []
    pnls: list[float] = []
    cats: Counter[str] = Counter()

    for p in positions:
        pnl = float(p.get("realizedPnl") or 0)
        cost = float(p.get("avgPrice") or 0) * float(p.get("totalBought") or 0)
        pnls.append(pnl)
        m.total_realized_pnl_usd += pnl
        if pnl > 0.01:
            m.wins += 1
        elif pnl < -0.01:
            m.losses += 1
        else:
            m.breakeven += 1
        if cost > 0:
            costs.append(cost)
            returns.append(pnl / cost)
            if cost < 1000:
                m.trades_under_1000 += 1
            if cost > 10000:
                m.trades_over_10000 += 1
        cats[categorize(p.get("title") or "", p.get("eventSlug") or "")] += 1

    resolved = m.wins + m.losses + m.breakeven
    m.win_rate_pct = (m.wins / resolved * 100) if resolved else 0.0
    m.category_counts = dict(cats)
    m.category_diversity = len(cats)
    m.top_categories = [c for c, _ in cats.most_common(3)]

    if costs:
        m.avg_trade_size_usd = statistics.mean(costs)
        m.median_trade_size_usd = statistics.median(costs)
        if len(costs) >= 4:
            q = statistics.quantiles(costs, n=4)
            m.size_q1_usd, m.size_q3_usd = q[0], q[2]
        elif len(costs) >= 2:
            m.size_q1_usd = min(costs)
            m.size_q3_usd = max(costs)

    if len(returns) > 1:
        sd = statistics.stdev(returns)
        if sd > 0:
            m.sharpe_approx = statistics.mean(returns) / sd

    m.avg_pnl_usd = m.total_realized_pnl_usd / resolved if resolved else 0.0

    if m.total_realized_pnl_usd > 0 and pnls:
        top10 = sum(sorted(pnls, reverse=True)[:10])
        m.top10_pnl_share_pct = top10 / m.total_realized_pnl_usd * 100

    return m


def apply_retail_filter(metrics: list[WalletMetrics]) -> list[WalletMetrics]:
    out = []
    for m in metrics:
        if m.closed_positions_count < 200:
            continue
        if m.active_days < 180:
            continue
        if m.total_realized_pnl_usd <= 0:
            continue
        if m.sharpe_approx is None or m.sharpe_approx <= 0.5:
            continue
        if not (50 <= m.median_trade_size_usd <= 5000):
            continue
        if m.category_diversity < 2:
            continue
        out.append(m)
    out.sort(key=lambda x: x.sharpe_approx or 0, reverse=True)
    return out


def ts_fmt(ts: int | None) -> str:
    if not ts:
        return "—"
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")


async def investigate_comon119(client: DataApiClient) -> dict:
    addr = COMON119
    lb = await client.get("/v1/leaderboard", {"orderBy": "PNL", "timePeriod": "ALL", "user": addr})
    lb_vol = await client.get("/v1/leaderboard", {"orderBy": "VOL", "timePeriod": "ALL", "user": addr})
    closed = await fetch_closed(client, addr, 15000)
    open_pos = await fetch_open_positions(client, addr)
    try:
        value = await client.get("/value", {"user": addr})
    except Exception as e:
        value = {"error": str(e)}

    closed_pnl = sum(float(p.get("realizedPnl") or 0) for p in closed)
    open_cash_pnl = sum(float(p.get("cashPnl") or 0) for p in open_pos)
    open_realized = sum(float(p.get("realizedPnl") or 0) for p in open_pos)
    open_current = sum(float(p.get("currentValue") or 0) for p in open_pos)
    open_initial = sum(float(p.get("initialValue") or 0) for p in open_pos)

    # activity sample by type
    activity_types: Counter[str] = Counter()
    for offset in range(0, 500, 100):
        batch = await client.get(
            "/activity",
            {"user": addr, "limit": 100, "offset": offset, "sortBy": "TIMESTAMP", "sortDirection": "DESC"},
        )
        if not batch:
            break
        for a in batch:
            activity_types[a.get("type") or "UNKNOWN"] += 1
        if len(batch) < 100:
            break

    worst_open = sorted(open_pos, key=lambda p: float(p.get("cashPnl") or 0))[:10]
    largest_open = sorted(open_pos, key=lambda p: float(p.get("currentValue") or 0), reverse=True)[:10]

    return {
        "address": addr,
        "leaderboard_pnl_all": lb[0] if lb else None,
        "leaderboard_vol_all": lb_vol[0] if lb_vol else None,
        "closed_positions_fetched": len(closed),
        "closed_realized_pnl_sum": closed_pnl,
        "open_positions_count": len(open_pos),
        "open_cash_pnl_sum": open_cash_pnl,
        "open_realized_pnl_sum": open_realized,
        "open_current_value_sum": open_current,
        "open_initial_value_sum": open_initial,
        "position_value_endpoint": value,
        "reconciliation": {
            "leaderboard_pnl": float(lb[0]["pnl"]) if lb else None,
            "closed_sum": closed_pnl,
            "open_cash_pnl": open_cash_pnl,
            "closed_plus_open_cash": closed_pnl + open_cash_pnl,
            "gap_lb_vs_closed": (float(lb[0]["pnl"]) - closed_pnl) if lb else None,
        },
        "activity_types_sample500": dict(activity_types),
        "worst_open_positions": [
            {
                "title": p.get("title"),
                "cashPnl": p.get("cashPnl"),
                "currentValue": p.get("currentValue"),
                "curPrice": p.get("curPrice"),
                "realizedPnl": p.get("realizedPnl"),
            }
            for p in worst_open
        ],
        "largest_open_by_value": [
            {"title": p.get("title"), "currentValue": p.get("currentValue"), "cashPnl": p.get("cashPnl")}
            for p in largest_open
        ],
        "closed_ts_range": {
            "first": ts_fmt(min(int(p["timestamp"]) for p in closed if p.get("timestamp")) if closed else None),
            "last": ts_fmt(max(int(p["timestamp"]) for p in closed if p.get("timestamp")) if closed else None),
        },
    }


def render_md(result: dict) -> str:
    metrics = [WalletMetrics(**m) for m in result["metrics"]]
    filtered = [WalletMetrics(**m) for m in result["filtered"]]
    comon = result.get("comon119_investigation", {})

    lines = [
        f"*Genereret: {result['generated_at']}*\n",
        "## 1. Top 100 wallets efter PnL (basis-metrics)\n",
        "| Rank | User | LB PnL ($) | Volume ($M) | Closed | Win% | Realized PnL | Sharpe | Median size | Q1/Q3 | <1k | >10k | Cats |",
        "|------|------|------------|-------------|--------|------|--------------|--------|-------------|-------|-----|------|------|",
    ]
    for m in sorted(metrics, key=lambda x: x.rank):
        sh = f"{m.sharpe_approx:.2f}" if m.sharpe_approx else "—"
        lines.append(
            f"| {m.rank} | {m.user_name[:20]} | {m.leaderboard_pnl_usd:,.0f} | {m.leaderboard_vol_usd/1e6:.1f} | "
            f"{m.closed_positions_count} | {m.win_rate_pct:.0f} | {m.total_realized_pnl_usd:,.0f} | {sh} | "
            f"${m.median_trade_size_usd:,.0f} | ${m.size_q1_usd:,.0f}/${m.size_q3_usd:,.0f} | "
            f"{m.trades_under_1000} | {m.trades_over_10000} | {m.category_diversity} |"
        )

    lines += [
        f"\n## 2. Filtreret liste (retail-feasibility)\n",
        f"**Kriterier:** ≥200 closed, ≥180 dage, PnL>0, Sharpe>0.5, median size $50–$5000, ≥2 kategorier\n",
        f"**Antal: {len(filtered)}**\n",
    ]
    if filtered:
        lines += [
            "| User | LB PnL | Realized PnL | Sharpe | Median | Win% | Cats | Top10 PnL share | Active days |",
            "|------|--------|--------------|--------|--------|------|------|-----------------|-------------|",
        ]
        for m in filtered:
            lines.append(
                f"| {m.user_name} | ${m.leaderboard_pnl_usd:,.0f} | ${m.total_realized_pnl_usd:,.0f} | "
                f"{m.sharpe_approx:.2f} | ${m.median_trade_size_usd:,.0f} | {m.win_rate_pct:.0f}% | "
                f"{m.category_diversity} | {m.top10_pnl_share_pct:.1f}% | {m.active_days:.0f} |"
            )

    lines += ["\n## 3. Detaljerede profiler (filtered)\n"]
    profiles = result.get("profiles", {})
    for m in filtered:
        lines += [
            f"### {m.user_name} (`{m.address}`)\n",
            f"- LB PnL: ${m.leaderboard_pnl_usd:,.0f} | Closed PnL: ${m.total_realized_pnl_usd:,.0f}",
            f"- Win rate: {m.win_rate_pct:.1f}% | Sharpe: {m.sharpe_approx:.2f}",
            f"- Trade sizes: median ${m.median_trade_size_usd:,.0f}, avg ${m.avg_trade_size_usd:,.0f}, Q1 ${m.size_q1_usd:,.0f}, Q3 ${m.size_q3_usd:,.0f}",
            f"- Under $1k: {m.trades_under_1000} | Over $10k: {m.trades_over_10000}",
            f"- Categories ({m.category_diversity}): {m.category_counts}",
            f"- Top-10 positions = {m.top10_pnl_share_pct:.1f}% of total PnL → "
            f"{'outlier-driven' if m.top10_pnl_share_pct > 50 else 'relatively distributed'}",
            f"- Active: {ts_fmt(m.first_ts)} → {ts_fmt(m.last_ts)} ({m.active_days:.0f} d)\n",
            "**Seneste 20 closed positions:**\n",
            "| Date | Market | PnL | Cost |",
            "|------|--------|-----|------|",
        ]
        for p in profiles.get(m.address, [])[:20]:
            cost = float(p.get("avgPrice") or 0) * float(p.get("totalBought") or 0)
            title = (p.get("title") or "")[:55].replace("|", "/")
            lines.append(
                f"| {ts_fmt(int(p.get('timestamp') or 0))[:10]} | {title} | "
                f"${float(p.get('realizedPnl') or 0):,.0f} | ${cost:,.0f} |"
            )
        lines.append("")

    lines += ["\n## 4. comon119 PnL-diskrepans\n"]
    if comon:
        rec = comon.get("reconciliation", {})
        lines += [
            f"- **Leaderboard PnL (ALL):** ${rec.get('leaderboard_pnl'):,.0f}" if rec.get("leaderboard_pnl") else "",
            f"- **Sum closed realizedPnl ({comon.get('closed_positions_fetched')} pos):** ${rec.get('closed_sum'):,.0f}",
            f"- **Open positions:** {comon.get('open_positions_count')} | **Open cashPnl sum:** ${comon.get('open_cash_pnl_sum'):,.0f}",
            f"- **Closed + open cashPnl:** ${rec.get('closed_plus_open_cash'):,.0f}",
            f"- **Gap (LB − closed sum):** ${rec.get('gap_lb_vs_closed'):,.0f}",
            f"- **Activity types (sample 500):** {comon.get('activity_types_sample500')}",
            f"- **Closed TS range:** {comon.get('closed_ts_range')}",
            "\n**Worst open positions (cashPnl):**\n",
        ]
        for p in comon.get("worst_open_positions", [])[:5]:
            lines.append(f"- {p.get('title','')[:60]}: cashPnl=${p.get('cashPnl'):,.0f}, value=${p.get('currentValue'):,.0f}")

    n = len(filtered)
    lines += ["\n## 5. Konklusion\n"]
    if n < 5:
        lines.append(f"**{n} wallets** → copy trading **parkeres definitivt** sammen med øvrige strategier.")
    elif n <= 15:
        lines.append(f"**{n} wallets** → **gå videre til Fase 1** (slippage-test på live trades).")
    else:
        lines.append(f"**{n} wallets** → **reelt grundlag**; overvej pipeline-bygning.")

    return "\n".join(l for l in lines if l is not None)


async def main() -> None:
    OUT_DIR.mkdir(exist_ok=True)
    client = DataApiClient()
    try:
        leaderboard = await fetch_leaderboard_pnl(client)
        print(f"PnL leaderboard: {len(leaderboard)} wallets")

        metrics: list[WalletMetrics] = []
        start = 0
        if OUT_JSON.exists():
            prev = json.loads(OUT_JSON.read_text(encoding="utf-8"))
            if prev.get("metrics"):
                metrics = [WalletMetrics(**m) for m in prev["metrics"]]
                start = len(metrics)
                leaderboard = prev.get("leaderboard", leaderboard)
                print(f"Resume from {start + 1}")

        for i, entry in enumerate(leaderboard[start:], start + 1):
            cap = vol_cap(float(entry.get("vol") or 0))
            name = entry.get("userName") or entry["proxyWallet"][:10]
            print(f"[{i}/100] {name} cap={cap}", flush=True)
            pos = await fetch_closed(client, entry["proxyWallet"], cap)
            metrics.append(compute_metrics(entry, pos, cap))
            if i % 10 == 0:
                OUT_JSON.write_text(
                    json.dumps({"leaderboard": leaderboard, "metrics": [asdict(m) for m in metrics]}),
                    encoding="utf-8",
                )

        filtered = apply_retail_filter(metrics)
        profiles: dict[str, list] = {}
        for m in filtered:
            profiles[m.address] = await client.get(
                "/closed-positions",
                {"user": m.address, "limit": 20, "offset": 0, "sortBy": "TIMESTAMP", "sortDirection": "DESC"},
            )

        print("Investigating comon119...", flush=True)
        comon = await investigate_comon119(client)

        result = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "leaderboard_type": "PNL",
            "leaderboard": leaderboard,
            "metrics": [asdict(m) for m in metrics],
            "filtered": [asdict(m) for m in filtered],
            "profiles": profiles,
            "comon119_investigation": comon,
        }
        OUT_JSON.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")

        header = """# Copy Trading Research — PnL Leaderboard (Fase 0b)

**Universe:** `GET /v1/leaderboard?orderBy=PNL&timePeriod=ALL` — top 100 efter total profit.

Se også: [volume-leaderboard research](copy_trading_research.md)

---

"""
        OUT_MD.write_text(header + render_md(result), encoding="utf-8")
        print(f"\nDone. Filtered: {len(filtered)} | Saved {OUT_JSON} + {OUT_MD}")
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
