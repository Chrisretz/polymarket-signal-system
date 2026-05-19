"""Dashboard: decisions journal."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from pss.dashboard.queries import fetch_journal

st.header("Journal")

limit = st.slider("Seneste poster", 10, 100, 30)


@st.cache_data(ttl=60)
def _load(lim: int):
    return fetch_journal(limit=lim)


rows = _load(limit)
if not rows:
    st.info(
        "Ingen journal-poster. Opret via:\n\n"
        "`uv run python scripts/pre_trade_journal.py --signal-id <id>`",
    )
    st.stop()

df = pd.DataFrame(
    [
        {
            "id": r.id,
            "type": r.entry_type,
            "strategi": r.strategy,
            "tid": r.created_at,
            "edge": r.expected_edge_pct,
            "marked": (r.question or "")[:70],
        }
        for r in rows
    ],
)
st.dataframe(df, use_container_width=True, hide_index=True)

for r in rows[:10]:
    with st.expander(f"#{r.id} · {r.entry_type} · {r.created_at.date()}"):
        st.write(r.question)
        if r.thesis:
            st.markdown(r.thesis)
