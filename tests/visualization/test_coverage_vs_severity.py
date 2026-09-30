import pandas as pd

from otwarta.visualization.coverage_vs_severity import monthly_coverage_and_severity


def test_monthly_shares_per_site():
    df = pd.DataFrame(
        {
            "site": ["a", "a", "a", "a", "b"],
            "publication_date": [
                "2023-10-01", "2023-10-15", "2023-10-20", "2023-10-31", "2023-10-02",
            ],
            "severity_score": [0.0, 5.0, 4.0, 1.0, 0.0],
            "result_json": [
                {"is_about_israel_gaza": True},
                '{"is_about_israel_gaza": true}',
                {},
                None,
                {"is_about_israel_gaza": False},
            ],
        }
    )
    out = monthly_coverage_and_severity(df).set_index("site")
    assert out.loc["a", "pct_israel_gaza"] == 50.0
    assert out.loc["a", "pct_severity_ge4"] == 50.0
    assert out.loc["b", "pct_israel_gaza"] == 0.0
