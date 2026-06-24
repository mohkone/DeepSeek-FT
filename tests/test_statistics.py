from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from deepseekcell_ft.statistics import exact_mcnemar_p_value, paired_comparison


class StatisticsTests(unittest.TestCase):
    def test_exact_mcnemar_p_value(self) -> None:
        self.assertIsNone(exact_mcnemar_p_value(0, 0))
        self.assertAlmostEqual(exact_mcnemar_p_value(3, 0), 0.25)
        self.assertAlmostEqual(exact_mcnemar_p_value(2, 2), 1.0)

    def test_paired_comparison(self) -> None:
        records_a = [
            {"y_true": "B cell", "y_pred": "B cell"},
            {"y_true": "T cell", "y_pred": "T cell"},
            {"y_true": "NK cell", "y_pred": "B cell"},
        ]
        records_b = [
            {"y_true": "B cell", "y_pred": "B cell"},
            {"y_true": "T cell", "y_pred": "B cell"},
            {"y_true": "NK cell", "y_pred": "NK cell"},
        ]

        result = paired_comparison(records_a, records_b, n_bootstrap=100, seed=1)

        self.assertEqual(result.n, 3)
        self.assertAlmostEqual(result.method_a_accuracy, 2 / 3)
        self.assertAlmostEqual(result.method_b_accuracy, 2 / 3)
        self.assertEqual(result.a_only_correct, 1)
        self.assertEqual(result.b_only_correct, 1)
        self.assertEqual(result.both_correct, 1)
        self.assertEqual(result.both_wrong, 0)


if __name__ == "__main__":
    unittest.main()
