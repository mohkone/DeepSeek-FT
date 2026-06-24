from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from deepseekcell_ft.reporting import write_experiment_summary


class ReportingTests(unittest.TestCase):
    def test_write_experiment_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            predictions = tmpdir_path / "predictions.jsonl"
            preflight = tmpdir_path / "preflight.json"
            output_json = tmpdir_path / "summary.json"
            output_markdown = tmpdir_path / "summary.md"

            with predictions.open("w", encoding="utf-8", newline="\n") as handle:
                handle.write(
                    json.dumps(
                        {
                            "y_true": "B cell",
                            "y_pred": "B cell",
                            "true_cl_id": "CL:0000236",
                            "pred_cl_id": "CL:0000236",
                            "confidence": 0.8,
                            "runtime_seconds": 0.1,
                        }
                    )
                    + "\n"
                )
            preflight.write_text(
                json.dumps(
                    {
                        "split_dir": "splits",
                        "splits": {
                            "train": {"records": 1},
                            "validation": {"records": 1},
                            "test": {"records": 1},
                        },
                        "total": {
                            "records": 3,
                            "unique_labels": 1,
                            "cl_coverage": 1.0,
                            "estimated_tokens": {"max": 128},
                        },
                        "label_overlap": {
                            "validation_labels_seen_in_train": 1,
                            "validation_labels_unseen_in_train": 0,
                            "test_labels_seen_in_train": 1,
                            "test_labels_unseen_in_train": 0,
                        },
                        "leakage": {"duplicate_records_across_splits": 0},
                        "hardware": {"cuda_available": False, "mps_available": False},
                        "training_dependencies": {"missing": []},
                        "warnings": [],
                    }
                ),
                encoding="utf-8",
            )

            summary = write_experiment_summary(
                prediction_specs=[
                    f"deepseek_lora={predictions}",
                    f"qwen25_7b_prompt={predictions}",
                    f"pbmc3k_matrix_singler={predictions}",
                ],
                preflight_specs=[f"label_overlap={preflight}"],
                output_json=output_json,
                output_markdown=output_markdown,
            )
            output_json_exists = output_json.exists()
            output_markdown_exists = output_markdown.exists()

        self.assertEqual(summary["predictions"][0]["accuracy"], 1.0)
        self.assertEqual(summary["predictions"][0]["method"], "DeepSeek-7B LoRA")
        self.assertEqual(summary["predictions"][1]["method"], "Prompt-only Qwen")
        self.assertEqual(summary["predictions"][2]["method"], "SingleR")
        self.assertEqual(summary["preflights"][0]["records"], 3)
        self.assertTrue(output_json_exists)
        self.assertTrue(output_markdown_exists)


if __name__ == "__main__":
    unittest.main()
