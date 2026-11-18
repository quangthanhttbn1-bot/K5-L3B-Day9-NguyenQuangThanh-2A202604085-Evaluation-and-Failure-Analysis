"""Statistics students implement (M2 judge calibration, M4 paired bootstrap).

Rules: a judge is a classifier -- measure it like one. A higher mean is not
"better" until the paired CI of the difference excludes 0.
Reference values to self-check are in tests/test_lab9_stats.py.
"""

from __future__ import annotations

from collections.abc import Sequence

POS = "FAIL"   # the judge's job is to FIND failures, so FAIL is the positive class


def confusion(human: Sequence[str], judge: Sequence[str]) -> dict[str, int]:
    """tp/fp/fn/tn with FAIL as positive."""
    if len(human) != len(judge):
        raise ValueError("human and judge labels must have the same length")
    tp = fp = fn = tn = 0
    for h, j in zip(human, judge):
        h_fail, j_fail = h == POS, j == POS
        if h_fail and j_fail:
            tp += 1
        elif j_fail:
            fp += 1
        elif h_fail:
            fn += 1
        else:
            tn += 1
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn}


def precision_recall(human: Sequence[str], judge: Sequence[str]) -> tuple[float, float]:
    cm = confusion(human, judge)
    p_den = cm["tp"] + cm["fp"]
    r_den = cm["tp"] + cm["fn"]
    return (cm["tp"] / p_den if p_den else 0.0,
            cm["tp"] / r_den if r_den else 0.0)


def cohen_kappa(human: Sequence[str], judge: Sequence[str]) -> float:
    """kappa = (p_o - p_e) / (1 - p_e). Raise ValueError when undefined (p_e == 1):
    a constant judge has no signal and must FAIL calibration, not pass on a technicality."""
    cm = confusion(human, judge)
    n = len(human)
    if n == 0:
        raise ValueError("kappa is undefined for an empty sample")
    observed = (cm["tp"] + cm["tn"]) / n
    human_fail = (cm["tp"] + cm["fn"]) / n
    judge_fail = (cm["tp"] + cm["fp"]) / n
    expected = human_fail * judge_fail + (1 - human_fail) * (1 - judge_fail)
    if expected == 1:
        raise ValueError("kappa is undefined when expected agreement is 1")
    return (observed - expected) / (1 - expected)


def rogan_gladen(observed_rate: float, sensitivity: float, specificity: float) -> float:
    """Correct an observed failure rate for judge error; clip to [0, 1]."""
    if not (0 <= observed_rate <= 1 and 0 <= sensitivity <= 1 and 0 <= specificity <= 1):
        raise ValueError("rates must be between 0 and 1")
    denominator = sensitivity + specificity - 1
    if denominator == 0:
        raise ValueError("cannot correct prevalence when judge has no discriminative power")
    estimate = (observed_rate + specificity - 1) / denominator
    return min(1.0, max(0.0, estimate))


def paired_bootstrap(a: Sequence[float], b: Sequence[float], *, n_resamples: int = 1000,
                     rng: int = 2027, confidence: float = 0.95) -> tuple[float, float, float]:
    """a[i], b[i] = per-item mean over seeds, SAME items, SAME order.
    Return (mean(a)-mean(b), lo, hi) with scipy.stats.bootstrap(paired=True, method="percentile",
    rng=numpy.random.default_rng(rng)). If a == b everywhere return (0.0, 0.0, 0.0)."""
    if len(a) != len(b):
        raise ValueError("paired samples must have the same length")
    if not a:
        raise ValueError("paired samples must not be empty")
    if n_resamples <= 0:
        raise ValueError("n_resamples must be positive")
    if not 0 < confidence < 1:
        raise ValueError("confidence must be between 0 and 1")
    differences = [float(x) - float(y) for x, y in zip(a, b)]
    observed = sum(differences) / len(differences)
    if all(d == 0 for d in differences):
        return (0.0, 0.0, 0.0)

    # Resample paired differences so each draw preserves the item-level pairing.
    import numpy as np

    samples = np.asarray(differences, dtype=float)
    generator = np.random.default_rng(rng)
    indices = generator.integers(0, len(samples), size=(n_resamples, len(samples)))
    boot_means = samples[indices].mean(axis=1)
    alpha = (1.0 - confidence) / 2.0
    lo, hi = np.quantile(boot_means, [alpha, 1.0 - alpha], method="linear")
    return (observed, float(lo), float(hi))


def pass_at_k(n: int, c: int, k: int) -> float:
    """Probability that AT LEAST ONE of k trials drawn from n (c of them passing) passes.
    Unbiased estimator (Chen et al. 2021): 1 - C(n-c, k) / C(n, k). Raise ValueError if k > n."""
    # TODO M6
    raise NotImplementedError


def pass_hat_k(n: int, c: int, k: int) -> float:
    """pass^k (tau-bench, Yao et al. 2024): probability that ALL k trials drawn from n pass.
    Unbiased estimator: C(c, k) / C(n, k). Raise ValueError if k > n.
    pass^k <= pass@1 <= pass@k; a reliable agent keeps pass^k close to pass@1."""
    # TODO M6
    raise NotImplementedError
