from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from deepseekcell_ft.cli import (
    benchmark_prompt_command,
    benchmark_sctype_style_command,
    build_parser,
    reparse_predictions_command,
)


class CliTests(unittest.TestCase):
    def test_benchmark_prompt_parser(self) -> None:
        parser = build_parser()
        args = parser.parse_args(
            [
                "benchmark-prompt",
                "--base-model",
                "deepseek-ai/deepseek-llm-7b-chat",
                "--input",
                "data/processed/test.jsonl",
                "--output",
                "outputs/deepseek_prompt_predictions.jsonl",
            ]
        )

        self.assertEqual(args.func, benchmark_prompt_command)
        self.assertEqual(args.max_new_tokens, 128)
        self.assertEqual(args.temperature, 0.0)

    def test_benchmark_sctype_style_parser(self) -> None:
        parser = build_parser()
        args = parser.parse_args(
            [
                "benchmark-sctype-style",
                "--marker-db",
                "data/raw/marker_evidence.example.csv",
                "--input",
                "data/processed/test.jsonl",
                "--output",
                "outputs/sctype_predictions.jsonl",
            ]
        )

        self.assertEqual(args.func, benchmark_sctype_style_command)
        self.assertEqual(args.negative_weight, 1.0)
        self.assertEqual(args.confidence_bins, 10)

    def test_reparse_predictions_parser(self) -> None:
        parser = build_parser()
        args = parser.parse_args(
            [
                "reparse-predictions",
                "--predictions",
                "outputs/raw.jsonl",
                "--output",
                "outputs/reparsed.jsonl",
            ]
        )

        self.assertEqual(args.func, reparse_predictions_command)
        self.assertEqual(args.predictions, Path("outputs/raw.jsonl"))


if __name__ == "__main__":
    unittest.main()
