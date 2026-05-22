"""Streamlit UI: Tracked Market Groups (Fase 2B)."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="Tracked Groups · PSS",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Streamlit wide mode alone leaves a max-width on .block-container — override for fuld bredde.
st.markdown(
    """
    <style>
        .main .block-container {
            max-width: 100%;
            padding-left: 2rem;
            padding-right: 2rem;
        }
    </style>
    """,
    unsafe_allow_html=True,
)

from pss.config import settings
from pss.dashboard.tracked_actions import (
    action_add_market,
    action_add_markets_bulk,
    action_add_relation,
    action_classify_reference,
    action_create_group,
    action_fetch_event_markets,
    action_refresh_snapshot,
    action_remove_market,
    action_remove_relation,
    action_set_status,
)
from pss.tracking.market_refs import EVENT_URL_HELP, EventUrlError, suggest_role_label
from pss.dashboard.tracked_charts import relation_dual_axis_chart
from pss.dashboard.tracked_format import RELATION_TYPE_LABELS, format_relation_definition
from pss.dashboard.tracked_queries import (
    fetch_alert_history,
    fetch_group_detail,
    fetch_groups_overview,
    fetch_relation_timeseries,
    fetch_snapshot_history,
)

# --- Session state ---
if "tg_group_id" not in st.session_state:
    st.session_state.tg_group_id = None
if "tg_show_closed" not in st.session_state:
    st.session_state.tg_show_closed = False
if "tg_show_create" not in st.session_state:
    st.session_state.tg_show_create = False


def _clear_caches() -> None:
    st.cache_data.clear()


@st.cache_data(ttl=30)
def _load_overview(show_closed: bool) -> list:
    active = fetch_groups_overview(status="active")
    if show_closed:
        closed = fetch_groups_overview(status="closed")
        return active + closed
    return active


@st.cache_data(ttl=15)
def _load_detail(group_id: int):
    return fetch_group_detail(group_id)


@st.cache_data(ttl=30)
def _load_history(group_id: int, date_from: date | None, date_to: date | None):
    return fetch_snapshot_history(group_id, date_from=date_from, date_to=date_to)


@st.cache_data(ttl=30)
def _load_alerts(group_id: int):
    return fetch_alert_history(group_id)


@st.cache_data(ttl=30)
def _load_relation_series(
    group_id: int,
    relation_label: str,
    relation_type: str,
    definition: dict,
    days: int | None,
):
    return fetch_relation_timeseries(
        group_id,
        relation_label,
        relation_type=relation_type,
        definition=definition,
        days=days,
    )


def _format_signed_pp(signed: float | None) -> str:
    if signed is None:
        return "—"
    return f"{signed:+.1f} pp"


def _signed_status_parts(relation_type: str, signed: float | None) -> tuple[str, str]:
    """Kort status-label + valgfri detalje (fuld bredde, undgår afkortning i metrics)."""
    if signed is None:
        return "", ""
    if relation_type == "implied_lte":
        if signed > 0:
            return "Brudt", "Venstre sandsynlighed > højre"
        if signed > -3:
            return "Tæt på brud", f"{signed:+.1f} pp fra grænsen"
        return "Konsistent", f"{abs(signed):.1f} pp margin"
    if signed > 0:
        return "Over", f"{signed:+.1f} pp over forventet"
    if signed < 0:
        return "Under", f"{signed:+.1f} pp under forventet"
    return "På target", ""


def _relation_status_icon(rel) -> str:
    if rel.is_alert:
        return "🔴"
    status_short, _ = _signed_status_parts(rel.relation_type, rel.signed_deviation_pp)
    if status_short == "Tæt på brud":
        return "🟡"
    return "🟢"


def _relation_expander_label(rel) -> str:
    icon = _relation_status_icon(rel)
    type_tag = RELATION_TYPE_LABELS.get(rel.relation_type, rel.relation_type)
    signed = _format_signed_pp(rel.signed_deviation_pp)
    abs_pp = f"{rel.inconsistency_pp:.1f} pp" if rel.inconsistency_pp is not None else "—"
    status_short, _ = _signed_status_parts(rel.relation_type, rel.signed_deviation_pp)
    return (
        f"{icon}  {rel.label}  ·  {type_tag}  ·  "
        f"Signed {signed}  ·  Abs {abs_pp}  ·  {status_short}"
    )


def _render_relation_status_banner(rel) -> None:
    status_short, status_detail = _signed_status_parts(rel.relation_type, rel.signed_deviation_pp)
    if not status_short:
        return
    if rel.is_alert:
        st.error(f"**Status: {status_short}** — {status_detail or 'Over alert threshold'}")
    elif status_short == "Tæt på brud":
        st.warning(f"**Status: {status_short}** — {status_detail}")
    elif status_short == "Konsistent":
        st.success(f"**Status: {status_short}** — {status_detail}")
    else:
        detail_text = f" — {status_detail}" if status_detail else ""
        st.info(f"**Status: {status_short}**{detail_text}")


def _render_metric_row(metrics: list[tuple[str, str, str | None]]) -> None:
    """Render metrics i én række med lige brede kolonner."""
    cols = st.columns(len(metrics))
    for col, (label, value, help_text) in zip(cols, metrics):
        col.metric(label, value, help=help_text)


def _render_relation_history(group_id: int, rel) -> None:
    period_options = {
        "1 dag": 1,
        "7 dage": 7,
        "30 dage": 30,
        "Alt": None,
    }
    period_label = st.selectbox(
        "Historik periode",
        list(period_options.keys()),
        index=1,
        key=f"rel_period_{group_id}_{rel.id}",
    )
    days = period_options[period_label]
    points, stats = _load_relation_series(
        group_id,
        rel.label,
        rel.relation_type,
        rel.definition,
        days,
    )

    chart_hint = (
        "Venstre akse: signed afvigelse (pp) · Højre akse: underliggende YES-priser (%)"
    )
    st.caption(chart_hint)

    fig = relation_dual_axis_chart(
        points,
        title=f"Signed afvigelse + priser ({period_label.lower()})",
        relation_type=rel.relation_type,
    )
    st.plotly_chart(fig, use_container_width=True)

    min_val = f"{stats.min_signed_7d:+.1f} pp" if stats.min_signed_7d is not None else "—"
    max_val = f"{stats.max_signed_7d:+.1f} pp" if stats.max_signed_7d is not None else "—"
    since_breach = stats.time_since_last_breach or "—"
    _render_metric_row(
        [
            ("Gns (7d)", _format_signed_pp(stats.avg_signed_7d), "Gennemsnitlig signed afvigelse seneste 7 dage"),
            ("Min (7d)", min_val, "Laveste signed afvigelse seneste 7 dage"),
            ("Max (7d)", max_val, "Højeste signed afvigelse seneste 7 dage"),
            ("Brud (30d)", str(stats.breach_count_30d), f"Snapshots med abs ≥ {settings.tracked_group_alert_threshold_pp:.1f} pp"),
            ("Siden brud", since_breach, "Tid siden seneste alert-brud"),
        ],
    )


def _go_overview() -> None:
    st.session_state.tg_group_id = None
    _clear_caches()
    st.rerun()


def _go_group(group_id: int) -> None:
    st.session_state.tg_group_id = group_id
    _clear_caches()
    st.rerun()


def _render_overview() -> None:
    st.header("Tracked Groups")
    st.caption(
        "Manuelt kuraterede markedsgrupper med relationer og live overvågning. "
        f"Alert threshold: {settings.tracked_group_alert_threshold_pp:.1f} pp · "
        f"Snapshot: hvert {settings.tracked_group_snapshot_interval_minutes}. min"
    )

    col_f, col_n = st.columns([3, 1])
    with col_f:
        st.session_state.tg_show_closed = st.checkbox(
            "Vis lukkede grupper",
            value=st.session_state.tg_show_closed,
        )
    with col_n:
        if st.button("+ Opret ny gruppe", type="primary", use_container_width=True):
            st.session_state.tg_show_create = True

    if st.session_state.get("tg_show_create"):
        with st.form("create_group_form"):
            st.subheader("Opret ny gruppe")
            name = st.text_input("Navn *", placeholder="Fx Fed nested deadlines")
            desc = st.text_area("Beskrivelse", placeholder="Valgfri note om gruppens formål")
            c1, c2 = st.columns(2)
            submitted = c1.form_submit_button("Gem gruppe", type="primary")
            cancelled = c2.form_submit_button("Annuller")
            if cancelled:
                st.session_state.tg_show_create = False
                st.rerun()
            if submitted:
                if not name.strip():
                    st.error("Navn er påkrævet")
                else:
                    try:
                        gid = action_create_group(name.strip(), desc.strip() or None)
                        st.session_state.tg_show_create = False
                        _go_group(gid)
                    except Exception as exc:
                        st.error(str(exc))

    groups = _load_overview(st.session_state.tg_show_closed)
    if not groups:
        st.info("Ingen grupper endnu. Opret en ny gruppe for at komme i gang.")
        return

    rows = []
    for g in groups:
        snap = (
            g.snapshot_at.strftime("%Y-%m-%d %H:%M UTC") if g.snapshot_at else "—"
        )
        max_pp = f"{g.max_inconsistency_pp:.1f} pp" if g.max_inconsistency_pp is not None else "—"
        alerts = str(g.alert_count) if g.alert_count is not None else "—"
        rows.append(
            {
                "id": g.id,
                "Navn": g.name,
                "Status": g.status,
                "Markeder": g.market_count,
                "Relationer": g.relation_count,
                "Max afvigelse": max_pp,
                "Alerts": alerts,
                "Seneste snapshot": snap,
            },
        )
    st.dataframe(
        pd.DataFrame(rows),
        hide_index=True,
        use_container_width=True,
        column_config={"id": st.column_config.NumberColumn("ID", width="small")},
    )

    st.subheader("Åbn gruppe")
    opts = {f"{g.name} (#{g.id})": g.id for g in groups}
    pick = st.selectbox("Vælg gruppe", list(opts.keys()))
    if st.button("Gå til gruppe", type="primary"):
        _go_group(opts[pick])


def _render_live_banner(detail) -> None:
    metrics = detail.metrics
    if not metrics:
        st.warning("Ingen snapshot endnu. Tilføj markeder og klik **Opdater snapshot**.")
        return

    max_pp = float(metrics.get("max_inconsistency_pp", 0))
    alert_count = int(metrics.get("alert_count", 0))
    snap_ts = detail.snapshot_at.strftime("%Y-%m-%d %H:%M:%S UTC") if detail.snapshot_at else "—"

    if alert_count > 0:
        st.error(
            f"**{alert_count} alert(s)** · Max afvigelse **{max_pp:.1f} pp** "
            f"(threshold {settings.tracked_group_alert_threshold_pp:.1f} pp) · Snapshot {snap_ts}"
        )
    elif max_pp <= 2:
        st.success(f"Konsistent · Max afvigelse **{max_pp:.1f} pp** · Snapshot {snap_ts}")
    else:
        st.warning(f"Max afvigelse **{max_pp:.1f} pp** · Snapshot {snap_ts}")


def _event_pick_key(group_id: int) -> str:
    return f"tg_event_pick_{group_id}"


def _load_event_markets_into_session(group_id: int, event_slug: str) -> bool:
    """Hent event-markeder fra Gamma; returnerer True hvis markeder fundet."""
    result = action_fetch_event_markets(event_slug)
    if not result.markets:
        return False
    st.session_state[_event_pick_key(group_id)] = {
        "event_slug": result.event_slug,
        "event_title": result.title,
        "markets": [
            {
                "slug": m.slug,
                "question": m.question,
                "outcome_name": m.outcome_name,
                "condition_id": m.condition_id,
                "yes_price_pp": m.yes_price_pp,
                "no_price_pp": m.no_price_pp,
                "liquidity_usd": m.liquidity_usd,
                "suggested_role": suggest_role_label(m.outcome_name),
            }
            for m in result.markets
        ],
    }
    return True


def _render_event_market_picker(group_id: int, existing_roles: list[str]) -> None:
    pick_key = _event_pick_key(group_id)
    payload = st.session_state.get(pick_key)
    if not payload:
        return

    title = payload.get("event_title") or payload.get("event_slug", "")
    markets = payload.get("markets") or []
    st.caption(EVENT_URL_HELP)
    st.subheader(f"Vælg outcomes fra: {title}")
    st.write(f"{len(markets)} aktive markeder fundet — vælg dem du vil tracke.")

    if not markets:
        st.warning("Ingen aktive markeder fundet under dette event.")
        if st.button("Annuller", key=f"cancel_empty_{group_id}"):
            del st.session_state[pick_key]
            st.rerun()
        return

    hdr = st.columns([0.6, 2.2, 0.9, 0.9, 1.0, 1.8, 0.8])
    hdr[0].markdown("**Vælg**")
    hdr[1].markdown("**Outcome**")
    hdr[2].markdown("**YES**")
    hdr[3].markdown("**NO**")
    hdr[4].markdown("**Likviditet**")
    hdr[5].markdown("**role_label**")
    hdr[6].markdown("**side**")

    with st.form(f"pick_event_markets_{group_id}"):
        selections: list[dict] = []
        for i, m in enumerate(markets):
            cols = st.columns([0.6, 2.2, 0.9, 0.9, 1.0, 1.8, 0.8])
            default_role = m.get("suggested_role") or suggest_role_label(m["outcome_name"])
            if default_role in existing_roles:
                default_role = f"{default_role}_{i}"

            picked = cols[0].checkbox(
                " ",
                key=f"ev_pick_{group_id}_{i}",
                label_visibility="collapsed",
            )
            cols[1].write(m["outcome_name"])
            yes_pp = m.get("yes_price_pp")
            no_pp = m.get("no_price_pp")
            cols[2].write(f"{yes_pp:.1f}%" if yes_pp is not None else "—")
            cols[3].write(f"{no_pp:.1f}%" if no_pp is not None else "—")
            liq = m.get("liquidity_usd")
            cols[4].write(f"${liq:,.0f}" if liq is not None else "—")
            role = cols[5].text_input(
                "role",
                value=default_role,
                key=f"ev_role_{group_id}_{i}",
                label_visibility="collapsed",
            )
            side = cols[6].selectbox(
                "side",
                ["yes", "no"],
                key=f"ev_side_{group_id}_{i}",
                label_visibility="collapsed",
            )
            if picked:
                selections.append({"market": m, "role": role, "side": side})

        c1, c2 = st.columns(2)
        save = c1.form_submit_button("Tilføj valgte markeder", type="primary")
        cancel = c2.form_submit_button("Annuller")

        if cancel:
            del st.session_state[pick_key]
            st.rerun()

        if save:
            if not selections:
                st.error("Vælg mindst ét outcome (checkbox).")
            else:
                items = [
                    (s["market"]["slug"], s["role"].strip(), s["side"])
                    for s in selections
                    if s["role"].strip()
                ]
                if len(items) < len(selections):
                    st.error("Alle valgte outcomes skal have et role_label.")
                else:
                    ids, errors = action_add_markets_bulk(group_id, items)
                    del st.session_state[pick_key]
                    _clear_caches()
                    if errors:
                        st.warning(
                            f"Tilføjet {len(ids)} marked(er). Fejl:\n" + "\n".join(errors),
                        )
                    else:
                        st.success(f"Tilføjet {len(ids)} marked(er) fra eventet.")
                    st.rerun()


def _render_add_market(group_id: int, roles: list[str]) -> None:
    pick_key = _event_pick_key(group_id)
    if pick_key in st.session_state:
        _render_event_market_picker(group_id, roles)
        return

    with st.expander("Tilføj marked", expanded=not roles):
        tab_event, tab_single = st.tabs(["Fra Polymarket event", "Enkelt marked"])

        with tab_event:
            st.caption(
                "Indsæt event-URL fra polymarket.com/event/… — vi henter alle outcomes "
                "og lader dig vælge hvilke der skal trackes."
            )
            event_url = st.text_input(
                "Event-URL",
                placeholder="https://polymarket.com/event/next-prime-minister-of-denmark-…",
                key=f"event_url_{group_id}",
            )
            if st.button("Hent markeder fra event", type="primary", key=f"fetch_ev_{group_id}"):
                if not event_url.strip():
                    st.error("Indsæt en event-URL først.")
                else:
                    try:
                        kind, value = action_classify_reference(event_url)
                        if kind != "event_slug":
                            st.error(
                                "URL'en ser ikke ud som et rent event-link (/event/{slug}). "
                                "Brug fanen 'Enkelt marked' for condition_id eller market-slug.",
                            )
                        elif _load_event_markets_into_session(group_id, value):
                            st.rerun()
                        else:
                            st.warning(f"Ingen aktive markeder fundet for event '{value}'.")
                    except ValueError as exc:
                        st.error(str(exc))

        with tab_single:
            with st.form(f"add_market_{group_id}"):
                ref = st.text_input(
                    "Marked-reference *",
                    placeholder="condition_id (0x…), market-slug eller /market/ URL",
                )
                role = st.text_input(
                    "role_label *",
                    placeholder="fx cut_by_june",
                    help="Logisk navn brugt i relationer — unikt per gruppe.",
                )
                side = st.selectbox("outcome_side", ["yes", "no"], index=0)
                if st.form_submit_button("Gem marked", type="primary"):
                    if not ref.strip():
                        st.error("Marked-reference er påkrævet")
                    elif not role.strip():
                        st.error("role_label er påkrævet")
                    else:
                        try:
                            kind, value = action_classify_reference(ref)
                            if kind == "event_slug":
                                if _load_event_markets_into_session(group_id, value):
                                    st.rerun()
                                else:
                                    st.warning(
                                        f"Ingen aktive markeder under event '{value}'.",
                                    )
                            else:
                                action_add_market(group_id, ref.strip(), role.strip(), side)
                                _clear_caches()
                                st.success(f"Marked '{role}' tilføjet")
                                st.rerun()
                        except EventUrlError:
                            if _load_event_markets_into_session(group_id, ref.strip()):
                                st.rerun()
                        except ValueError as exc:
                            st.error(str(exc))
                        except Exception as exc:
                            st.error(f"Kunne ikke tilføje marked: {exc}")


def _build_relation_definition(
    relation_type: str,
    roles: list[str],
    form_key: str,
) -> dict[str, Any] | None:
    if not roles:
        st.warning("Tilføj mindst ét marked før du definerer relationer.")
        return None

    optional_label = st.text_input("Label (valgfri)", key=f"rel_label_{form_key}")

    if relation_type == "sum_equals":
        target = st.selectbox("target_role", roles, key=f"sum_eq_t_{form_key}")
        comps = st.multiselect("component_roles", roles, key=f"sum_eq_c_{form_key}")
        if not comps:
            return None
        d: dict[str, Any] = {"target_role": target, "component_roles": comps}

    elif relation_type == "sum_to_target":
        comps = st.multiselect("component_roles (buckets)", roles, key=f"stt_c_{form_key}")
        target_p = st.number_input(
            "target_probability",
            min_value=0.0,
            max_value=1.0,
            value=1.0,
            step=0.01,
            key=f"stt_p_{form_key}",
        )
        if not comps:
            return None
        d = {"component_roles": comps, "target_probability": target_p}

    elif relation_type == "implied_lte":
        left = st.selectbox("left_role (tidligere deadline)", roles, key=f"imp_l_{form_key}")
        right = st.selectbox("right_role (senere deadline)", roles, key=f"imp_r_{form_key}")
        d = {"left_role": left, "right_role": right}

    elif relation_type == "target_equals":
        role = st.selectbox("role", roles, key=f"te_r_{form_key}")
        target_p = st.number_input(
            "target_probability",
            min_value=0.0,
            max_value=1.0,
            value=0.5,
            step=0.01,
            key=f"te_p_{form_key}",
        )
        d = {"role": role, "target_probability": target_p}

    elif relation_type == "weighted_sum_equals":
        target = st.selectbox("target_role", roles, key=f"ws_t_{form_key}")
        n = st.number_input("Antal komponenter", min_value=1, max_value=8, value=2, key=f"ws_n_{form_key}")
        components = []
        for i in range(int(n)):
            c1, c2 = st.columns(2)
            r = c1.selectbox(f"Role {i+1}", roles, key=f"ws_r_{form_key}_{i}")
            w = c2.number_input(f"Vægt {i+1}", min_value=0.0, value=1.0, step=0.1, key=f"ws_w_{form_key}_{i}")
            components.append({"role": r, "weight": w})
        d = {"target_role": target, "components": components}

    else:
        return None

    if optional_label.strip():
        d["label"] = optional_label.strip()
    return d


def _render_add_relation(group_id: int, roles: list[str]) -> None:
    with st.expander("Tilføj relation"):
        rtype = st.selectbox(
            "Relation type",
            list(RELATION_TYPE_LABELS.keys()),
            format_func=lambda x: RELATION_TYPE_LABELS.get(x, x),
            key=f"rtype_{group_id}",
        )
        definition = _build_relation_definition(rtype, roles, f"{group_id}_{rtype}")
        if st.button("Gem relation", type="primary", key=f"save_rel_{group_id}"):
            if definition is None:
                st.error("Udfyld alle felter")
            else:
                try:
                    action_add_relation(group_id, rtype, definition)
                    _clear_caches()
                    st.success("Relation gemt")
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))


def _render_group_detail(group_id: int) -> None:
    st.markdown(
        """
        <style>
            div[data-testid="stMetric"] {
                min-width: 0;
                padding: 0.4rem 0.6rem;
            }
            div[data-testid="stMetricLabel"] p {
                white-space: normal;
                overflow: visible;
                text-overflow: unset;
            }
            div[data-testid="stMetricValue"] {
                white-space: nowrap;
                overflow: visible;
                text-overflow: unset;
                font-size: 1.15rem;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )

    detail = _load_detail(group_id)
    if detail is None:
        st.error("Gruppe ikke fundet")
        if st.button("Tilbage"):
            _go_overview()
        return

    if st.button("← Tilbage til oversigt"):
        _go_overview()

    st.header(detail.name)
    if detail.description:
        st.caption(detail.description)

    h1, h2, h3, h4 = st.columns(4)
    h1.metric("Status", detail.status)
    h2.metric("Markeder", len(detail.markets))
    h3.metric("Relationer", len(detail.relations))
    max_pp = detail.metrics.get("max_inconsistency_pp") if detail.metrics else None
    h4.metric("Max afvigelse", f"{max_pp:.1f} pp" if max_pp is not None else "—")

    btn1, btn2, btn3 = st.columns(3)
    with btn1:
        if st.button("Opdater snapshot nu", type="primary"):
            with st.spinner("Henter live priser fra Polymarket…"):
                try:
                    action_refresh_snapshot(group_id)
                    _clear_caches()
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))
    with btn2:
        if detail.status == "active":
            if st.button("Luk gruppe"):
                action_set_status(group_id, "closed")
                _clear_caches()
                st.rerun()
        else:
            if st.button("Genaktiver gruppe"):
                action_set_status(group_id, "active")
                _clear_caches()
                st.rerun()

    _render_live_banner(detail)

    roles = [m.role_label for m in detail.markets]
    tab_markets, tab_relations, tab_history, tab_alerts = st.tabs(
        ["Markeder", "Relationer", "Snapshot-historik", "Alert-historik"],
    )

    with tab_markets:
        _render_add_market(group_id, roles)
        if not detail.markets:
            st.info("Ingen markeder endnu.")
        else:
            mrows = []
            for m in detail.markets:
                price = f"{m.price_pp:.1f}%" if m.price_pp is not None else "—"
                mrows.append(
                    {
                        "role_label": m.role_label,
                        "outcome_side": m.outcome_side,
                        "Pris": price,
                        "Spørgsmål": m.question[:80],
                        "Polymarket": m.polymarket_url or "",
                    },
                )
            st.dataframe(
                pd.DataFrame(mrows),
                hide_index=True,
                use_container_width=True,
                column_config={
                    "Polymarket": st.column_config.LinkColumn("Polymarket", display_text="Åbn"),
                },
            )
            with st.expander("Fjern marked"):
                rm_options = {m.role_label: m.id for m in detail.markets}
                rm_label = st.selectbox("Marked at fjerne", list(rm_options.keys()), key="rm_market")
                if st.button("Fjern", key="btn_rm_market"):
                    action_remove_market(group_id, rm_options[rm_label])
                    _clear_caches()
                    st.rerun()

    with tab_relations:
        _render_add_relation(group_id, roles)
        if not detail.relations:
            st.info("Ingen relationer endnu.")
        else:
            for rel in detail.relations:
                with st.expander(
                    _relation_expander_label(rel),
                    expanded=rel.is_alert,
                ):
                    _render_relation_status_banner(rel)
                    _render_metric_row(
                        [
                            (
                                "Faktisk",
                                f"{rel.actual_pp:.1f}%" if rel.actual_pp is not None else "—",
                                None,
                            ),
                            (
                                "Forventet",
                                f"{rel.expected_pp:.1f}%" if rel.expected_pp is not None else "—",
                                None,
                            ),
                        ],
                    )
                    _render_relation_history(group_id, rel)
            with st.expander("Fjern relation"):
                rel_options = {
                    format_relation_definition(r.relation_type, r.definition): r.id
                    for r in detail.relations
                }
                rel_label = st.selectbox("Relation", list(rel_options.keys()))
                if st.button("Fjern relation"):
                    action_remove_relation(group_id, rel_options[rel_label])
                    _clear_caches()
                    st.rerun()

    with tab_history:
        today = date.today()
        d1, d2 = st.columns(2)
        date_from = d1.date_input("Fra dato", value=today - timedelta(days=7), key="hist_from")
        date_to = d2.date_input("Til dato", value=today, key="hist_to")
        history = _load_history(group_id, date_from, date_to)
        if not history:
            st.info("Ingen snapshots i valgt periode.")
        else:
            df = pd.DataFrame(
                [
                    {
                        "Tidspunkt": h.snapshot_at.strftime("%Y-%m-%d %H:%M UTC"),
                        "Relation": h.relation_label,
                        "Signed pp": (
                            round(h.signed_deviation_pp, 2)
                            if h.signed_deviation_pp is not None
                            else None
                        ),
                        "Abs pp": round(h.inconsistency_pp, 2),
                        "Faktisk %": h.actual_pp,
                        "Forventet %": h.expected_pp,
                        "Max pp (snapshot)": round(h.max_inconsistency_pp, 2),
                        "Alerts": h.alert_count,
                    }
                    for h in history
                ],
            )
            st.dataframe(df, hide_index=True, use_container_width=True)

    with tab_alerts:
        st.caption(
            "Alerts afledt fra snapshots hvor afvigelse ≥ "
            f"{settings.tracked_group_alert_threshold_pp:.1f} pp (samme logik som Telegram)."
        )
        alerts = _load_alerts(group_id)
        if not alerts:
            st.info("Ingen alerts i historikken endnu.")
        else:
            st.dataframe(
                pd.DataFrame(
                    [
                        {
                            "Tidspunkt": a.snapshot_at.strftime("%Y-%m-%d %H:%M UTC"),
                            "Relation": a.relation_label,
                            "Afvigelse pp": round(a.inconsistency_pp, 2),
                            "Faktisk %": a.actual_pp,
                            "Forventet %": a.expected_pp,
                        }
                        for a in alerts
                    ],
                ),
                hide_index=True,
                use_container_width=True,
            )


# --- Main ---
if st.session_state.tg_group_id is None:
    _render_overview()
else:
    _render_group_detail(st.session_state.tg_group_id)
