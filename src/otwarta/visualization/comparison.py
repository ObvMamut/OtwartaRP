from datetime import datetime

import pandas as pd
import plotly.graph_objects as go

from otwarta.visualization.stats import bootstrap_ci, cohens_d, mann_whitney_u

OCT_7 = datetime(2023, 10, 7)


def create_comparison_chart(
    df: pd.DataFrame,
    cutoff: datetime = OCT_7,
    output_path: str | None = None,
) -> go.Figure:
    """Monthly box plots of antisemitism severity score, colored pre vs post Oct 7."""
    df = df.dropna(subset=["publication_date", "severity_score"]).copy()
    df["publication_date"] = pd.to_datetime(df["publication_date"])
    df["month"] = df["publication_date"].dt.to_period("M").dt.to_timestamp()
    df["period"] = df["publication_date"].apply(
        lambda d: "Post Oct 7" if d >= cutoff else "Pre Oct 7"
    )

    pre_scores = df[df["period"] == "Pre Oct 7"]["severity_score"].tolist()
    post_scores = df[df["period"] == "Post Oct 7"]["severity_score"].tolist()

    stats_result = mann_whitney_u(pre_scores, post_scores) if pre_scores and post_scores else {}
    d = cohens_d(pre_scores, post_scores) if pre_scores and post_scores else 0.0
    ci_lo, ci_hi = bootstrap_ci(post_scores) if post_scores else (0.0, 0.0)

    months_sorted = sorted(df["month"].unique())
    pre_color = "#2A78D6"
    post_color = "#E63946"

    fig = go.Figure()
    for month in months_sorted:
        month_data = df[df["month"] == month]["severity_score"].tolist()
        period = "Post Oct 7" if month >= cutoff else "Pre Oct 7"
        color = post_color if period == "Post Oct 7" else pre_color
        fig.add_trace(go.Box(
            y=month_data,
            name=month.strftime("%Y-%m"),
            marker_color=color,
            showlegend=False,
            boxpoints=False,
        ))

    # Legend proxies
    fig.add_trace(go.Box(
        y=[None], name="Pre Oct 7", marker_color=pre_color, showlegend=True,
    ))
    fig.add_trace(go.Box(
        y=[None], name="Post Oct 7", marker_color=post_color, showlegend=True,
    ))

    cutoff_label = cutoff.strftime("%Y-%m")
    if cutoff_label in [m.strftime("%Y-%m") for m in months_sorted]:
        cutoff_idx = [m.strftime("%Y-%m") for m in months_sorted].index(cutoff_label)
        fig.add_shape(
            type="line",
            x0=cutoff_idx - 0.5, x1=cutoff_idx - 0.5,
            y0=0, y1=1,
            xref="x", yref="paper",
            line=dict(color="black", width=2, dash="dash"),
        )
        fig.add_annotation(
            x=cutoff_idx - 0.5, y=1,
            xref="x", yref="paper",
            text="Oct 7, 2023",
            showarrow=False,
            xanchor="left",
            yanchor="top",
            font=dict(size=11),
        )

    if stats_result:
        p = stats_result["p_value"]
        sig = "✓ p<0.05" if stats_result["significant"] else "✗ p≥0.05"
        annotation = (
            f"Mann-Whitney U: p={p:.4f} {sig}<br>"
            f"Cohen's d={d:.2f}<br>"
            f"Post mean 95% CI: [{ci_lo:.2f}, {ci_hi:.2f}]"
        )
        fig.add_annotation(
            text=annotation,
            xref="paper", yref="paper",
            x=0.98, y=0.95,
            showarrow=False,
            align="right",
            bgcolor="white",
            bordercolor="gray",
            font=dict(size=12),
        )

    fig.update_layout(
        title="Monthly Antisemitism Score Distribution: Pre vs Post Oct 7, 2023",
        xaxis_title="Month",
        yaxis_title="Severity Score (0–10)",
        yaxis=dict(range=[0, 10.5]),
        template="plotly_white",
        height=550,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    fig.update_xaxes(type="category", tickangle=45)

    if output_path:
        fig.write_html(output_path)

    return fig
