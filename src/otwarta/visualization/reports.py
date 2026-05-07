from datetime import datetime
from pathlib import Path

import pandas as pd

from otwarta.visualization.comparison import create_comparison_chart
from otwarta.visualization.stats import bootstrap_ci, cohens_d, mann_whitney_u
from otwarta.visualization.time_series import create_time_series_chart

OCT_7 = datetime(2023, 10, 7)


def generate_report(
    df: pd.DataFrame,
    output_dir: str = "data/processed",
    cutoff: datetime = OCT_7,
) -> str:
    """Generate full HTML report with embedded charts and statistics."""
    out = Path(output_dir)
    charts_dir = out / "charts"
    charts_dir.mkdir(parents=True, exist_ok=True)

    df = df.dropna(subset=["publication_date", "severity_score"]).copy()
    df["publication_date"] = pd.to_datetime(df["publication_date"])

    pre = df[df["publication_date"] < cutoff]["severity_score"].tolist()
    post = df[df["publication_date"] >= cutoff]["severity_score"].tolist()

    stats = mann_whitney_u(pre, post) if pre and post else {}
    d = cohens_d(pre, post) if pre and post else 0.0
    ci_lo, ci_hi = bootstrap_ci(post) if post else (0.0, 0.0)

    ts_fig = create_time_series_chart(df)
    ts_html = ts_fig.to_html(full_html=False, include_plotlyjs="cdn")
    comp_fig = create_comparison_chart(df, cutoff=cutoff)
    comp_html = comp_fig.to_html(full_html=False, include_plotlyjs=False)

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
  body {{ font-family: sans-serif; max-width: 1200px; margin: 0 auto; padding: 20px; }}
  table {{ border-collapse: collapse; width: 100%; }}
  th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
  th {{ background-color: #f4f4f4; }}
</style>
</head>
<body>
<h1>Antisemitism in Polish Right-Wing Media</h1>
<h2>Pre/Post October 7, 2023 Analysis</h2>
<p>Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>

<h3>Summary Statistics</h3>
<table>
  <tr><th>Metric</th><th>Pre Oct 7</th><th>Post Oct 7</th></tr>
  <tr><td>Articles analyzed</td><td>{len(pre)}</td><td>{len(post)}</td></tr>
  <tr><td>Mean severity score</td><td>{pre_mean:.2f}</td><td>{post_mean:.2f}</td></tr>
  <tr><td>Mann-Whitney U p-value</td><td colspan="2">{p_str}</td></tr>
  <tr><td>Statistically significant?</td><td colspan="2">{sig_str}</td></tr>
  <tr><td>Cohen's d (effect size)</td><td colspan="2">{d:.2f}</td></tr>
  <tr><td>Post-Oct7 mean 95% CI</td><td colspan="2">[{ci_lo:.2f}, {ci_hi:.2f}]</td></tr>
</table>

<h3>Time Series</h3>
{ts_html}

<h3>Distribution Comparison</h3>
{comp_html}
</body>
</html>"""

    report_path = out / "report.html"
    report_path.write_text(html, encoding="utf-8")
    return str(report_path)
