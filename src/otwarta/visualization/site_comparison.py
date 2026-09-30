from datetime import datetime
from typing import Any

import pandas as pd
import plotly.graph_objects as go

OCT_7 = datetime(2023, 10, 7)
_WINDOW = 30


def create_site_comparison_chart(df: pd.DataFrame) -> go.Figure:
    """Rolling-average severity_score vs hateful_score, separated by site."""
    has_hateful = "hateful_score" in df.columns

    plot_df = df.dropna(subset=["publication_date", "severity_score"]).copy()
    plot_df["publication_date"] = pd.to_datetime(plot_df["publication_date"])
    plot_df = plot_df.sort_values("publication_date").set_index("publication_date")

    line_styles: dict[str, dict[str, Any]] = {
        "severity": dict(width=2),
        "hateful": dict(width=2, dash="dot"),
    }
    palette = {
        "dorzeczy": {"severity": "#E63946", "hateful": "#F4A261"},
        "pch24": {"severity": "#2A78D6", "hateful": "#2A9D8F"},
    }

    fig = go.Figure()
    for site in sorted(plot_df["site"].unique()):
        site_df = plot_df[plot_df["site"] == site]
        colors = palette.get(site, {"severity": "#333", "hateful": "#888"})

        sev_rolling = (
            site_df["severity_score"]
            .rolling(f"{_WINDOW}D", min_periods=5)
            .mean()
        )
        fig.add_trace(go.Scatter(
            x=sev_rolling.index,
            y=sev_rolling.values,
            name=f"{site} — antisemitism",
            mode="lines",
            line=dict(color=colors["severity"], **line_styles["severity"]),
        ))

        if has_hateful and "hateful_score" in site_df.columns:
            hate_df = site_df.dropna(subset=["hateful_score"])
            if not hate_df.empty:
                hate_rolling = (
                    hate_df["hateful_score"]
                    .rolling(f"{_WINDOW}D", min_periods=5)
                    .mean()
                )
                fig.add_trace(go.Scatter(
                    x=hate_rolling.index,
                    y=hate_rolling.values,
                    name=f"{site} — hateful (general)",
                    mode="lines",
                    line=dict(color=colors["hateful"], **line_styles["hateful"]),
                ))

    fig.add_vline(
        x=OCT_7.timestamp() * 1000,
        line=dict(color="black", width=2, dash="dash"),
        annotation_text="Oct 7, 2023",
        annotation_position="top right",
    )
    fig.update_layout(
        title=f"Antisemitism vs General Hate Content by Site ({_WINDOW}-day rolling avg)",
        xaxis_title="Date",
        yaxis_title="Score (0–10)",
        yaxis=dict(range=[0, 10]),
        template="plotly_white",
        height=500,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    fig.update_xaxes(rangeslider_visible=True)
    return fig
