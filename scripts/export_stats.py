"""Export aggregated, text-free statistics to CSV (monthly series + pre/post tests)."""
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
from export_charts import load_df

from otwarta.visualization.stats import bootstrap_ci, cohens_d, mann_whitney_u

OUT_DIR = Path("data/processed")
OCT_7 = datetime(2023, 10, 7)
WINDOW = timedelta(days=60)
FILTERED_EXPLANATION = "Filtered: no relevant keywords"


def add_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["model_scored"] = df["result_json"].apply(
        lambda r: r.get("explanation") != FILTERED_EXPLANATION
    )
    df["about_israel_gaza"] = df["result_json"].apply(
        lambda r: bool(r.get("is_about_israel_gaza"))
    )
    df["post"] = df["publication_date"] >= OCT_7
    return df


def monthly(df: pd.DataFrame) -> pd.DataFrame:
    g = df.groupby(["site", df["publication_date"].dt.strftime("%Y-%m").rename("month")])
    return g.agg(
        n=("severity_score", "size"),
        n_model_scored=("model_scored", "sum"),
        mean_severity=("severity_score", "mean"),
        mean_hateful=("hateful_score", "mean"),
        share_severity_ge4=("severity_score", lambda s: (s >= 4).mean()),
        share_about_israel_gaza=("about_israel_gaza", "mean"),
    ).round(4).reset_index()


def prepost_row(site: str, subset: str, df: pd.DataFrame) -> dict[str, object]:
    pre = df.loc[~df["post"], "severity_score"].tolist()
    post = df.loc[df["post"], "severity_score"].tolist()
    mw = mann_whitney_u(pre, post)
    pre_lo, pre_hi = bootstrap_ci(pre)
    post_lo, post_hi = bootstrap_ci(post)
    return {
        "site": site,
        "subset": subset,
        "n_pre": mw["n_pre"],
        "n_post": mw["n_post"],
        "mean_pre": round(sum(pre) / len(pre), 4),
        "mean_post": round(sum(post) / len(post), 4),
        "mean_pre_ci95": f"[{pre_lo:.3f}, {pre_hi:.3f}]",
        "mean_post_ci95": f"[{post_lo:.3f}, {post_hi:.3f}]",
        "share_ge4_pre": round(sum(s >= 4 for s in pre) / len(pre), 4),
        "share_ge4_post": round(sum(s >= 4 for s in post) / len(post), 4),
        "share_ge7_pre": round(sum(s >= 7 for s in pre) / len(pre), 4),
        "share_ge7_post": round(sum(s >= 7 for s in post) / len(post), 4),
        "mann_whitney_u": mw["statistic"],
        "p_value": mw["p_value"],
        "cohens_d": round(cohens_d(pre, post), 4),
    }


def prepost(df: pd.DataFrame) -> pd.DataFrame:
    subsets = {
        "all_articles": df,
        "model_scored_only": df[df["model_scored"]],
        "window_pm60d": df[
            (df["publication_date"] >= OCT_7 - WINDOW) & (df["publication_date"] < OCT_7 + WINDOW)
        ],
    }
    rows = []
    for subset, sdf in subsets.items():
        for site in [*sorted(sdf["site"].unique()), "all"]:
            site_df = sdf if site == "all" else sdf[sdf["site"] == site]
            rows.append(prepost_row(site, subset, site_df))
    return pd.DataFrame(rows)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df = add_columns(load_df())
    print(f"  {len(df)} rows loaded")

    monthly(df).to_csv(OUT_DIR / "monthly_stats.csv", index=False)
    tests = prepost(df)
    tests.to_csv(OUT_DIR / "prepost_tests.csv", index=False)
    print(tests.to_string(index=False))
    print(f"\nSaved monthly_stats.csv and prepost_tests.csv to {OUT_DIR}/")


if __name__ == "__main__":
    main()
