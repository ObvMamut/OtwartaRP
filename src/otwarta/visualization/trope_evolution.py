from datetime import datetime
from typing import Any

import pandas as pd
import plotly.graph_objects as go

OCT_7 = datetime(2023, 10, 7)

_TROPE_COLORS = {
    "economic": "#2196F3",
    "anti-zionist": "#FF5722",
    "conspiracy": "#9C27B0",
    "historical": "#795548",
    "religious": "#FF9800",
}
_ALL_TROPES = list(_TROPE_COLORS)


def _extract_tropes(result_json: Any) -> list[str]:
    if not isinstance(result_json, dict):
        return []
    cats = result_json.get("trope_categories", [])
    return [c for c in (cats or []) if c in _ALL_TROPES]


def create_trope_stacked_area(df: pd.DataFrame) -> go.Figure:
    """Stacked area chart: proportion of each trope category over time."""
    if "result_json" not in df.columns:
        fig = go.Figure()
        fig.update_layout(title="Trope Evolution (no data — result_json column missing)")
        return fig

    plot_df = df.dropna(subset=["publication_date"]).copy()
    plot_df["publication_date"] = pd.to_datetime(plot_df["publication_date"])
    plot_df["month"] = plot_df["publication_date"].dt.to_period("M").dt.to_timestamp()

    rows = []
    for _, row in plot_df.iterrows():
        tropes = _extract_tropes(row.get("result_json"))
        for trope in tropes:
            rows.append({"month": row["month"], "trope": trope})

    if not rows:
        fig = go.Figure()
        fig.update_layout(
            title="Trope Category Evolution Over Time (no trope data yet)",
            template="plotly_white",
        )
        return fig

    trope_df = pd.DataFrame(rows)
    monthly = (
        trope_df.groupby(["month", "trope"])
        .size()
        .unstack(fill_value=0)
        .reindex(columns=_ALL_TROPES, fill_value=0)
        .reset_index()
        .sort_values("month")
    )

    fig = go.Figure()
    for trope in _ALL_TROPES:
        if trope not in monthly.columns:
            continue
        fig.add_trace(go.Scatter(
            x=monthly["month"],
            y=monthly[trope],
            name=trope.capitalize(),
            mode="lines",
            stackgroup="one",
            fillcolor=_TROPE_COLORS[trope],
            line=dict(color=_TROPE_COLORS[trope], width=0.5),
        ))

    fig.add_vline(
        x=OCT_7.timestamp() * 1000,
        line=dict(color="black", width=2, dash="dash"),
        annotation_text="Oct 7, 2023",
        annotation_position="top right",
    )
    fig.update_layout(
        title="Antisemitic Trope Category Evolution Over Time",
        xaxis_title="Month",
        yaxis_title="Articles per category",
        template="plotly_white",
        height=500,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    return fig
