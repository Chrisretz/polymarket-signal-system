"""Dashboard: signaler."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from pss.dashboard.queries import fetch_signals

st.header("Signaler")

status_filter = st.selectbox(
    "Status",
    ["Alle", "NEW", "ACCEPTED", "REJECTED", "EXPIRED"],
    index=0,
)
limit = st.slider("Max antal", 10, 200, 50)


@st.cache_data(ttl=45)
def _load(status: str | None, lim: int):
    return fetch_signals(status=status, limit=lim)


status_arg = None if status_filter == "Alle" else status_filter
rows = _load(status_arg, limit)

if not rows:
    st.info("Ingen signaler matcher filteret.")
    st.stop()

df = pd.DataFrame(
    [
        {
            "id": r.id,
            "polymarket": r.polymarket_url or "",
            "tid": r.generated_at,
            "status": r.status,
            "side": r.side,
            "edge": round(r.edge_pct, 3),
            "marked": round(r.market_price, 3),
            "fair": round(r.fair_value_estimate, 3),
            "size_usd": r.suggested_size_usd,
            "strategi": r.strategy,
            "spørgsmål": (r.question or "")[:80],
        }
        for r in rows
    ],
)
st.dataframe(
    df,
    width="stretch",
    hide_index=True,
    column_config={
        "polymarket": st.column_config.LinkColumn(
            "Polymarket",
            display_text="Åbn marked",
        ),
    },
)

st.subheader("Detaljer")
for r in rows[:15]:
    with st.expander(f"#{r.id} · {r.status} · {r.side} · edge {r.edge_pct:.2%}"):
        st.write(r.question)
        if r.polymarket_url:
            st.link_button("Åbn på Polymarket", r.polymarket_url)
        st.write(
            f"Marked {r.market_price:.3f} → fair {r.fair_value_estimate:.3f} · "
            f"Size ${r.suggested_size_usd:,.0f}",
        )
        if r.metadata:
            st.json(r.metadata)
        st.code(
            f"uv run python scripts/review_signal.py {r.id}\n"
            f"uv run python scripts/pre_trade_journal.py --signal-id {r.id}",
        )
