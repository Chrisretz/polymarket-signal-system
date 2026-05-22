"""Insider-activity hypothesis: retrospective volume/price analysis near resolution."""

from __future__ import annotations

import asyncio
import json
import statistics
import time
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

GAMMA = "https://gamma-api.polymarket.com"
CLOB = "https://clob.polymarket.com"
DATA = "https://data-api.polymarket.com"

OUT_DIR = Path("research")
OUT_JSON = OUT_DIR / "insider_activity_data.json"
OUT_MD = Path("docs/insider_activity_research.md")

CUTOFF = datetime(2025, 11, 21, tzinfo=timezone.utc)
POLITICS_TAGS = ("politics", "economics", "fed-rates", "geopolitics", "us-politics", "macro", "world")
TARGET_EVENTS = 50
MIN_EVENT_VOL = 100_000
MIN_TRADE_DAYS = 10  # need enough history for baseline
PRICE_MOVE_PP = 5.0
VOLUME_SPIKE_MULT = 3.0
FRICTION_PP = 3.0  # spread + slippage estimate from prior PSS research
REQ_INTERVAL = 0.15


@dataclass
class DailyBar:
    date: str
    volume_usd: float
    yes_price: float | None
    volume_source: str  # trades | activity_proxy


@dataclass
class EventAnalysis:
    event_id: str
    event_title: str
    market_question: str
    condition_id: str
    closed_time: str
    event_volume: float
    market_volume: float
    winner: str
    yes_wins: bool
    daily_bars: list[DailyBar] = field(default_factory=list)
    volume_spike: bool = False
    spike_start: str | None = None
    spike_ratio: float | None = None
    price_move_correct: bool = False
    price_move_pp: float | None = None
    price_move_hours_before: float | None = None
    insider_pattern: bool = False
    entry_price: float | None = None
    entry_time: str | None = None
    gross_edge_pp: float | None = None
    net_edge_pp: float | None = None
    profitable: bool | None = None
    volume_spike_wrong_direction: bool = False
    notes: str = ""


class Api:
    def __init__(self) -> None:
        self._c = httpx.AsyncClient(timeout=90.0)
        self._lock = asyncio.Lock()
        self._last = 0.0

    async def close(self) -> None:
        await self._c.aclose()

    async def get(self, base: str, path: str, params: dict | None = None) -> any:
        async with self._lock:
            wait = REQ_INTERVAL - (time.monotonic() - self._last)
            if wait > 0:
                await asyncio.sleep(wait)
            r = await self._c.get(f"{base}{path}", params=params or {})
            self._last = time.monotonic()
        r.raise_for_status()
        return r.json()


def parse_json_list(raw: str | list | None) -> list:
    if raw is None:
        return []
    if isinstance(raw, list):
        return raw
    return json.loads(raw)


def is_politics_macro(event: dict) -> bool:
    tags = {t.get("slug", "") for t in (event.get("tags") or [])}
    return bool(tags & set(POLITICS_TAGS))


async def collect_candidate_events(api: Api) -> list[dict]:
    """Event-level candidates: politics/macro, resolved since cutoff, min volume."""
    by_event: dict[str, dict] = {}
    for tag in POLITICS_TAGS:
        offset = 0
        while offset < 800:
            batch = await api.get(
                GAMMA,
                "/events",
                {"closed": "true", "tag_slug": tag, "limit": 50, "offset": offset},
            )
            if not batch:
                break
            for event in batch:
                if not is_politics_macro(event):
                    continue
                eid = str(event.get("id") or event.get("slug"))
                ev_vol = float(event.get("volume") or 0)
                if ev_vol < MIN_EVENT_VOL:
                    continue
                best = None
                best_vol = 0.0
                for m in event.get("markets") or []:
                    ct_s = m.get("closedTime")
                    if not ct_s or not m.get("closed"):
                        continue
                    ct = datetime.fromisoformat(ct_s.replace("Z", "+00:00"))
                    if ct < CUTOFF:
                        continue
                    outcomes = parse_json_list(m.get("outcomes"))
                    prices = parse_json_list(m.get("outcomePrices"))
                    if len(outcomes) != 2 or "1" not in prices:
                        continue
                    vol = float(m.get("volume") or 0)
                    if vol > best_vol:
                        best_vol = vol
                        best = (m, ct, outcomes, prices)
                if best is None:
                    continue
                m, ct, outcomes, prices = best
                win_idx = prices.index("1")
                yes_wins = outcomes[win_idx].lower() in ("yes", "true")

                row = {
                    "event_id": eid,
                    "event_title": event.get("title") or "",
                    "event_volume": ev_vol,
                    "market": m,
                    "closed_time": ct,
                    "winner": outcomes[prices.index("1")],
                    "yes_wins": yes_wins,
                    "tag": tag,
                }
                prev = by_event.get(eid)
                if prev is None or row["event_volume"] > prev["event_volume"]:
                    by_event[eid] = row
            offset += 50
            if len(batch) < 50:
                break

    ranked = sorted(by_event.values(), key=lambda x: x["event_volume"], reverse=True)
    return ranked[:TARGET_EVENTS]


async def fetch_trades(api: Api, condition_id: str, start_ts: int, end_ts: int) -> list[dict]:
    out: list[dict] = []
    offset = 0
    while offset < 3500:  # data-api returns 400 beyond ~3500 offset
        try:
            batch = await api.get(DATA, "/trades", {"market": condition_id, "limit": 500, "offset": offset})
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 400:
                break
            raise
        if not batch:
            break
        out.extend(t for t in batch if isinstance(t, dict))
        if len(batch) < 500:
            break
        offset += 500
    return [t for t in out if start_ts <= int(t.get("timestamp") or 0) <= end_ts]


async def fetch_clob_prices(api: Api, yes_token: str, start_ts: int, end_ts: int) -> list[tuple[int, float]]:
    hist = await api.get(
        CLOB,
        "/prices-history",
        {"market": yes_token, "interval": "max", "fidelity": 1440},
    )
    points = hist.get("history", []) if isinstance(hist, dict) else []
    return [(int(p["t"]), float(p["p"])) for p in points if start_ts <= int(p["t"]) <= end_ts]


def build_daily_bars(
    closed: datetime,
    trades: list[dict],
    prices: list[tuple[int, float]],
) -> list[DailyBar]:
    start = closed - timedelta(days=30)
    days = []
    d = start.date()
    while d <= closed.date():
        days.append(d.isoformat())
        d += timedelta(days=1)

    vol_by_day: dict[str, float] = defaultdict(float)
    for t in trades:
        ts = int(t["timestamp"])
        dt = datetime.fromtimestamp(ts, tz=timezone.utc).date().isoformat()
        vol_by_day[dt] += float(t.get("size") or 0) * float(t.get("price") or 0)

    price_by_day: dict[str, float] = {}
    for ts, p in sorted(prices):
        dt = datetime.fromtimestamp(ts, tz=timezone.utc).date().isoformat()
        price_by_day[dt] = p

    # forward-fill prices
    last_p = None
    bars: list[DailyBar] = []
    trade_days = sum(1 for day in days if vol_by_day.get(day, 0) > 0)
    vol_source = "trades" if trade_days >= MIN_TRADE_DAYS else "activity_proxy"

    for i, day in enumerate(days):
        if day in price_by_day:
            last_p = price_by_day[day]
        elif last_p is None and prices:
            # backfill from first available
            for ts, p in prices:
                pday = datetime.fromtimestamp(ts, tz=timezone.utc).date().isoformat()
                if pday <= day:
                    last_p = p

        vol = vol_by_day.get(day, 0.0)
        if vol_source == "activity_proxy" and i > 0 and last_p is not None:
            prev_day = days[i - 1]
            prev_p = price_by_day.get(prev_day)
            if prev_p is None:
                # find last known
                for j in range(i - 1, -1, -1):
                    if days[j] in price_by_day:
                        prev_p = price_by_day[days[j]]
                        break
            if prev_p is not None:
                vol = abs(last_p - prev_p) * 1_000_000  # activity index scaled

        bars.append(DailyBar(date=day, volume_usd=vol, yes_price=last_p, volume_source=vol_source))
    return bars


def detect_volume_spike(bars: list[DailyBar], closed: datetime) -> tuple[bool, str | None, float | None]:
    """48h volume ending at T vs median daily volume in days -30 to -3."""
    if len(bars) < 10:
        return False, None, None

    close_date = closed.date()
    last48_start = close_date - timedelta(days=2)
    baseline_end = close_date - timedelta(days=3)
    baseline_start = close_date - timedelta(days=30)

    def day_vol(d: str) -> float:
        for b in bars:
            if b.date == d:
                return b.volume_usd
        return 0.0

    vol48 = sum(day_vol(d.isoformat()) for d in _daterange(last48_start, close_date))
    baseline = [
        day_vol(d.isoformat())
        for d in _daterange(baseline_start, baseline_end)
        if day_vol(d.isoformat()) > 0
    ]
    if not baseline:
        return False, None, None
    med = statistics.median(baseline)
    if med <= 0:
        return False, None, None
    ratio = vol48 / med if med > 0 else 0
    if ratio < VOLUME_SPIKE_MULT:
        return False, None, ratio

    # spike start: first day in last 72h where rolling 48h exceeds threshold
    spike_start = None
    for d in _daterange(close_date - timedelta(days=3), close_date - timedelta(days=1)):
        v48 = sum(day_vol(x.isoformat()) for x in _daterange(d - timedelta(days=1), d))
        if med > 0 and v48 / med >= VOLUME_SPIKE_MULT:
            spike_start = (d - timedelta(days=1)).isoformat()
            break
    if spike_start is None:
        spike_start = (close_date - timedelta(days=2)).isoformat()
    return True, spike_start, ratio


def _daterange(start, end):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def price_on(bars: list[DailyBar], day: str) -> float | None:
    for b in bars:
        if b.date == day:
            return b.yes_price
    return None


def detect_price_move(bars: list[DailyBar], closed: datetime, yes_wins: bool) -> tuple[bool, float, float]:
    """Move from 72h before close to 24h before close in outcome direction."""
    t72 = (closed - timedelta(hours=72)).date().isoformat()
    t24 = (closed - timedelta(hours=24)).date().isoformat()
    p72 = price_on(bars, t72)
    p24 = price_on(bars, t24)
    if p72 is None or p24 is None:
        return False, 0.0, 0.0
    move = (p24 - p72) * 100
    if yes_wins:
        correct = move >= PRICE_MOVE_PP
    else:
        correct = move <= -PRICE_MOVE_PP
    return correct, move if yes_wins else -move, 48.0


def simulate_trade(
    bars: list[DailyBar],
    closed: datetime,
    spike_start: str,
    yes_wins: bool,
) -> tuple[float | None, str | None, float | None, bool | None]:
    """Enter 24h after spike_start on winning side; hold to resolution."""
    spike_dt = datetime.fromisoformat(spike_start).replace(tzinfo=timezone.utc)
    entry_dt = spike_dt + timedelta(hours=24)
    if entry_dt >= closed - timedelta(hours=12):
        return None, None, None, None  # not enough time before resolution

    entry_day = entry_dt.date().isoformat()
    p = price_on(bars, entry_day)
    if p is None:
        return None, None, None, None

    if yes_wins:
        entry = p
        payout = 1.0
    else:
        entry = 1.0 - p
        payout = 1.0

    gross = (payout - entry) * 100
    net = gross - FRICTION_PP
    return entry, entry_dt.isoformat(), net, net > 0


async def analyze_event(api: Api, cand: dict) -> EventAnalysis:
    m = cand["market"]
    closed: datetime = cand["closed_time"]
    start_ts = int((closed - timedelta(days=30)).timestamp())
    end_ts = int(closed.timestamp())
    tokens = parse_json_list(m.get("clobTokenIds"))
    cid = m["conditionId"]
    yes_token = tokens[0] if tokens else ""

    trades, prices = await asyncio.gather(
        fetch_trades(api, cid, start_ts, end_ts),
        fetch_clob_prices(api, yes_token, start_ts, end_ts),
    )
    bars = build_daily_bars(closed, trades, prices)
    trade_days = sum(1 for b in bars if b.volume_source == "trades" and b.volume_usd > 0)

    a = EventAnalysis(
        event_id=cand["event_id"],
        event_title=cand["event_title"],
        market_question=m.get("question") or "",
        condition_id=cid,
        closed_time=closed.isoformat(),
        event_volume=cand["event_volume"],
        market_volume=float(m.get("volume") or 0),
        winner=cand["winner"],
        yes_wins=cand["yes_wins"],
        daily_bars=bars,
    )

    if len(prices) < 5:
        a.notes = "insufficient price history"
        return a

    if trade_days < MIN_TRADE_DAYS:
        a.notes = f"trade history short ({trade_days}d); volume via activity proxy"

    spike, spike_start, ratio = detect_volume_spike(bars, closed)
    a.volume_spike = spike
    a.spike_start = spike_start
    a.spike_ratio = ratio

    pm_ok, move_pp, hrs = detect_price_move(bars, closed, cand["yes_wins"])
    a.price_move_correct = pm_ok
    a.price_move_pp = move_pp
    a.price_move_hours_before = hrs

    a.insider_pattern = spike and pm_ok and spike_start is not None
    if spike_start:
        entry, et, net, prof = simulate_trade(bars, closed, spike_start, cand["yes_wins"])
        a.entry_price = entry
        a.entry_time = et
        a.net_edge_pp = net
        a.gross_edge_pp = (net + FRICTION_PP) if net is not None else None
        a.profitable = prof

    if spike and not pm_ok:
        a.volume_spike_wrong_direction = True

    return a


def render_md(results: list[EventAnalysis], summary: dict) -> str:
    lines = [
        f"*Genereret: {summary['generated_at']}*\n",
        "## Metode\n",
        "- **Universe:** 50 højest-volume politics/macro events, resolved siden 2025-11-21",
        "- **Pris:** CLOB `/prices-history` (daily, interval=max)",
        "- **Volume:** trade-notional per dag; activity-proxy (|Δprice|×1M) hvis <10 dages trade-historik",
        f"- **Spike:** 48h-volume > {VOLUME_SPIKE_MULT}× median daglig baseline (dage −30 til −3)",
        f"- **Pris-signal:** ≥{PRICE_MOVE_PP}pp move i outcome-retning mellem T−72h og T−24h",
        f"- **Friktion:** {FRICTION_PP}pp (spread+slippage estimat fra prior PSS-tests)\n",
        "## Resultater\n",
        f"| Metric | Værdi |",
        f"|--------|-------|",
        f"| Events analyseret | {summary['n_analyzed']} |",
        f"| Med tilstrækkelig prisdata | {summary['n_with_prices']} |",
        f"| Volume-spike (>3×) | {summary['n_volume_spike']} |",
        f"| Insider pattern (spike + pris + >24h lead) | {summary['n_insider_pattern']} |",
        f"| Volume-spike, forkert retning (false positive) | {summary['n_spike_wrong_dir']} |",
        f"| Volume-spike uden insider pattern | {summary['n_spike_no_pattern']} |",
        f"| Hit rate (trade 24h efter spike, alle spikes) | {summary['hit_rate_pct']:.1f}% |",
        f"| Hit rate (kun insider pattern, n={summary['n_insider_pattern']}) | {summary.get('pattern_hit_rate_pct', 0):.1f}% |",
        f"| Gns. net edge (alle spikes) | {summary['avg_net_edge_pp']:.1f}pp |",
        f"| Gns. net edge (insider pattern only) | {summary.get('pattern_avg_net_edge_pp', 0):.1f}pp |\n",
        "### Konklusion\n",
        summary["conclusion"],
        "\n## Events med insider pattern\n",
    ]
    matches = [r for r in results if r.insider_pattern]
    if matches:
        lines += [
            "| Event | Spike ratio | Price move | Entry | Net edge | Profitable |",
            "|-------|-------------|------------|-------|----------|------------|",
        ]
        for r in matches:
            lines.append(
                f"| {r.event_title[:45]} | {r.spike_ratio:.1f}x | {r.price_move_pp:.1f}pp | "
                f"{r.entry_price:.2f} | {r.net_edge_pp:.1f}pp | {r.profitable} |"
            )
    else:
        lines.append("*Ingen events matchede fuldt insider pattern.*\n")

    lines += ["\n## False positives (volume-spike, forkert pris-retning)\n"]
    fps = [r for r in results if r.volume_spike_wrong_direction]
    for r in fps[:15]:
        lines.append(f"- {r.event_title[:55]} (move {r.price_move_pp:.1f}pp mod outcome)")
    if not fps:
        lines.append("*Ingen false positives i denne kategori.*")

    lines += ["\n## Alle 50 events (summary)\n"]
    lines += [
        "| # | Event | Vol ($M) | Spike | Pattern | Move | Net edge | Note |",
        "|---|-------|---------|-------|---------|------|----------|------|",
    ]
    for i, r in enumerate(results, 1):
        sp = "✓" if r.volume_spike else "—"
        ip = "✓" if r.insider_pattern else "—"
        mv = f"{r.price_move_pp:.0f}pp" if r.price_move_pp is not None else "—"
        ne = f"{r.net_edge_pp:.0f}pp" if r.net_edge_pp is not None else "—"
        lines.append(
            f"| {i} | {r.event_title[:40]} | {r.event_volume/1e6:.1f} | {sp} | {ip} | {mv} | {ne} | {r.notes[:25]} |"
        )
    return "\n".join(lines)


async def main() -> None:
    OUT_DIR.mkdir(exist_ok=True)
    api = Api()
    try:
        candidates = await collect_candidate_events(api)
        print(f"Selected {len(candidates)} events")

        results: list[EventAnalysis] = []
        for i, cand in enumerate(candidates, 1):
            title = (cand["event_title"] or "")[:50]
            print(f"[{i}/{len(candidates)}] {title}", flush=True)
            results.append(await analyze_event(api, cand))

        with_prices = [r for r in results if len([b for b in r.daily_bars if b.yes_price is not None]) >= 5]
        spikes = [r for r in results if r.volume_spike]
        patterns = [r for r in results if r.insider_pattern]
        fp_wrong = [r for r in results if r.volume_spike_wrong_direction]
        spike_no_pat = [r for r in spikes if not r.insider_pattern]

        traded = [r for r in spikes if r.profitable is not None]
        hits = sum(1 for r in traded if r.profitable)
        hit_rate = (hits / len(traded) * 100) if traded else 0.0
        avg_net = statistics.mean([r.net_edge_pp for r in traded if r.net_edge_pp is not None]) if traded else 0.0
        pattern_traded = [r for r in patterns if r.profitable is not None]
        pattern_hits = sum(1 for r in pattern_traded if r.profitable)
        pattern_hit_rate = (pattern_hits / len(pattern_traded) * 100) if pattern_traded else 0.0
        pattern_avg_net = (
            statistics.mean([r.net_edge_pp for r in pattern_traded if r.net_edge_pp is not None])
            if pattern_traded
            else 0.0
        )

        if hit_rate > 60 and avg_net > 3:
            conclusion = (
                f"**Hit rate {hit_rate:.0f}%** (alle volume-spikes) og **gns. net edge {avg_net:.1f}pp** "
                "→ diskuter pipeline."
            )
        elif hit_rate < 50 or avg_net <= 0:
            conclusion = (
                f"**Hit rate {hit_rate:.0f}%** på alle volume-spikes (n={len(traded)}), "
                f"**gns. net edge {avg_net:.1f}pp** efter {FRICTION_PP}pp friktion. "
                f"Kun **{len(patterns)}/{len(results)}** events viste fuldt insider pattern. "
                f"Volume-anomali er primært **støj** ({len(fp_wrong)}/{len(spikes)} spikes uden pris i outcome-retning). "
                "**Endegyldig test — ingen pipeline.**"
            )
        else:
            conclusion = (
                f"Hit rate {hit_rate:.0f}%, gns. net edge {avg_net:.1f}pp → grænsezone, ikke pipeline-ready."
            )

        summary = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "n_analyzed": len(results),
            "n_with_prices": len(with_prices),
            "n_volume_spike": len(spikes),
            "n_insider_pattern": len(patterns),
            "n_spike_wrong_dir": len(fp_wrong),
            "n_spike_no_pattern": len(spike_no_pat),
            "hit_rate_pct": hit_rate,
            "pattern_hit_rate_pct": pattern_hit_rate,
            "avg_net_edge_pp": avg_net,
            "pattern_avg_net_edge_pp": pattern_avg_net,
            "avg_net_edge_all_spikes_pp": avg_net,
            "conclusion": conclusion,
        }

        payload = {"summary": summary, "results": [asdict(r) for r in results]}
        OUT_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")

        header = """# Insider Activity Research (Fase 0c)

**Hypotese:** Abnormal volume + prisbevægelse 24–72h før resolution indikerer informed trading.

---

"""
        OUT_MD.write_text(header + render_md(results, summary), encoding="utf-8")
        print(f"\nDone. Patterns: {len(patterns)} | Hit rate: {hit_rate:.1f}% | Avg net: {avg_net:.1f}pp")
    finally:
        await api.close()


if __name__ == "__main__":
    asyncio.run(main())
