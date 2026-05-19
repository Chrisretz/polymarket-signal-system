"""Dashboard: positioner."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from pss.dashboard.queries import fetch_positions

st.header("Positioner")

status_filter = st.selectbox("Status", ["Alle", "OPEN", "CLOSED"], index=0)
paper_only = st.checkbox("Kun paper", value=True)


@st.cache_data(ttl=45)
def _load(status: str | None, lim: int):
    return fetch_positions(status=status, limit=lim)


status_arg = None if status_filter == "Alle" else status_filter
rows = _load(status_arg, 100)
if paper_only:
    rows = [r for r in rows if r.is_paper]

if not rows:
    st.info(
        "Ingen positioner endnu. Paper positions oprettes når du går fra "
        "ACCEPTED signal → manuel/logget entry (uge 11+).",
    )
    st.stop()

df = pd.DataFrame(
    [
        {
            "id": r.id,
            "status": r.status,
            "paper": r.is_paper,
            "side": r.side,
            "entry": r.entered_at,
            "entry_usd": r.entry_size_usd,
            "pnl_usd": r.realized_pnl_usd,
            "pnl_pct": r.realized_pnl_pct,
            "strategi": r.strategy,
            "marked": (r.question or "")[:60],
        }
        for r in rows
    ],
)
st.dataframe(df, use_container_width=True, hide_index=True)

open_rows = [r for r in rows if r.status == "OPEN"]
if open_rows:
    exposure = sum(r.entry_size_usd for r in open_rows)
    st.metric("Åben eksponering (paper)", f"${exposure:,.0f}")
