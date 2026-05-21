"""PSS Streamlit dashboard — start med: streamlit run src/pss/dashboard/app.py"""

from __future__ import annotations

import streamlit as st

from pss.config import settings
from pss.dashboard.drawdown import alert_message, compute_drawdown
from pss.dashboard.queries import fetch_pipeline_stats, fetch_realized_pnl_total

st.set_page_config(
    page_title="PSS Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)


@st.cache_data(ttl=60)
def _pipeline_stats():
    return fetch_pipeline_stats()


@st.cache_data(ttl=60)
def _realized_pnl():
    return fetch_realized_pnl_total()


st.title("Polymarket Signal System")
st.caption(f"Miljø: {settings.environment} · Bankroll (config): ${settings.bankroll_usd:,.0f}")

stats = _pipeline_stats()
realized = _realized_pnl()
current_bankroll = settings.bankroll_usd + realized
dd = compute_drawdown(
    bankroll_start=settings.bankroll_usd,
    bankroll_current=current_bankroll,
)
alert = alert_message(dd)

if alert:
    st.error(alert)
else:
    st.success(f"Drawdown OK ({dd.drawdown_pct * 100:.1f}% fra peak ${dd.peak:,.0f})")

c1, c2, c3, c4 = st.columns(4)
c1.metric("Aktive markeder", stats.active_markets)
c2.metric("Tracked events", stats.tracked_events)
c3.metric("Snapshots i DB", f"{stats.snapshot_count:,}")
last = (
    stats.last_snapshot_at.strftime("%Y-%m-%d %H:%M UTC")
    if stats.last_snapshot_at
    else "—"
)
c4.metric("Seneste snapshot", last)

c5, c6, c7 = st.columns(3)
c5.metric("Bankroll (estimat)", f"${current_bankroll:,.0f}")
c6.metric("Realiseret PnL", f"${realized:,.2f}")
new_count = stats.signal_counts.get("NEW", 0)
c7.metric("Signaler NEW", new_count)

st.subheader("Signaler efter status")
if stats.signal_counts:
    st.bar_chart(stats.signal_counts)
else:
    st.info("Ingen signaler i databasen endnu.")

st.markdown(
    """
Brug sidemenuen til **Signaler**, **Positioner**, **Journal** og **Performance**.

Se **PROGRESS.md** i projektroden for uge-status.
    """,
)
