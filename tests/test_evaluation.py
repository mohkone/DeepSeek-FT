from __future__ import annotations

import sys
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from deepseekcell_ft.evaluation import (
    analyze_prediction_records,
    analyze_rerank_prediction_records,
    evaluate_predictions,
    harmonize_prediction_labels,
    map_prediction_ontology_ids,
    reparse_prediction_records,
    sync_prediction_gold_ontology_ids,
)


class EvaluationTests(unittest.TestCase):
    def test_evaluate_predictions(self) -> None:
        metrics = evaluate_predictions(
            [
                {
                    "y_true": "CD4+ T cell",
                    "y_pred": "CD4+ T cell",
                    "true_cl_id": "CL:0000624",
                    "pred_cl_id": "CL:0000624",
                    "confidence": 0.9,
                    "runtime_seconds": 0.1,
                },
                {
                    "y_true": "B cell",
                    "y_pred": "CD4+ T cell",
                    "true_cl_id": "CL:0000236",
                    "pred_cl_id": "CL:0000624",
                    "confidence": 0.6,
                    "runtime_seconds": 0.2,
                },
            ]
        )
        self.assertEqual(metrics["n"], 2)
        self.assertAlmostEqual(metrics["accuracy"], 0.5)
        self.assertAlmostEqual(metrics["cell_ontology_accuracy"], 0.5)
        self.assertIsNotNone(metrics["expected_calibration_error"])

    def test_ontology_accuracy_is_null_when_no_predictions_have_cl_ids(self) -> None:
        metrics = evaluate_predictions(
            [
                {
                    "y_true": "B cell",
                    "y_pred": "B cell",
                    "true_cl_id": "CL:0000236",
                    "pred_cl_id": None,
                },
                {
                    "y_true": "T cell",
                    "y_pred": "T cell",
                    "true_cl_id": "CL:0000084",
                    "pred_cl_id": None,
                },
            ]
        )

        self.assertIsNone(metrics["cell_ontology_accuracy"])

    def test_analyze_prediction_records_writes_error_examples(self) -> None:
        records = [
            {
                "tissue": "PBMC",
                "markers": ["IL7R", "LTB"],
                "y_true": "CD4+ T cell",
                "y_pred": "B cell",
                "true_cl_id": "CL:0000624",
                "pred_cl_id": None,
                "confidence": None,
                "raw_response": "Cell type: B cell",
            },
            {
                "tissue": "PBMC",
                "markers": ["MS4A1"],
                "y_true": "B cell",
                "y_pred": "B cell",
                "true_cl_id": "CL:0000236",
                "pred_cl_id": "CL:0000236",
                "confidence": 0.8,
            },
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "errors.csv"
            analysis = analyze_prediction_records(records, examples_output=output)
            text = output.read_text(encoding="utf-8")

        self.assertEqual(analysis["errors"], 1)
        self.assertEqual(analysis["records_with_pred_cl_id"], 1)
        self.assertEqual(analysis["missing_confidence"], 1)
        self.assertIn("CD4+ T cell", text)

    def test_map_prediction_ontology_ids_overwrites_generated_ids(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            marker_db = tmpdir_path / "markers.csv"
            predictions = tmpdir_path / "predictions.jsonl"
            output = tmpdir_path / "mapped.jsonl"

            marker_db.write_text(
                "\n".join(
                    [
                        "tissue,cell_type,cell_ontology_id,markers,source,evidence",
                        'PBMC,B cell,CL:0000236,"MS4A1,CD79A",Example,canonical',
                    ]
                ),
                encoding="utf-8",
            )
            predictions.write_text(
                json.dumps(
                    {
                        "y_true": "B cell",
                        "y_pred": "B cell",
                        "true_cl_id": "CL:0000236",
                        "pred_cl_id": "CL:0000624",
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            summary = map_prediction_ontology_ids(predictions, marker_db, output)
            mapped = json.loads(output.read_text(encoding="utf-8").splitlines()[0])

        self.assertEqual(summary["mapped"], 1)
        self.assertEqual(summary["overwritten"], 1)
        self.assertEqual(summary["after_cell_ontology_accuracy"], 1.0)
        self.assertEqual(mapped["original_pred_cl_id"], "CL:0000624")
        self.assertEqual(mapped["pred_cl_id"], "CL:0000236")

    def test_map_prediction_ontology_ids_uses_conservative_label_variants(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            marker_db = tmpdir_path / "markers.csv"
            predictions = tmpdir_path / "predictions.jsonl"
            output = tmpdir_path / "mapped.jsonl"

            marker_db.write_text(
                "\n".join(
                    [
                        "tissue,cell_type,cell_ontology_id,markers,source,evidence",
                        'PBMC,CD4 T cells,CL:0000624,"CD3D,IL7R",Example,canonical',
                        'PBMC,Dendritic cells,CL:0000451,"FCER1A,CST3",Example,canonical',
                    ]
                ),
                encoding="utf-8",
            )
            predictions.write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "y_true": "CD4 T cells",
                                "y_pred": "CD4+ T-cells",
                                "true_cl_id": "CL:0000624",
                                "pred_cl_id": None,
                            }
                        ),
                        json.dumps(
                            {
                                "y_true": "Dendritic cells",
                                "y_pred": "DC",
                                "true_cl_id": "CL:0000451",
                                "pred_cl_id": None,
                            }
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            summary = map_prediction_ontology_ids(predictions, marker_db, output)
            mapped = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]

        self.assertEqual(summary["mapped"], 2)
        self.assertEqual(summary["after_cell_ontology_accuracy"], 1.0)
        self.assertEqual(mapped[0]["pred_cl_id"], "CL:0000624")
        self.assertEqual(mapped[1]["pred_cl_id"], "CL:0000451")

    def test_map_prediction_ontology_ids_does_not_broaden_ambiguous_labels(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            marker_db = tmpdir_path / "markers.csv"
            predictions = tmpdir_path / "predictions.jsonl"
            output = tmpdir_path / "mapped.jsonl"

            marker_db.write_text(
                "\n".join(
                    [
                        "tissue,cell_type,cell_ontology_id,markers,source,evidence",
                        'PBMC,CD14+ Monocytes,CL:0001054,"LYZ,LST1",Example,canonical',
                        'PBMC,FCGR3A+ Monocytes,CL:0002396,"FCGR3A,MS4A7",Example,canonical',
                    ]
                ),
                encoding="utf-8",
            )
            predictions.write_text(
                json.dumps(
                    {
                        "y_true": "CD14+ Monocytes",
                        "y_pred": "Monocytes",
                        "true_cl_id": "CL:0001054",
                        "pred_cl_id": None,
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            summary = map_prediction_ontology_ids(predictions, marker_db, output)
            mapped = json.loads(output.read_text(encoding="utf-8").splitlines()[0])

        self.assertEqual(summary["mapped"], 0)
        self.assertEqual(summary["unmapped"], 1)
        self.assertIsNone(mapped.get("pred_cl_id"))
        self.assertEqual(mapped["pred_cl_id_source"], "unmapped_predicted_label")

    def test_harmonize_prediction_labels_uses_explicit_mapping(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            predictions = tmpdir_path / "predictions.jsonl"
            mapping = tmpdir_path / "mapping.csv"
            marker_db = tmpdir_path / "markers.csv"
            output = tmpdir_path / "harmonized.jsonl"

            predictions.write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "y_true": "CD4 T cells",
                                "y_pred": "Naive CD4+ T cells",
                                "true_cl_id": "CL:0000624",
                                "pred_cl_id": None,
                            }
                        ),
                        json.dumps(
                            {
                                "y_true": "CD8 T cells",
                                "y_pred": "CD8+ NKT-like cells",
                                "true_cl_id": "CL:0000625",
                                "pred_cl_id": None,
                            }
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            mapping.write_text(
                "\n".join(
                    [
                        "predicted_label,harmonized_label,harmonized_cl_id,notes",
                        "Naive CD4+ T cells,CD4 T cells,CL:0000624,subtype parent",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            marker_db.write_text(
                "\n".join(
                    [
                        "tissue,cell_type,cell_ontology_id,markers,source,evidence",
                        'PBMC,CD4 T cells,CL:0000624,"CD3D,IL7R",Example,canonical',
                        'PBMC,CD8 T cells,CL:0000625,"CD8A,CD8B",Example,canonical',
                    ]
                ),
                encoding="utf-8",
            )

            summary = harmonize_prediction_labels(predictions, mapping, output, marker_db)
            rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]

        self.assertEqual(summary["harmonized"], 1)
        self.assertEqual(summary["unchanged"], 1)
        self.assertEqual(summary["after_accuracy"], 0.5)
        self.assertEqual(summary["after_cell_ontology_accuracy"], 0.5)
        self.assertEqual(rows[0]["y_pred"], "CD4 T cells")
        self.assertEqual(rows[0]["original_y_pred"], "Naive CD4+ T cells")
        self.assertEqual(rows[0]["pred_cl_id"], "CL:0000624")
        self.assertEqual(rows[1]["y_pred"], "CD8+ NKT-like cells")

    def test_reparse_prediction_records_updates_raw_response_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            predictions = tmpdir_path / "predictions.jsonl"
            output = tmpdir_path / "reparsed.jsonl"
            predictions.write_text(
                json.dumps(
                    {
                        "y_true": "Neutrophils",
                        "y_pred": "** Neutrophil",
                        "true_cl_id": "CL:0000775",
                        "pred_cl_id": None,
                        "confidence": None,
                        "runtime_seconds": 1.0,
                        "raw_response": "- **Cell Type:** Neutrophils\n"
                        "- **Confidence Score:** 0.95\n"
                        "- **Biological Reasoning:** CD33 supports this label.",
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            summary = reparse_prediction_records(predictions, output)
            reparsed = json.loads(output.read_text(encoding="utf-8").splitlines()[0])

        self.assertEqual(summary["after_accuracy"], 1.0)
        self.assertEqual(reparsed["y_pred"], "Neutrophils")
        self.assertAlmostEqual(reparsed["confidence"], 0.95)
        self.assertEqual(reparsed["original_y_pred"], "** Neutrophil")

    def test_sync_prediction_gold_ontology_ids_refreshes_true_cl_ids(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            predictions = tmpdir_path / "predictions.jsonl"
            instructions = tmpdir_path / "test.jsonl"
            output = tmpdir_path / "synced.jsonl"
            predictions.write_text(
                json.dumps(
                    {
                        "tissue": "PBMC",
                        "markers": ["MS4A1"],
                        "y_true": "B cell",
                        "y_pred": "B cell",
                        "true_cl_id": None,
                        "pred_cl_id": "CL:0000236",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            instructions.write_text(
                json.dumps(
                    {
                        "messages": [],
                        "metadata": {
                            "tissue": "PBMC",
                            "markers": ["MS4A1"],
                            "cell_type": "B cell",
                            "cell_ontology_id": "CL:0000236",
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            summary = sync_prediction_gold_ontology_ids(predictions, instructions, output)
            synced = json.loads(output.read_text(encoding="utf-8").splitlines()[0])

        self.assertEqual(summary["filled_true_cl_ids"], 1)
        self.assertEqual(summary["after_records_with_true_cl_id"], 1)
        self.assertEqual(summary["after_cell_ontology_accuracy"], 1.0)
        self.assertEqual(synced["true_cl_id"], "CL:0000236")
        self.assertIsNone(synced["original_true_cl_id"])

    def test_analyze_rerank_prediction_records_reports_harm_and_oracle(self) -> None:
        records = [
            {
                "tissue": "PBMC",
                "markers": ["IL7R"],
                "y_true": "CD4+ T cell",
                "y_pred": "B cell",
                "true_cl_id": "CL:0000624",
                "pred_cl_id": "CL:0000236",
                "selection_source": "candidate_number",
                "candidates": [
                    {"rank": 1, "cell_type": "CD4+ T cell", "cell_ontology_id": "CL:0000624"},
                    {"rank": 2, "cell_type": "B cell", "cell_ontology_id": "CL:0000236"},
                ],
            },
            {
                "tissue": "PBMC",
                "markers": ["MS4A1"],
                "y_true": "B cell",
                "y_pred": "B cell",
                "true_cl_id": "CL:0000236",
                "pred_cl_id": "CL:0000236",
                "selection_source": "cell_type_label",
                "candidates": [
                    {"rank": 1, "cell_type": "T cell", "cell_ontology_id": "CL:0000084"},
                    {"rank": 2, "cell_type": "B cell", "cell_ontology_id": "CL:0000236"},
                ],
            },
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "harm.csv"
            analysis = analyze_rerank_prediction_records(records, examples_output=output)
            text = output.read_text(encoding="utf-8")

        self.assertEqual(analysis["records_with_candidates"], 2)
        self.assertAlmostEqual(analysis["top1_candidate_accuracy"], 0.5)
        self.assertAlmostEqual(analysis["oracle_top_k_accuracy"], 1.0)
        self.assertEqual(analysis["reranker_harmed_top1"], 1)
        self.assertEqual(analysis["reranker_fixed_top1"], 1)
        self.assertIn("CD4+ T cell", text)


if __name__ == "__main__":
    unittest.main()
