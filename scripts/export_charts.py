"""Export all visualization charts to PNG files."""
import json
from pathlib import Path

import pandas as pd
import sqlalchemy as sa

from otwarta.visualization.comparison import create_comparison_chart
from otwarta.visualization.coverage_vs_severity import create_coverage_vs_severity_chart
from otwarta.visualization.mention_frequency import (
    create_frequency_vs_score_chart,
    create_mention_frequency_chart,
)
from otwarta.visualization.score_scatter import create_score_scatter_chart
from otwarta.visualization.site_comparison import create_site_comparison_chart
from otwarta.visualization.time_series import create_time_series_chart
from otwarta.visualization.trope_evolution import create_trope_stacked_area

DB_URL = "sqlite:///./data/raw/otwarta.db"
OUT_DIR = Path("data/processed/charts")


def load_df() -> pd.DataFrame:
    engine = sa.create_engine(DB_URL)
    with engine.connect() as conn:
        rows = conn.execute(sa.text("""
            SELECT
                a.id, a.site, a.url, a.title, a.publication_date,
                r.severity_score, r.hateful_score, r.result_json
            FROM articles a
            JOIN analysis_results r ON r.article_id = a.id
        """)).fetchall()
    df = pd.DataFrame(rows, columns=[
        "id", "site", "url", "title", "publication_date",
        "severity_score", "hateful_score", "result_json",
    ])
    df["publication_date"] = pd.to_datetime(df["publication_date"])
    df["result_json"] = df["result_json"].apply(
        lambda x: json.loads(x) if isinstance(x, str) else x
    )
    return df


def export(fig, name: str) -> None:
    path = OUT_DIR / f"{name}.png"
    fig.write_image(str(path), width=1400, height=600, scale=2)
    print(f"  saved {path}")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print("Loading data...")
    df = load_df()
    print(f"  {len(df)} rows loaded")

    charts = [
        ("01_time_series_all_sites",    lambda: create_time_series_chart(df)),
        ("02_time_series_dorzeczy",     lambda: create_time_series_chart(df, site="dorzeczy")),
        ("03_time_series_pch24",        lambda: create_time_series_chart(df, site="pch24")),
        ("04_monthly_box_comparison",   lambda: create_comparison_chart(df)),
        ("05_mention_frequency",        lambda: create_mention_frequency_chart(df)),
        ("06_frequency_vs_score",       lambda: create_frequency_vs_score_chart(df)),
        ("07_trope_evolution",          lambda: create_trope_stacked_area(df)),
        ("08_site_comparison",          lambda: create_site_comparison_chart(df)),
        ("09_score_scatter_weekly",     lambda: create_score_scatter_chart(df, period="W")),
        ("10_coverage_vs_severity",     lambda: create_coverage_vs_severity_chart(df)),
    ]

    print("Generating charts...")
    for name, fn in charts:
        print(f"  {name}...")
        export(fn(), name)

    print(f"\nDone. {len(charts)} charts saved to {OUT_DIR}/")


if __name__ == "__main__":
    main()
