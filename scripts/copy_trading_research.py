"""Fase 0: Copy trading wallet research — Polymarket Data API."""

from __future__ import annotations

import asyncio
import json
import math
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
OUT_JSON = OUT_DIR / "copy_trading_data.json"

# Rate limit: closed-positions 150/10s — stay conservative
REQ_INTERVAL = 0.12
PAGE_SIZE = 50
MAX_RETRIES = 5


@dataclass
class WalletMetrics:
    rank: int
    address: str
    user_name: str
    leaderboard_vol_usd: float
    leaderboard_pnl_usd: float
    closed_positions_count: int
    trade_fills_note: str = "See closed_positions_count; /trades paginated max ~20k fills"
    first_ts: int | None = None
    last_ts: int | None = None
    total_realized_pnl_usd: float = 0.0
    wins: int = 0
    losses: int = 0
    breakeven: int = 0
    win_rate_pct: float = 0.0
    avg_trade_size_usd: float = 0.0
    avg_pnl_usd: float = 0.0
    avg_pnl_pct: float = 0.0
    std_return_pct: float = 0.0
    sharpe_approx: float | None = None
    active_days: float = 0.0
    top_categories: list[str] = field(default_factory=list)
    category_counts: dict[str, int] = field(default_factory=dict)
    fetch_complete: bool = False
    fetch_note: str = ""


def categorize(title: str, event_slug: str) -> str:
    t = (title + " " + event_slug).lower()
    rules = [
        ("Sports", r"\b(nfl|nba|mlb|nhl|ufc|soccer|premier league|champions league|win on|vs\.|match|goal|super bowl|world cup|tennis|f1|formula)\b"),
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


class DataApiClient:
    def __init__(self) -> None:
        self._client = httpx.AsyncClient(base_url=BASE, timeout=60.0)
        self._lock = asyncio.Lock()
        self._last_at = 0.0

    async def close(self) -> None:
        await self._client.aclose()

    async def get(self, path: str, params: dict | None = None) -> any:
        for attempt in range(MAX_RETRIES):
            async with self._lock:
                elapsed = time.monotonic() - self._last_at
                if elapsed < REQ_INTERVAL:
                    await asyncio.sleep(REQ_INTERVAL - elapsed)
                r = await self._client.get(path, params=params or {})
                self._last_at = time.monotonic()
            if r.status_code == 429:
                await asyncio.sleep(2 ** attempt)
                continue
            r.raise_for_status()
            return r.json()
        r.raise_for_status()
        return []


async def fetch_leaderboard_top100(client: DataApiClient) -> list[dict]:
    rows: list[dict] = []
    for offset in (0, 50):
        batch = await client.get(
            "/v1/leaderboard",
            {
                "orderBy": "VOL",
                "timePeriod": "ALL",
                "category": "OVERALL",
                "limit": 50,
                "offset": offset,
            },
        )
        rows.extend(batch)
    return rows[:100]


async def fetch_all_closed_positions(
    client: DataApiClient,
    address: str,
    max_rows: int = 15000,
) -> list[dict]:
    out: list[dict] = []
    offset = 0
    while offset < max_rows:
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


def compute_metrics(entry: dict, positions: list[dict]) -> WalletMetrics:
    m = WalletMetrics(
        rank=int(entry["rank"]),
        address=entry["proxyWallet"],
        user_name=entry.get("userName") or "",
        leaderboard_vol_usd=float(entry.get("vol") or 0),
        leaderboard_pnl_usd=float(entry.get("pnl") or 0),
        closed_positions_count=len(positions),
    )
    if not positions:
        m.fetch_note = "no closed positions"
        return m

    ts_list = [int(p["timestamp"]) for p in positions if p.get("timestamp")]
    m.first_ts = min(ts_list) if ts_list else None
    m.last_ts = max(ts_list) if ts_list else None
    if m.first_ts and m.last_ts:
        m.active_days = (m.last_ts - m.first_ts) / 86400

    returns_pct: list[float] = []
    costs: list[float] = []
    cats: Counter[str] = Counter()

    for p in positions:
        pnl = float(p.get("realizedPnl") or 0)
        cost = float(p.get("avgPrice") or 0) * float(p.get("totalBought") or 0)
        m.total_realized_pnl_usd += pnl
        if pnl > 0.01:
            m.wins += 1
        elif pnl < -0.01:
            m.losses += 1
        else:
            m.breakeven += 1
        if cost > 0:
            costs.append(cost)
            returns_pct.append(pnl / cost)
        cat = categorize(p.get("title") or "", p.get("eventSlug") or "")
        cats[cat] += 1

    resolved = m.wins + m.losses + m.breakeven
    m.win_rate_pct = (m.wins / resolved * 100) if resolved else 0.0
    m.avg_trade_size_usd = statistics.mean(costs) if costs else 0.0
    m.avg_pnl_usd = m.total_realized_pnl_usd / resolved if resolved else 0.0
    m.avg_pnl_pct = statistics.mean(returns_pct) * 100 if returns_pct else 0.0
    m.std_return_pct = statistics.stdev(returns_pct) * 100 if len(returns_pct) > 1 else 0.0
    if len(returns_pct) > 1 and m.std_return_pct > 0:
        m.sharpe_approx = (statistics.mean(returns_pct)) / statistics.stdev(returns_pct)
    m.category_counts = dict(cats)
    m.top_categories = [c for c, _ in cats.most_common(3)]
    m.fetch_complete = True
    m.fetch_note = ""
    return m


async def fetch_recent_closed(client: DataApiClient, address: str, n: int = 20) -> list[dict]:
    return await client.get(
        "/closed-positions",
        {
            "user": address,
            "limit": n,
            "offset": 0,
            "sortBy": "TIMESTAMP",
            "sortDirection": "DESC",
        },
    )


def vol_cap_rows(vol_usd: float) -> int:
    """Whale wallets: sample fewer rows — they rarely pass copy-trade filters anyway."""
    if vol_usd >= 100_000_000:
        return 2500
    if vol_usd >= 20_000_000:
        return 5000
    if vol_usd >= 5_000_000:
        return 10000
    return 15000


async def analyze_wallet(client: DataApiClient, entry: dict, idx: int, total: int) -> WalletMetrics:
    addr = entry["proxyWallet"]
    name = entry.get("userName") or addr[:10]
    cap = vol_cap_rows(float(entry.get("vol") or 0))
    print(f"[{idx}/{total}] {name} (cap={cap}) ...", flush=True)
    positions = await fetch_all_closed_positions(client, addr, max_rows=cap)
    m = compute_metrics(entry, positions)
    if len(positions) >= cap:
        m.fetch_complete = False
        m.fetch_note = f"truncated at {cap} closed positions (volume-adaptive cap)"
    return m


def apply_filters(metrics: list[WalletMetrics]) -> list[WalletMetrics]:
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
        out.append(m)
    out.sort(key=lambda x: x.sharpe_approx or 0, reverse=True)
    return out


def ts_fmt(ts: int | None) -> str:
    if not ts:
        return "—"
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")


def render_results_md(result: dict) -> str:
    metrics = [WalletMetrics(**m) for m in result["metrics"]]
    filtered = [WalletMetrics(**m) for m in result["filtered"]]
    lines = [
        f"*Genereret: {result['generated_at']}*\n",
        "## 3. Top 100 wallets efter volume (basis-metrics)\n",
        "| Rank | User | Volume ($M) | LB PnL ($) | Closed pos | Win% | Realized PnL ($) | Sharpe | Active days |",
        "|------|------|-------------|------------|------------|------|------------------|--------|-------------|",
    ]
    for m in sorted(metrics, key=lambda x: x.rank)[:100]:
        sh = f"{m.sharpe_approx:.2f}" if m.sharpe_approx is not None else "—"
        lines.append(
            f"| {m.rank} | {m.user_name or m.address[:10]} | {m.leaderboard_vol_usd/1e6:.1f} | "
            f"{m.leaderboard_pnl_usd:,.0f} | {m.closed_positions_count} | {m.win_rate_pct:.1f} | "
            f"{m.total_realized_pnl_usd:,.0f} | {sh} | {m.active_days:.0f} |"
        )

    lines += [
        "\n## 4. Filtreret liste (kvalitetskriterier)\n",
        f"**Antal der overlever filter: {len(filtered)}**\n",
    ]
    if filtered:
        lines += [
            "| User | Address | Closed | Win% | Realized PnL | Sharpe | Avg size | Active days | Top categories |",
            "|------|---------|--------|------|--------------|--------|----------|-------------|----------------|",
        ]
        for m in filtered:
            lines.append(
                f"| {m.user_name} | `{m.address[:10]}…` | {m.closed_positions_count} | "
                f"{m.win_rate_pct:.1f}% | ${m.total_realized_pnl_usd:,.0f} | {m.sharpe_approx:.2f} | "
                f"${m.avg_trade_size_usd:,.0f} | {m.active_days:.0f} | {', '.join(m.top_categories)} |"
            )
    else:
        lines.append("*Ingen wallets opfylder alle kriterier i denne run.*\n")

    by_sharpe = sorted(
        [m for m in metrics if m.sharpe_approx is not None],
        key=lambda x: x.sharpe_approx or 0,
        reverse=True,
    )
    sanity_list = filtered[:5] if filtered else by_sharpe[:5]
    lines += ["\n## 5. Sanity check — top 5 efter Sharpe\n"]
    sanity = result.get("sanity_recent_closed", {})
    for m in sanity_list:
        lines += [
            f"### {m.user_name or m.address} (`{m.address}`)\n",
            f"- **Leaderboard PnL:** ${m.leaderboard_pnl_usd:,.0f} | **Closed-pos PnL:** ${m.total_realized_pnl_usd:,.0f}",
            f"- **Win rate:** {m.win_rate_pct:.1f}% ({m.wins}W / {m.losses}L / {m.breakeven}BE)",
            f"- **Sharpe (approx):** {m.sharpe_approx:.2f}" if m.sharpe_approx else "",
            f"- **Specialisering:** {', '.join(f'{k} ({v})' for k, v in sorted(m.category_counts.items(), key=lambda x: -x[1])[:5])}",
            f"- **Periode:** {ts_fmt(m.first_ts)} → {ts_fmt(m.last_ts)} ({m.active_days:.0f} dage)",
            f"- **Fetch note:** {m.fetch_note or 'complete'}\n",
            "**Seneste 20 closed positions:**\n",
            "| Date | Market | Outcome | PnL | Cost |",
            "|------|--------|---------|-----|------|",
        ]
        for p in sanity.get(m.address, [])[:20]:
            cost = float(p.get("avgPrice") or 0) * float(p.get("totalBought") or 0)
            ts = ts_fmt(int(p.get("timestamp") or 0))
            title = (p.get("title") or "")[:60].replace("|", "/")
            lines.append(
                f"| {ts} | {title} | {p.get('outcome','')} | ${float(p.get('realizedPnl') or 0):,.0f} | ${cost:,.0f} |"
            )
        # outlier analysis
        recent = sanity.get(m.address, [])
        if recent:
            pnls = [float(p.get("realizedPnl") or 0) for p in recent]
            wins_p = [x for x in pnls if x > 0]
            lines.append(
                f"\n*Seneste 20: {len(wins_p)} winners, max win ${max(pnls):,.0f}, "
                f"median PnL ${statistics.median(pnls):,.0f}*\n"
            )

    # conclusion
    n = len(filtered)
    lines += ["\n## 6. Konklusion\n"]
    if n < 5:
        lines.append(
            f"**{n} wallets** overlever filteret → strategien er **ikke levedygtig** "
            "med nuværende kriterier (for lille univers)."
        )
    elif n <= 30:
        lines.append(
            f"**{n} wallets** overlever filteret → **gå videre til Fase 1** (slippage-test)."
        )
    else:
        lines.append(
            f"**{n} wallets** overlever filteret → **god kandidatpulje** til Fase 1."
        )
    return "\n".join(line for line in lines if line is not None)


async def main() -> None:
    OUT_DIR.mkdir(exist_ok=True)
    client = DataApiClient()
    try:
        leaderboard = await fetch_leaderboard_top100(client)
        print(f"Leaderboard fetched: {len(leaderboard)} wallets")

        metrics: list[WalletMetrics] = []
        start_idx = 0
        if OUT_JSON.exists():
            prev = json.loads(OUT_JSON.read_text(encoding="utf-8"))
            if prev.get("metrics"):
                metrics = [WalletMetrics(**m) for m in prev["metrics"]]
                start_idx = len(metrics)
                if prev.get("leaderboard"):
                    leaderboard = prev["leaderboard"]
                print(f"Resuming from wallet {start_idx + 1}")

        for i, entry in enumerate(leaderboard[start_idx:], start_idx + 1):
            m = await analyze_wallet(client, entry, i, len(leaderboard))
            metrics.append(m)
            # checkpoint every 10
            if i % 10 == 0:
                with open(OUT_JSON, "w", encoding="utf-8") as f:
                    json.dump({"leaderboard": leaderboard, "metrics": [asdict(x) for x in metrics]}, f)

        filtered = apply_filters(metrics)

        # sanity: top 5 by sharpe (from filtered, else top 5 by sharpe overall)
        by_sharpe = sorted(
            [m for m in metrics if m.sharpe_approx is not None],
            key=lambda x: x.sharpe_approx or 0,
            reverse=True,
        )
        sanity_wallets = (filtered[:5] if filtered else by_sharpe[:5])
        sanity: dict[str, list] = {}
        for m in sanity_wallets:
            recent = await fetch_recent_closed(client, m.address, 20)
            sanity[m.address] = recent

        result = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "leaderboard": leaderboard,
            "metrics": [asdict(m) for m in metrics],
            "filtered": [asdict(m) for m in filtered],
            "sanity_recent_closed": sanity,
        }
        with open(OUT_JSON, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, default=str)

        md_path = Path("docs/copy_trading_research.md")
        base = md_path.read_text(encoding="utf-8").split("<!-- GENERATED BELOW -->")[0]
        md_path.write_text(base + "<!-- GENERATED BELOW -->\n\n" + render_results_md(result), encoding="utf-8")

        print(f"\nDone. Filtered wallets: {len(filtered)}")
        print(f"Saved {OUT_JSON}")
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
