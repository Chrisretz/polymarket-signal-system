"""Plotly charts for Tracked Groups dashboard."""

from __future__ import annotations

import plotly.graph_objects as go
from plotly.subplots import make_subplots

from pss.dashboard.tracked_queries import RelationTimeseriesPoint

_SIGNED_COLOR = "#1f77b4"
_IMPLIED_LTE_PRICE_COLORS = ("#28a745", "#dc3545")
_PRICE_PALETTE = ("#28a745", "#dc3545", "#fd7e14", "#6f42c1", "#20c997", "#ffc107", "#17a2b8")
_REFERENCE_LINE_NAMES = frozenset(
    {"target", "target Σ", "faktisk Σ", "Σ komponenter", "weighted Σ"},
)


def _line_color(name: str, index: int, relation_type: str) -> str:
    if relation_type == "implied_lte" and index < len(_IMPLIED_LTE_PRICE_COLORS):
        return _IMPLIED_LTE_PRICE_COLORS[index]
    if name in _REFERENCE_LINE_NAMES:
        return "#adb5bd"
    return _PRICE_PALETTE[index % len(_PRICE_PALETTE)]


def _is_reference_line(name: str) -> bool:
    return name in _REFERENCE_LINE_NAMES


def relation_dual_axis_chart(
    points: list[RelationTimeseriesPoint],
    *,
    title: str,
    relation_type: str,
) -> go.Figure:
    """Dual-axis: signed afvigelse (venstre) + YES-priser % (højre)."""
    fig = make_subplots(specs=[[{"secondary_y": True}]])

    layout_base = dict(
        height=440,
        margin=dict(l=56, r=64, t=64, b=72),
        title=dict(text=title, x=0, xanchor="left", font=dict(size=15)),
        xaxis=dict(
            title="Tid (UTC)",
            automargin=True,
            tickangle=-25,
            title_standoff=14,
        ),
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
        uirevision="relation_dual_axis",
    )

    if not points:
        fig.update_layout(
            **layout_base,
            annotations=[
                dict(
                    text="Ingen snapshot-data i valgt periode",
                    xref="paper",
                    yref="paper",
                    x=0.5,
                    y=0.5,
                    showarrow=False,
                    font=dict(size=14, color="gray"),
                ),
            ],
        )
        fig.update_yaxes(title_text="Signed afvigelse (pp)", secondary_y=False)
        fig.update_yaxes(title_text="YES pris (%)", secondary_y=True, side="right")
        return fig

    x = [p.snapshot_at for p in points]
    signed_y = [p.signed_deviation_pp for p in points]

    y_pos = [max(0.0, v) for v in signed_y]
    y_neg = [min(0.0, v) for v in signed_y]

    fig.add_trace(
        go.Scatter(
            x=x,
            y=y_pos,
            mode="lines",
            line=dict(width=0),
            fill="tozeroy",
            fillcolor="rgba(220, 53, 69, 0.18)",
            showlegend=False,
            hoverinfo="skip",
        ),
        secondary_y=False,
    )
    fig.add_trace(
        go.Scatter(
            x=x,
            y=y_neg,
            mode="lines",
            line=dict(width=0),
            fill="tozeroy",
            fillcolor="rgba(40, 167, 69, 0.18)",
            showlegend=False,
            hoverinfo="skip",
        ),
        secondary_y=False,
    )
    fig.add_trace(
        go.Scatter(
            x=x,
            y=signed_y,
            mode="lines+markers",
            name="Signed afvigelse",
            line=dict(color=_SIGNED_COLOR, width=2.5),
            marker=dict(size=7),
            hovertemplate="Signed: %{y:+.2f} pp<extra></extra>",
        ),
        secondary_y=False,
    )

    line_names: list[str] = []
    if points[0].price_lines_pp:
        line_names = list(points[0].price_lines_pp.keys())
        for other in points[1:]:
            for key in other.price_lines_pp:
                if key not in line_names:
                    line_names.append(key)

    for idx, line_name in enumerate(line_names):
        ys = [p.price_lines_pp.get(line_name) for p in points]
        if all(v is None for v in ys):
            continue
        color = _line_color(line_name, idx, relation_type)
        dash = "dash" if _is_reference_line(line_name) else "solid"
        fig.add_trace(
            go.Scatter(
                x=x,
                y=ys,
                mode="lines+markers",
                name=line_name,
                line=dict(color=color, width=2, dash=dash),
                marker=dict(size=5),
                connectgaps=True,
                hovertemplate=f"{line_name}: %{{y:.1f}}%<extra></extra>",
            ),
            secondary_y=True,
        )

    fig.add_hline(
        y=0,
        line_dash="dash",
        line_color="rgba(100,100,100,0.75)",
        line_width=1.5,
        secondary_y=False,
    )

    fig.update_layout(**layout_base)
    fig.update_yaxes(
        title_text="Signed afvigelse (pp)",
        zeroline=True,
        zerolinecolor="rgba(100,100,100,0.5)",
        automargin=True,
        title_standoff=12,
        secondary_y=False,
    )
    fig.update_yaxes(
        title_text="YES pris (%)",
        automargin=True,
        title_standoff=12,
        side="right",
        secondary_y=True,
    )
    return fig


def signed_deviation_chart(
    points: list[RelationTimeseriesPoint],
    *,
    title: str,
    relation_type: str = "implied_lte",
) -> go.Figure:
    """Bagudkompatibel wrapper — bruger dual-axis chart."""
    return relation_dual_axis_chart(points, title=title, relation_type=relation_type)
