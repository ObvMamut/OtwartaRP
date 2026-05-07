import numpy as np
import pytest

from otwarta.visualization.stats import bootstrap_ci, cohens_d, mann_whitney_u


def test_mann_whitney_detects_significant_difference():
    pre = [0.5, 1.2, 0.8, 1.0, 0.3, 0.7, 0.9, 1.1, 0.6, 0.4]
    post = [5.5, 6.2, 7.8, 5.0, 6.3, 7.7, 6.9, 5.1, 6.6, 7.4]
    result = mann_whitney_u(pre, post)
    assert result["p_value"] < 0.05
    assert result["statistic"] is not None
    assert result["significant"] is True


def test_cohens_d_zero_for_equal_groups():
    a = [1.0, 2.0, 3.0, 4.0, 5.0]
    b = [1.0, 2.0, 3.0, 4.0, 5.0]
    assert cohens_d(a, b) == pytest.approx(0.0, abs=1e-10)


def test_bootstrap_ci_returns_tuple():
    scores = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
    lo, hi = bootstrap_ci(scores, n_bootstrap=100)
    assert lo <= np.mean(scores) <= hi
    assert lo < hi
