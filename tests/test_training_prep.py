from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from deepseekcell_ft.training_prep import inspect_finetune_splits


def _record(
    tissue: str,
    cell_type: str,
    cl_id: str | None,
    markers: list[str],
    source: str = "PanglaoDB",
) -> dict[str, object]:
    return {
        "messages": [
            {"role": "system", "content": "Annotate cell types."},
            {"role": "user", "content": f"Tissue: {tissue}\n\nCluster markers:\n{', '.join(markers)}"},
            {
                "role": "assistant",
                "content": f"Cell type: {cell_type}\nCell Ontology ID: {cl_id or ''}",
            },
        ],
        "metadata": {
            "tissue": tissue,
            "cell_type": cell_type,
            "cell_ontology_id": cl_id,
            "markers": markers,
            "source": source,
        },
    }


def _write_jsonl(path: Path, records: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record) + "\n")


class TrainingPrepTests(unittest.TestCase):
    def test_inspect_finetune_splits_counts_records_and_cl_coverage(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            split_dir = Path(tmpdir) / "splits"
            split_dir.mkdir()
            _write_jsonl(
                split_dir / "train.jsonl",
                [
                    _record("PBMC", "B cell", "CL:0000236", ["MS4A1", "CD79A"]),
                    _record("PBMC", "T cell", "CL:0000084", ["CD3D", "IL7R"]),
                ],
            )
            _write_jsonl(
                split_dir / "validation.jsonl",
                [_record("PBMC", "NK cell", "CL:0000623", ["NKG7", "GNLY"])],
            )
            _write_jsonl(
                split_dir / "test.jsonl",
                [_record("Lung", "Goblet cell", None, ["MUC5AC", "SPDEF"])],
            )
            output = Path(tmpdir) / "preflight.json"

            report = inspect_finetune_splits(split_dir, output_path=output, max_seq_length=512)
            output_exists = output.exists()

        self.assertTrue(output_exists)
        self.assertEqual(report["total"]["records"], 4)
        self.assertEqual(report["splits"]["train"]["records"], 2)
        self.assertEqual(report["total"]["records_with_cl_id"], 3)
        self.assertEqual(report["total"]["cl_coverage"], 0.75)
        self.assertEqual(report["leakage"]["leaked_groups"], 0)
        self.assertIn("Cell Ontology coverage is below 95%", report["warnings"])
        self.assertIn("torch", report["training_dependencies"]["dependencies"])
        self.assertIn("cuda_available", report["hardware"])

    def test_inspect_finetune_splits_reports_group_leakage(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            split_dir = Path(tmpdir) / "splits"
            split_dir.mkdir()
            leaked = _record("PBMC", "B cell", "CL:0000236", ["MS4A1"])
            _write_jsonl(split_dir / "train.jsonl", [leaked])
            _write_jsonl(split_dir / "validation.jsonl", [leaked])
            _write_jsonl(
                split_dir / "test.jsonl",
                [_record("PBMC", "T cell", "CL:0000084", ["CD3D"])],
            )

            report = inspect_finetune_splits(split_dir, max_seq_length=512)

        self.assertEqual(report["leakage"]["leaked_groups"], 1)
        self.assertEqual(report["leakage"]["duplicate_records_across_splits"], 1)
        self.assertIn("metadata groups appear in more than one split", report["warnings"])

    def test_inspect_finetune_splits_can_disable_group_leakage_check(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            split_dir = Path(tmpdir) / "splits"
            split_dir.mkdir()
            _write_jsonl(
                split_dir / "train.jsonl",
                [_record("PBMC", "B cell", "CL:0000236", ["MS4A1"])],
            )
            _write_jsonl(
                split_dir / "validation.jsonl",
                [_record("PBMC", "B cell", "CL:0000236", ["CD79A"])],
            )
            _write_jsonl(
                split_dir / "test.jsonl",
                [_record("PBMC", "B cell", "CL:0000236", ["CD19"])],
            )

            report = inspect_finetune_splits(split_dir, max_seq_length=512, group_by=())

        self.assertFalse(report["leakage"]["group_check_enabled"])
        self.assertEqual(report["leakage"]["leaked_groups"], 0)
        self.assertNotIn("metadata groups appear in more than one split", report["warnings"])


if __name__ == "__main__":
    unittest.main()
