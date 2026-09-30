from datetime import datetime

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

OCT_7 = datetime(2023, 10, 7)
_COLORS = {"dorzeczy": "#E63946", "pch24": "#2A78D6"}


def create_mention_frequency_chart(df: pd.DataFrame) -> go.Figure:
    """Monthly count of analyzed articles per site (the size of the corpus over time)."""
    plot_df = df.dropna(subset=["publication_date"]).copy()
    plot_df["publication_date"] = pd.to_datetime(plot_df["publication_date"])
    plot_df["month"] = plot_df["publication_date"].dt.to_period("M").dt.to_timestamp()

    monthly = plot_df.groupby(["month", "site"]).size().reset_index(name="count")

    fig = go.Figure()
    for site in sorted(monthly["site"].unique()):
        site_data = monthly[monthly["site"] == site].sort_values("month")
        fig.add_trace(go.Bar(
            x=site_data["month"],
            y=site_data["count"],
            name=site,
            marker_color=_COLORS.get(site, "#666"),
            opacity=0.8,
        ))

    fig.add_vline(
        x=OCT_7.timestamp() * 1000,
        line=dict(color="black", width=2, dash="dash"),
        annotation_text="Oct 7, 2023",
        annotation_position="top right",
    )
    fig.update_layout(
        title="Monthly Number of Analyzed Articles per Site",
        xaxis_title="Month",
        yaxis_title="Articles",
        barmode="stack",
        template="plotly_white",
        height=450,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    return fig


def create_frequency_vs_score_chart(df: pd.DataFrame) -> go.Figure:
    """Dual-axis: monthly article count (left) vs mean antisemitism severity_score (right)."""
    plot_df = df.dropna(subset=["publication_date", "severity_score"]).copy()
    plot_df["publication_date"] = pd.to_datetime(plot_df["publication_date"])
    plot_df["month"] = plot_df["publication_date"].dt.to_period("M").dt.to_timestamp()

    monthly = plot_df.groupby("month").agg(
        count=("severity_score", "size"),
        mean_score=("severity_score", "mean"),
    ).reset_index().sort_values("month")

    fig = make_subplots(specs=[[{"secondary_y": True}]])

    fig.add_trace(
        go.Bar(
            x=monthly["month"],
            y=monthly["count"],
            name="Article count",
            marker_color="#BFC0C0",
            opacity=0.7,
        ),
        secondary_y=False,
    )
    fig.add_trace(
        go.Scatter(
            x=monthly["month"],
            y=monthly["mean_score"],
            name="Mean antisemitism score",
            mode="lines+markers",
            line=dict(color="#E63946", width=2),
        ),
        secondary_y=True,
    )

    fig.add_vline(
        x=OCT_7.timestamp() * 1000,
        line=dict(color="black", width=2, dash="dash"),
        annotation_text="Oct 7, 2023",
        annotation_position="top right",
    )
    fig.update_layout(
        title="Monthly Analyzed Articles vs Mean Antisemitism Score",
        template="plotly_white",
        height=450,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    fig.update_yaxes(title_text="Articles", secondary_y=False)
    fig.update_yaxes(title_text="Mean severity score (0–10)", range=[0, 10], secondary_y=True)
    fig.update_xaxes(title_text="Month")
    return fig
