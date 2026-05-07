from datetime import datetime

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from otwarta.visualization.stats import bootstrap_ci, cohens_d, mann_whitney_u

OCT_7 = datetime(2023, 10, 7)


def create_comparison_chart(
    df: pd.DataFrame,
    cutoff: datetime = OCT_7,
    output_path: str | None = None,
) -> go.Figure:
    """Pre/post Oct-7 distribution comparison with stats annotation."""
    df = df.dropna(subset=["publication_date", "severity_score"]).copy()
    df["publication_date"] = pd.to_datetime(df["publication_date"])
    df["period"] = df["publication_date"].apply(
        lambda d: "Post Oct 7" if d >= cutoff else "Pre Oct 7"
    )

    pre_scores = df[df["period"] == "Pre Oct 7"]["severity_score"].tolist()
    post_scores = df[df["period"] == "Post Oct 7"]["severity_score"].tolist()

    stats_result = mann_whitney_u(pre_scores, post_scores) if pre_scores and post_scores else {}
    d = cohens_d(pre_scores, post_scores) if pre_scores and post_scores else 0.0
    ci_lo, ci_hi = bootstrap_ci(post_scores) if post_scores else (0.0, 0.0)

    fig = px.histogram(
        df,
        x="severity_score",
        color="period",
        barmode="overlay",
        nbins=11,
        color_discrete_map={"Pre Oct 7": "#457B9D", "Post Oct 7": "#E63946"},
        title="Antisemitism Score Distribution: Pre vs Post Oct 7, 2023",
        labels={"severity_score": "Severity Score", "count": "Articles"},
        opacity=0.7,
    )
    fig.update_layout(template="plotly_white", height=500)

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

    if output_path:
        fig.write_html(output_path)

    return fig
