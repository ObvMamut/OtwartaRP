from datetime import datetime

import pandas as pd
import plotly.graph_objects as go

OCT_7 = datetime(2023, 10, 7)

# Per-site, per-score-type: (dot_color_faint, line_color, marker_symbol)
_STYLE: dict[str, dict[str, tuple[str, str, str]]] = {
    "dorzeczy": {
        "severity": ("rgba(230,57,70,0.35)",  "#E63946", "circle"),
        "hate":     ("rgba(244,162,97,0.35)", "#F4A261", "triangle-up"),
    },
    "pch24": {
        "severity": ("rgba(42,120,214,0.35)", "#2A78D6", "circle"),
        "hate":     ("rgba(42,157,143,0.35)", "#2A9D8F", "triangle-up"),
    },
}
_DEFAULT_STYLE = {
    "severity": ("rgba(100,100,100,0.35)", "#555", "circle"),
    "hate":     ("rgba(180,120,60,0.35)",  "#b47a3c", "triangle-up"),
}

_SCORE_COLUMNS = [
    ("severity_score", "severity", "Antisemitism"),
    ("hateful_score",  "hate",     "General hate"),
]


def create_score_scatter_chart(
    df: pd.DataFrame,
    period: str = "W",  # "W" = weekly, "ME" = month-end
    output_path: str | None = None,
) -> go.Figure:
    """Scatter of every article's severity and hate scores over time.

    Circles = antisemitism score; triangles = general hate score.
    Color encodes site (red/orange = dorzeczy, blue/teal = pch24).
    """
    plot_df = df.copy()
    plot_df["publication_date"] = pd.to_datetime(plot_df["publication_date"])
    plot_df = plot_df.dropna(subset=["publication_date"])

    # Drop keyword-filtered articles (auto-scored 0 without model)
    if "result_json" in plot_df.columns:
        def _was_filtered(rj: object) -> bool:
            return isinstance(rj, dict) and rj.get("explanation", "").startswith("Filtered")
        plot_df = plot_df[~plot_df["result_json"].apply(_was_filtered)]

    period_label = "Weekly" if period == "W" else "Monthly"
    fig = go.Figure()

    sites = sorted(plot_df["site"].dropna().unique())

    for site in sites:
        s_df = plot_df[plot_df["site"] == site].sort_values("publication_date")
        site_style = _STYLE.get(site, _DEFAULT_STYLE)

        for col, kind, label in _SCORE_COLUMNS:
            if col not in s_df.columns:
                continue
            col_df = s_df.dropna(subset=[col])
            if col_df.empty:
                continue

            faint, color, symbol = site_style[kind]
            legend_name = f"{site} — {label}"

            # Raw dots
            customdata = (
                col_df[["title"]].fillna("(no title)").values
                if "title" in col_df.columns
                else [[""] for _ in range(len(col_df))]
            )
            fig.add_trace(go.Scatter(
                x=col_df["publication_date"],
                y=col_df[col],
                mode="markers",
                name=legend_name,
                marker=dict(
                    color=faint, size=7,
                    line=dict(color=color, width=0.8),
                    symbol=symbol,
                ),
                hovertemplate=(
                    "<b>%{customdata[0]}</b><br>"
                    f"{label}: %{{y:.1f}}<br>"
                    "Date: %{x|%Y-%m-%d}<extra></extra>"
                ),
                customdata=customdata,
                legendgroup=legend_name,
                showlegend=True,
            ))

            # Period mean line
            period_mean = (
                col_df.set_index("publication_date")[col]
                .resample(period)
                .mean()
                .dropna()
            )
            if not period_mean.empty:
                fig.add_trace(go.Scatter(
                    x=period_mean.index,
                    y=period_mean.values,
                    mode="lines+markers",
                    name=f"{legend_name} ({period_label.lower()} mean)",
                    line=dict(color=color, width=2.5),
                    marker=dict(color=color, size=5, symbol=symbol),
                    legendgroup=legend_name,
                    showlegend=False,
                    hovertemplate=f"{legend_name} mean: %{{y:.2f}}<extra></extra>",
                ))

    fig.add_vline(
        x=OCT_7.timestamp() * 1000,
        line=dict(color="black", width=2, dash="dash"),
        annotation_text="Oct 7, 2023",
        annotation_position="top right",
    )

    fig.update_layout(
        title=(
            "Per-Article Scores Over Time — Antisemitism (●) vs General Hate (▲) — "
            f"{period_label} mean overlay"
        ),
        xaxis_title="Publication Date",
        yaxis_title="Score (0–10)",
        yaxis=dict(range=[-0.3, 10.3]),
        template="plotly_white",
        height=560,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    fig.update_xaxes(rangeslider_visible=True)

    if output_path:
        fig.write_html(output_path)

    return fig
