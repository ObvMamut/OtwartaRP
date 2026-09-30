import json
from datetime import datetime
from typing import Any

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

OCT_7 = datetime(2023, 10, 7)
_COLORS = {"dorzeczy": "#E63946", "pch24": "#2A78D6"}


def _about_israel_gaza(result_json: Any) -> bool:
    if isinstance(result_json, str):
        result_json = json.loads(result_json)
    return bool((result_json or {}).get("is_about_israel_gaza"))


def monthly_coverage_and_severity(df: pd.DataFrame) -> pd.DataFrame:
    """Per site and month: % of articles about Israel/Gaza and % scoring >= 4."""
    plot_df = df.dropna(subset=["publication_date", "severity_score"]).copy()
    plot_df["publication_date"] = pd.to_datetime(plot_df["publication_date"])
    plot_df["month"] = plot_df["publication_date"].dt.to_period("M").dt.to_timestamp()
    plot_df["about_israel_gaza"] = plot_df["result_json"].apply(_about_israel_gaza)
    plot_df["severity_ge4"] = plot_df["severity_score"] >= 4
    return (
        plot_df.groupby(["site", "month"])
        .agg(
            pct_israel_gaza=("about_israel_gaza", "mean"),
            pct_severity_ge4=("severity_ge4", "mean"),
        )
        .mul(100)
        .reset_index()
    )


def create_coverage_vs_severity_chart(df: pd.DataFrame) -> go.Figure:
    """Small multiples: Israel/Gaza coverage share vs share of articles scoring >= 4."""
    monthly = monthly_coverage_and_severity(df)
    panels = [
        ("pct_israel_gaza", "Articles about Israel/Gaza (%)"),
        ("pct_severity_ge4", "Articles scoring ≥ 4 for antisemitism (%)"),
    ]
    fig = make_subplots(
        rows=1, cols=2, shared_yaxes=True, subplot_titles=[t for _, t in panels],
        horizontal_spacing=0.06,
    )
    for col, (metric, _title) in enumerate(panels, start=1):
        for site in sorted(monthly["site"].unique()):
            site_data = monthly[monthly["site"] == site].sort_values("month")
            fig.add_trace(
                go.Scatter(
                    x=site_data["month"],
                    y=site_data[metric],
                    name=site,
                    legendgroup=site,
                    showlegend=col == 1,
                    mode="lines+markers",
                    line=dict(color=_COLORS.get(site, "#666"), width=2),
                    marker=dict(size=8),
                    hovertemplate=f"{site} — %{{x|%Y-%m}}: %{{y:.1f}}%<extra></extra>",
                ),
                row=1, col=col,
            )
            last = site_data.iloc[-1]
            fig.add_annotation(
                x=last["month"].to_pydatetime(), y=last[metric], text=site, showarrow=False,
                xanchor="left", xshift=8, font=dict(size=12, color="#444"),
                row=1, col=col,
            )
        fig.add_vline(
            x=OCT_7.timestamp() * 1000, row=1, col=col,
            line=dict(color="black", width=1.5, dash="dash"),
        )
    fig.update_yaxes(title_text="% of analyzed articles", row=1, col=1, rangemode="tozero")
    fig.update_layout(
        title=(
            "Israel/Gaza coverage rose after Oct 7, 2023; "
            "the share of antisemitic articles stayed near baseline"
        ),
        template="plotly_white",
        height=500,
        legend=dict(orientation="h", yanchor="bottom", y=1.08, xanchor="right", x=1),
    )
    return fig
