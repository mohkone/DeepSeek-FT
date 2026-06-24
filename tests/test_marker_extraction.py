from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from deepseekcell_ft.marker_extraction import majority_value


class MarkerExtractionTests(unittest.TestCase):
    def test_majority_value_ignores_empty_values_and_reports_fraction(self) -> None:
        label, fraction = majority_value(["B cell", "", None, "T cell", "B cell", "nan"])

        self.assertEqual(label, "B cell")
        self.assertAlmostEqual(fraction, 2 / 3)

    def test_majority_value_handles_no_usable_values(self) -> None:
        label, fraction = majority_value([None, "", "nan"])

        self.assertIsNone(label)
        self.assertIsNone(fraction)


if __name__ == "__main__":
    unittest.main()
