from datetime import datetime
from pathlib import Path

import pandas as pd

from otwarta.visualization.comparison import create_comparison_chart
from otwarta.visualization.mention_frequency import (
    create_frequency_vs_score_chart,
    create_mention_frequency_chart,
)
from otwarta.visualization.score_scatter import create_score_scatter_chart
from otwarta.visualization.site_comparison import create_site_comparison_chart
from otwarta.visualization.stats import bootstrap_ci, cohens_d, mann_whitney_u
from otwarta.visualization.time_series import create_time_series_chart
from otwarta.visualization.trope_evolution import create_trope_stacked_area

OCT_7 = datetime(2023, 10, 7)


def generate_report(
    df: pd.DataFrame,
    output_dir: str = "data/processed",
    cutoff: datetime = OCT_7,
) -> str:
    """Generate full HTML report with embedded charts and statistics."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    df = df.dropna(subset=["publication_date", "severity_score"]).copy()
    df["publication_date"] = pd.to_datetime(df["publication_date"])

    pre = df[df["publication_date"] < cutoff]["severity_score"].tolist()
    post = df[df["publication_date"] >= cutoff]["severity_score"].tolist()

    stats = mann_whitney_u(pre, post) if pre and post else {}
    d = cohens_d(pre, post) if pre and post else 0.0
    ci_lo, ci_hi = bootstrap_ci(post) if post else (0.0, 0.0)

    # --- Charts ---
    ts_html = create_time_series_chart(df).to_html(full_html=False, include_plotlyjs="cdn")
    comp_html = create_comparison_chart(df, cutoff=cutoff).to_html(
        full_html=False, include_plotlyjs=False
    )
    freq_html = create_mention_frequency_chart(df).to_html(
        full_html=False, include_plotlyjs=False
    )
    freq_vs_score_html = create_frequency_vs_score_chart(df).to_html(
        full_html=False, include_plotlyjs=False
    )
    trope_html = create_trope_stacked_area(df).to_html(
        full_html=False, include_plotlyjs=False
    )
    site_cmp_html = create_site_comparison_chart(df).to_html(
        full_html=False, include_plotlyjs=False
    )
    scatter_html = create_score_scatter_chart(df).to_html(
        full_html=False, include_plotlyjs=False
    )

    # --- Stats summary ---
    pre_mean = sum(pre) / len(pre) if pre else 0
    post_mean = sum(post) / len(post) if post else 0
    p_str = f"{stats.get('p_value', 1.0):.4f}" if stats else "N/A"
    sig_str = "Yes (p < 0.05)" if stats.get("significant") else "No"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Antisemitism in Polish Media: Pre/Post Oct 7 Analysis</title>
<style>
  body {{ font-family: sans-serif; max-width: 1400px; margin: 0 auto; padding: 20px; }}
  table {{ border-collapse: collapse; width: 100%; }}
  th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
  th {{ background-color: #f4f4f4; }}
  h2 {{ margin-top: 2em; border-bottom: 2px solid #ddd; padding-bottom: 0.3em; }}
</style>
</head>
<body>
<h1>Antisemitism &amp; Hate Content in Polish Right-Wing Media</h1>
<h2>Pre/Post October 7, 2023 Analysis</h2>
<p>Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')} &mdash;
   Analyzed with local LLMs (primary: llama3.1, secondary: mistral-nemo)</p>

<h2>Summary Statistics — Antisemitism Score</h2>
<table>
  <tr><th>Metric</th><th>Pre Oct 7</th><th>Post Oct 7</th></tr>
  <tr><td>Articles analyzed</td><td>{len(pre)}</td><td>{len(post)}</td></tr>
  <tr><td>Mean severity score</td><td>{pre_mean:.2f}</td><td>{post_mean:.2f}</td></tr>
  <tr><td>Mann-Whitney U p-value</td><td colspan="2">{p_str}</td></tr>
  <tr><td>Statistically significant?</td><td colspan="2">{sig_str}</td></tr>
  <tr><td>Cohen's d (effect size)</td><td colspan="2">{d:.2f}</td></tr>
  <tr><td>Post-Oct7 mean 95% CI</td><td colspan="2">[{ci_lo:.2f}, {ci_hi:.2f}]</td></tr>
</table>

<h2>Chart 1 — Antisemitism &amp; Hate Severity Over Time</h2>
<p>Rolling 30-day average of antisemitism score (solid) and general hate score (dotted),
per site.</p>
{ts_html}

<h2>Chart 2 — Monthly Score Distribution (Box Plots)</h2>
<p>Each box shows the distribution of antisemitism scores within a calendar month.
   Blue = pre Oct 7, 2023; Red = post Oct 7, 2023.</p>
{comp_html}

<h2>Chart 3 — Analyzed Article Frequency</h2>
<p>Monthly count of analyzed articles per site, i.e. the size of the corpus over time.
   Articles without any keyword match are included with score 0.</p>
{freq_html}

<h2>Chart 4 — Frequency vs Antisemitism Score Correlation</h2>
<p>Bar = monthly article count; Line = monthly mean antisemitism score.
   Shows whether spikes in mentions of sensitive keywords coincide with score changes.</p>
{freq_vs_score_html}

<h2>Chart 5 — Antisemitic Trope Category Evolution</h2>
<p>Stacked area: which types of antisemitism appear over time (economic, anti-Zionist,
   conspiracy, historical, religious). Filled in after analysis produces trope_categories data.</p>
{trope_html}

<h2>Chart 6 — Antisemitism vs General Hate Content by Site</h2>
<p>Solid = antisemitism score; Dotted = general hate score
(Ukrainians, Muslims, Roma, LGBT, migrants).
   Compares the intensity of each type of content across the two outlets.</p>
{site_cmp_html}

<h2>Chart 7 — Per-Article Score Scatter (Weekly Mean Overlay)</h2>
<p>Every analyzed article plotted as a dot at its publication date and severity score.
   The solid line is the weekly mean per site. Keyword-filtered (score=0) articles are excluded.
   Use the range slider to zoom in on any period.</p>
{scatter_html}
</body>
</html>"""

    report_path = out / "report.html"
    report_path.write_text(html, encoding="utf-8")
    return str(report_path)
