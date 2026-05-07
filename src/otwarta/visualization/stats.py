from typing import Any

import numpy as np
from scipy import stats


def mann_whitney_u(pre: list[float], post: list[float]) -> dict[str, Any]:
    statistic, p_value = stats.mannwhitneyu(pre, post, alternative="two-sided")
    return {
        "statistic": float(statistic),
        "p_value": float(p_value),
        "significant": bool(p_value < 0.05),
        "n_pre": len(pre),
        "n_post": len(post),
    }


def cohens_d(a: list[float], b: list[float]) -> float:
    a_arr, b_arr = np.array(a, dtype=float), np.array(b, dtype=float)
    pooled_std = np.sqrt((np.std(a_arr, ddof=1) ** 2 + np.std(b_arr, ddof=1) ** 2) / 2)
    if pooled_std == 0:
        return 0.0
    return float((np.mean(b_arr) - np.mean(a_arr)) / pooled_std)


def bootstrap_ci(
    scores: list[float], n_bootstrap: int = 1000, confidence: float = 0.95
) -> tuple[float, float]:
    rng = np.random.default_rng(42)
    arr = np.array(scores, dtype=float)
    means = [
        float(np.mean(rng.choice(arr, size=len(arr), replace=True)))
        for _ in range(n_bootstrap)
    ]
    alpha = 1 - confidence
    return (
        float(np.percentile(means, 100 * alpha / 2)),
        float(np.percentile(means, 100 * (1 - alpha / 2))),
    )
