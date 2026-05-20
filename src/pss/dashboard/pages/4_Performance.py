"""Dashboard: performance og drawdown."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from pss.config import settings
from pss.dashboard.drawdown import THRESHOLDS, alert_message, compute_drawdown
from pss.dashboard.queries import (
    fetch_performance_daily,
    fetch_pipeline_stats,
    fetch_realized_pnl_total,
)

st.header("Performance")

stats = fetch_pipeline_stats()
realized = fetch_realized_pnl_total()
current = settings.bankroll_usd + realized
dd = compute_drawdown(bankroll_start=settings.bankroll_usd, bankroll_current=current)
msg = alert_message(dd)

if msg:
    st.error(msg)
else:
    st.success(f"Ingen drawdown-alarm (nuværende: {dd.drawdown_pct * 100:.1f}%)")

m1, m2, m3, m4 = st.columns(4)
m1.metric("Start bankroll", f"${settings.bankroll_usd:,.0f}")
m2.metric("Estimat nu", f"${current:,.0f}")
m3.metric("Realiseret PnL", f"${realized:,.2f}")
m4.metric("Peak", f"${dd.peak:,.0f}")

st.subheader("Drawdown-niveauer")
for threshold, level in THRESHOLDS:
    st.progress(
        min(1.0, dd.drawdown_pct / threshold) if threshold else 0,
        text=f"{level}: ≥{threshold * 100:.0f}%",
    )

daily = fetch_performance_daily()
if daily:
    df = pd.DataFrame(
        [
            {
                "dato": d.date,
                "start": float(d.bankroll_start_usd),
                "slut": float(d.bankroll_end_usd),
                "realiseret": float(d.realized_pnl_usd),
                "åbne": d.open_positions_count,
            }
            for d in reversed(daily)
        ],
    )
    st.subheader("Daglig performance (DB)")
    st.line_chart(df.set_index("dato")["slut"])
    st.dataframe(df, width="stretch", hide_index=True)
else:
    st.info(
        "`performance_daily` er tom — udfyldes når daglig PnL-job kører (senere uge). "
        "Indtil da: brug backtest-rapporter under uge 7.",
    )

st.subheader("Pipeline")
st.write(
    {
        "snapshots": stats.snapshot_count,
        "signaler": stats.signal_counts,
        "base_rate_markeder": stats.base_rate_markets,
    },
)
