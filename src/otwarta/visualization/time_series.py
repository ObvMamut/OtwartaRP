from datetime import datetime
from typing import Optional

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

OCT_7 = datetime(2023, 10, 7)


def create_time_series_chart(
    df: pd.DataFrame,
    site: Optional[str] = None,
    output_path: Optional[str] = None,
    window_days: int = 30,
) -> go.Figure:
    """Create rolling-average time-series chart for a site or both sites combined."""
    if site:
        plot_df = df[df["site"] == site].copy()
        title = f"Antisemitism Severity Over Time — {site}"
    else:
        plot_df = df.copy()
        title = "Antisemitism Severity Over Time — All Sites"

    plot_df = plot_df.dropna(subset=["publication_date", "severity_score"])
    plot_df = plot_df.sort_values("publication_date")
    plot_df["publication_date"] = pd.to_datetime(plot_df["publication_date"])
    plot_df = plot_df.set_index("publication_date")

    fig = go.Figure()

    sites = [site] if site else plot_df["site"].unique().tolist()
    colors = {"dorzeczy": "#E63946", "pch24": "#457B9D"}

    for s in sites:
        site_df = plot_df[plot_df["site"] == s] if not site else plot_df
        rolling = (
            site_df["severity_score"]
            .rolling(f"{window_days}D", min_periods=5)
            .mean()
        )
        fig.add_trace(go.Scatter(
            x=rolling.index,
            y=rolling.values,
            name=f"{s} ({window_days}-day avg)",
            mode="lines",
            line=dict(color=colors.get(s, "#333"), width=2),
        ))

    fig.add_vline(
        x=OCT_7.timestamp() * 1000,
        line=dict(color="black", width=2, dash="dash"),
        annotation_text="Oct 7, 2023",
        annotation_position="top right",
    )

    fig.update_layout(
        title=title,
        xaxis_title="Date",
        yaxis_title="Severity Score (0–10)",
        yaxis=dict(range=[0, 10]),
        template="plotly_white",
        height=500,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    fig.update_xaxes(rangeslider_visible=True)

    if output_path:
        fig.write_html(output_path)

    return fig
