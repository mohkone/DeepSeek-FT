from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from deepseekcell_ft.dataset_builder import (
    generate_examples,
    load_marker_records,
    perturb_instruction_markers,
    read_jsonl,
    split_grouped_jsonl,
    split_stratified_jsonl,
    write_jsonl,
)


class DatasetBuilderTests(unittest.TestCase):
    def test_load_and_generate_examples(self) -> None:
        records = load_marker_records(ROOT / "data" / "raw" / "marker_evidence.example.csv")
        self.assertGreaterEqual(len(records), 3)

        examples = generate_examples(records[:2], examples_per_record=3, seed=7)
        self.assertEqual(len(examples), 6)
        self.assertTrue(all(example.prompt for example in examples))
        self.assertTrue(all(example.response for example in examples))

    def test_write_chat_jsonl(self) -> None:
        records = load_marker_records(ROOT / "data" / "raw" / "marker_evidence.example.csv")
        examples = generate_examples(records[:1], examples_per_record=2, seed=7)

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "examples.jsonl"
            write_jsonl(examples, path)
            lines = path.read_text(encoding="utf-8").splitlines()

        self.assertEqual(len(lines), 2)
        parsed = json.loads(lines[0])
        self.assertIn("messages", parsed)
        self.assertEqual(parsed["messages"][0]["role"], "system")

    def test_split_grouped_jsonl_prevents_group_leakage(self) -> None:
        records = load_marker_records(ROOT / "data" / "raw" / "marker_evidence.example.csv")
        examples = generate_examples(records[:4], examples_per_record=3, seed=7)

        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = Path(tmpdir) / "examples.jsonl"
            output_dir = Path(tmpdir) / "splits"
            write_jsonl(examples, input_path)
            paths = split_grouped_jsonl(
                input_path,
                output_dir,
                group_by=("tissue", "cell_type", "source"),
                train_ratio=0.5,
                validation_ratio=0.25,
                seed=17,
            )
            split_records = {
                split: read_jsonl(path)
                for split, path in paths.items()
                if split != "manifest"
            }
            manifest_exists = paths["manifest"].exists()

        group_to_split: dict[tuple[str, str, str], str] = {}
        total = 0
        for split_name, records_for_split in split_records.items():
            total += len(records_for_split)
            for record in records_for_split:
                metadata = record["metadata"]
                key = (
                    metadata["tissue"],
                    metadata["cell_type"],
                    metadata["source"],
                )
                if key in group_to_split:
                    self.assertEqual(group_to_split[key], split_name)
                group_to_split[key] = split_name

        self.assertEqual(total, len(examples))
        self.assertTrue(all(records_for_split for records_for_split in split_records.values()))
        self.assertTrue(manifest_exists)

    def test_split_stratified_jsonl_preserves_label_overlap(self) -> None:
        records = []
        for label in ("B cell", "T cell", "NK cell"):
            for index in range(4):
                records.append(
                    {
                        "messages": [
                            {"role": "user", "content": f"{label} markers {index}"},
                            {"role": "assistant", "content": label},
                        ],
                        "metadata": {
                            "tissue": "PBMC",
                            "cell_type": label,
                            "source": "synthetic",
                            "augmentation_index": index,
                        },
                    }
                )

        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = Path(tmpdir) / "examples.jsonl"
            output_dir = Path(tmpdir) / "splits"
            with input_path.open("w", encoding="utf-8", newline="\n") as handle:
                for record in records:
                    handle.write(json.dumps(record) + "\n")
            paths = split_stratified_jsonl(
                input_path,
                output_dir,
                stratify_by="cell_type",
                train_ratio=0.5,
                validation_ratio=0.25,
                seed=17,
            )
            split_labels = {
                split: {
                    record["metadata"]["cell_type"]
                    for record in read_jsonl(path)
                }
                for split, path in paths.items()
                if split != "manifest"
            }
            manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))

        self.assertEqual(split_labels["train"], {"B cell", "T cell", "NK cell"})
        self.assertEqual(split_labels["validation"], {"B cell", "T cell", "NK cell"})
        self.assertEqual(split_labels["test"], {"B cell", "T cell", "NK cell"})
        self.assertEqual(manifest["strata"], 3)
        self.assertEqual(manifest["splits"]["test"]["missing_strata"], 0)

    def test_split_stratified_jsonl_keeps_duplicate_training_text_together(self) -> None:
        records = []
        for index, content in enumerate(("duplicate", "duplicate", "unique one", "unique two")):
            records.append(
                {
                    "messages": [
                        {"role": "user", "content": content},
                        {"role": "assistant", "content": "B cell"},
                    ],
                    "metadata": {
                        "tissue": "PBMC",
                        "cell_type": "B cell",
                        "source": "synthetic",
                        "augmentation_index": index,
                    },
                }
            )

        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = Path(tmpdir) / "examples.jsonl"
            output_dir = Path(tmpdir) / "splits"
            with input_path.open("w", encoding="utf-8", newline="\n") as handle:
                for record in records:
                    handle.write(json.dumps(record) + "\n")
            paths = split_stratified_jsonl(
                input_path,
                output_dir,
                stratify_by="cell_type",
                train_ratio=0.5,
                validation_ratio=0.25,
                seed=17,
            )
            duplicate_splits = []
            for split, path in paths.items():
                if split == "manifest":
                    continue
                for record in read_jsonl(path):
                    if record["messages"][0]["content"] == "duplicate":
                        duplicate_splits.append(split)

        self.assertEqual(len(set(duplicate_splits)), 1)

    def test_perturb_instruction_markers_updates_metadata_and_prompt(self) -> None:
        records = load_marker_records(ROOT / "data" / "raw" / "marker_evidence.example.csv")
        examples = generate_examples(records[:1], examples_per_record=1, seed=7)

        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = Path(tmpdir) / "input.jsonl"
            output_path = Path(tmpdir) / "perturbed.jsonl"
            write_jsonl(examples, input_path)
            summary = perturb_instruction_markers(
                input_path=input_path,
                output_path=output_path,
                marker_db_path=ROOT / "data" / "raw" / "marker_evidence.example.csv",
                drop_rate=1.0,
                add_noise_markers=2,
                min_markers=1,
                seed=3,
            )
            perturbed = read_jsonl(output_path)[0]

        metadata = perturbed["metadata"]
        self.assertEqual(summary["records"], 1)
        self.assertEqual(metadata["cell_type"], examples[0].cell_type)
        self.assertIn("original_markers", metadata)
        self.assertIn("perturbation", metadata)
        self.assertNotEqual(metadata["markers"], metadata["original_markers"])
        self.assertIn("Cluster markers:", perturbed["messages"][1]["content"])


if __name__ == "__main__":
    unittest.main()
