"""Paired statistical comparisons for annotation predictions."""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any

from .evaluation import accuracy, macro_f1
from .normalization import normalize_cell_label


@dataclass(frozen=True)
class PairedComparison:
    """Summary of a paired method comparison on the same examples."""

    n: int
    method_a_accuracy: float
    method_b_accuracy: float
    accuracy_delta: float
    accuracy_delta_ci_low: float
    accuracy_delta_ci_high: float
    method_a_macro_f1: float
    method_b_macro_f1: float
    macro_f1_delta: float
    macro_f1_delta_ci_low: float
    macro_f1_delta_ci_high: float
    a_only_correct: int
    b_only_correct: int
    both_correct: int
    both_wrong: int
    mcnemar_p_value: float | None


def _correct_flags(records: list[dict[str, Any]]) -> list[bool]:
    return [
        normalize_cell_label(str(record.get("y_true", "")))
        == normalize_cell_label(str(record.get("y_pred", "")))
        for record in records
    ]


def _labels(records: list[dict[str, Any]]) -> tuple[list[str], list[str]]:
    return (
        [str(record.get("y_true", "")) for record in records],
        [str(record.get("y_pred", "")) for record in records],
    )


def exact_mcnemar_p_value(a_only_correct: int, b_only_correct: int) -> float | None:
    """Two-sided exact McNemar p-value using the binomial distribution."""

    discordant = a_only_correct + b_only_correct
    if discordant == 0:
        return None
    tail = min(a_only_correct, b_only_correct)
    probability = sum(_binomial_pmf(discordant, k, 0.5) for k in range(tail + 1))
    return min(1.0, 2.0 * probability)


def _binomial_pmf(n: int, k: int, p: float) -> float:
    from math import comb

    return comb(n, k) * (p**k) * ((1.0 - p) ** (n - k))


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    index = (len(values) - 1) * percentile
    lower = int(index)
    upper = min(lower + 1, len(values) - 1)
    weight = index - lower
    return values[lower] * (1.0 - weight) + values[upper] * weight


def _subset(records: list[dict[str, Any]], indices: list[int]) -> list[dict[str, Any]]:
    return [records[index] for index in indices]


def _metric_delta(
    records_a: list[dict[str, Any]],
    records_b: list[dict[str, Any]],
    metric: str,
) -> float:
    y_true_a, y_pred_a = _labels(records_a)
    y_true_b, y_pred_b = _labels(records_b)
    if y_true_a != y_true_b:
        raise ValueError("paired records must have identical gold labels in the same order")
    if metric == "accuracy":
        return accuracy(y_true_a, y_pred_a) - accuracy(y_true_b, y_pred_b)
    if metric == "macro_f1":
        return macro_f1(y_true_a, y_pred_a) - macro_f1(y_true_b, y_pred_b)
    raise ValueError(f"unsupported metric: {metric}")


def _bootstrap_delta_ci(
    records_a: list[dict[str, Any]],
    records_b: list[dict[str, Any]],
    metric: str,
    *,
    n_bootstrap: int,
    seed: int,
) -> tuple[float, float]:
    rng = random.Random(seed)
    n = len(records_a)
    deltas: list[float] = []
    for _ in range(n_bootstrap):
        indices = [rng.randrange(n) for _ in range(n)]
        deltas.append(_metric_delta(_subset(records_a, indices), _subset(records_b, indices), metric))
    return _percentile(deltas, 0.025), _percentile(deltas, 0.975)


def paired_comparison(
    records_a: list[dict[str, Any]],
    records_b: list[dict[str, Any]],
    *,
    n_bootstrap: int = 2000,
    seed: int = 13,
) -> PairedComparison:
    """Compare two prediction sets generated for the same records."""

    if len(records_a) != len(records_b):
        raise ValueError("paired prediction files must contain the same number of records")
    if not records_a:
        raise ValueError("paired prediction files must not be empty")

    y_true_a, y_pred_a = _labels(records_a)
    y_true_b, y_pred_b = _labels(records_b)
    if y_true_a != y_true_b:
        raise ValueError("paired records must have identical gold labels in the same order")

    flags_a = _correct_flags(records_a)
    flags_b = _correct_flags(records_b)
    a_only = sum(a and not b for a, b in zip(flags_a, flags_b, strict=True))
    b_only = sum(b and not a for a, b in zip(flags_a, flags_b, strict=True))
    both_correct = sum(a and b for a, b in zip(flags_a, flags_b, strict=True))
    both_wrong = sum((not a) and (not b) for a, b in zip(flags_a, flags_b, strict=True))

    acc_a = accuracy(y_true_a, y_pred_a)
    acc_b = accuracy(y_true_b, y_pred_b)
    f1_a = macro_f1(y_true_a, y_pred_a)
    f1_b = macro_f1(y_true_b, y_pred_b)
    acc_ci = _bootstrap_delta_ci(
        records_a,
        records_b,
        "accuracy",
        n_bootstrap=n_bootstrap,
        seed=seed,
    )
    f1_ci = _bootstrap_delta_ci(
        records_a,
        records_b,
        "macro_f1",
        n_bootstrap=n_bootstrap,
        seed=seed + 1,
    )

    return PairedComparison(
        n=len(records_a),
        method_a_accuracy=acc_a,
        method_b_accuracy=acc_b,
        accuracy_delta=acc_a - acc_b,
        accuracy_delta_ci_low=acc_ci[0],
        accuracy_delta_ci_high=acc_ci[1],
        method_a_macro_f1=f1_a,
        method_b_macro_f1=f1_b,
        macro_f1_delta=f1_a - f1_b,
        macro_f1_delta_ci_low=f1_ci[0],
        macro_f1_delta_ci_high=f1_ci[1],
        a_only_correct=a_only,
        b_only_correct=b_only,
        both_correct=both_correct,
        both_wrong=both_wrong,
        mcnemar_p_value=exact_mcnemar_p_value(a_only, b_only),
    )
