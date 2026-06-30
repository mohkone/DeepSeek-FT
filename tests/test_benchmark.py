from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from deepseekcell_ft.benchmark import (
    run_annotation_benchmark,
    run_marker_overlap_benchmark,
    run_sctype_style_benchmark,
)
from deepseekcell_ft.dataset_builder import generate_examples, load_marker_records, write_jsonl
from deepseekcell_ft.schemas import AnnotationPrediction
from deepseekcell_ft.annotation import (
    MarkerOverlapAnnotator,
    ScTypeStyleAnnotator,
    build_candidate_rerank_prompt,
    choose_candidate_from_response,
)


class StaticAnnotator:
    def predict(self, tissue: str, markers: list[str]) -> AnnotationPrediction:
        return AnnotationPrediction(
            cell_type="CD4+ T cell",
            cell_ontology_id="CL:0000624",
            confidence=0.91,
            reasoning=f"Static prediction for {tissue}.",
            raw_response="Cell type: CD4+ T cell\nCell Ontology ID: CL:0000624\nConfidence: 0.91",
            runtime_seconds=0.01,
        )


class BenchmarkTests(unittest.TestCase):
    def test_marker_overlap_rank_candidates(self) -> None:
        marker_db = ROOT / "data" / "raw" / "marker_evidence.example.csv"
        annotator = MarkerOverlapAnnotator(load_marker_records(marker_db))
        candidates = annotator.rank_candidates("PBMC", ["IL7R", "LTB", "IL32"], top_k=3)

        self.assertEqual(candidates[0]["cell_type"], "CD4+ T cell")
        self.assertEqual(candidates[0]["rank"], 1)
        self.assertIn("IL7R", candidates[0]["overlap"])

    def test_sctype_predicts_from_positive_marker_score(self) -> None:
        marker_db = ROOT / "data" / "raw" / "marker_evidence.example.csv"
        annotator = ScTypeStyleAnnotator(load_marker_records(marker_db))
        prediction = annotator.predict("PBMC", ["IL7R", "LTB", "IL32"])

        self.assertEqual(prediction.cell_type, "CD4+ T cell")
        self.assertEqual(prediction.cell_ontology_id, "CL:0000624")
        self.assertIn("scType-style score", prediction.raw_response or "")

    def test_sctype_negative_markers_penalize_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            marker_db = Path(tmpdir) / "markers.csv"
            marker_db.write_text(
                "\n".join(
                    [
                        "tissue,cell_type,cell_ontology_id,markers,negative_markers",
                        'PBMC,Target cell,CL:0000001,"GENEA, GENEB",GENEX',
                        'PBMC,Distractor cell,CL:0000002,"GENEA, GENEX",GENEB',
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            annotator = ScTypeStyleAnnotator(load_marker_records(marker_db))
            candidates = annotator.rank_candidates("PBMC", ["GENEA", "GENEB"], top_k=2)

        self.assertEqual(candidates[0]["cell_type"], "Target cell")
        self.assertEqual(candidates[1]["cell_type"], "Distractor cell")
        self.assertIn("GENEB", candidates[1]["negative_overlap"])

    def test_candidate_rerank_response_uses_candidate_number(self) -> None:
        candidates = [
            {
                "rank": 1,
                "cell_type": "B cell",
                "cell_ontology_id": "CL:0000236",
                "marker_score": 0.2,
                "overlap": ["MS4A1"],
            },
            {
                "rank": 2,
                "cell_type": "CD4+ T cell",
                "cell_ontology_id": "CL:0000624",
                "marker_score": 0.1,
                "overlap": ["IL7R"],
            },
        ]
        prompt = build_candidate_rerank_prompt("PBMC", ["IL7R", "LTB"], candidates)
        candidate, source, parsed = choose_candidate_from_response(
            "Candidate: 2\nCell type: CD4+ T cell\nConfidence: 0.72",
            candidates,
        )

        self.assertIn("Candidate cell types", prompt)
        self.assertEqual(source, "candidate_number")
        self.assertEqual(candidate["cell_ontology_id"], "CL:0000624")
        self.assertAlmostEqual(parsed.confidence or 0.0, 0.72)

    def test_candidate_rerank_response_falls_back_to_top_candidate(self) -> None:
        candidates = [
            {
                "rank": 1,
                "cell_type": "B cell",
                "cell_ontology_id": "CL:0000236",
                "marker_score": 0.2,
                "overlap": ["MS4A1"],
            }
        ]

        candidate, source, _ = choose_candidate_from_response("Cell type: Plasma cell", candidates)

        self.assertEqual(source, "fallback_top_candidate")
        self.assertEqual(candidate["cell_type"], "B cell")

    def test_marker_overlap_benchmark_writes_predictions(self) -> None:
        marker_db = ROOT / "data" / "raw" / "marker_evidence.example.csv"
        records = load_marker_records(marker_db)
        examples = generate_examples(records[:1], examples_per_record=2, seed=11)

        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = Path(tmpdir) / "input.jsonl"
            output_path = Path(tmpdir) / "predictions.jsonl"
            write_jsonl(examples, input_path)
            predictions = run_marker_overlap_benchmark(marker_db, input_path, output_path)
            lines = output_path.read_text(encoding="utf-8").splitlines()

        self.assertEqual(len(predictions), 2)
        self.assertEqual(len(lines), 2)
        self.assertEqual(json.loads(lines[0])["y_pred"], "CD4+ T cell")

    def test_sctype_benchmark_writes_predictions(self) -> None:
        marker_db = ROOT / "data" / "raw" / "marker_evidence.example.csv"
        records = load_marker_records(marker_db)
        examples = generate_examples(records[:1], examples_per_record=2, seed=11)

        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = Path(tmpdir) / "input.jsonl"
            output_path = Path(tmpdir) / "predictions.jsonl"
            write_jsonl(examples, input_path)
            predictions = run_sctype_style_benchmark(marker_db, input_path, output_path)
            lines = output_path.read_text(encoding="utf-8").splitlines()

        self.assertEqual(len(predictions), 2)
        self.assertEqual(len(lines), 2)
        self.assertEqual(json.loads(lines[0])["y_pred"], "CD4+ T cell")

    def test_annotation_benchmark_writes_raw_response(self) -> None:
        marker_db = ROOT / "data" / "raw" / "marker_evidence.example.csv"
        records = load_marker_records(marker_db)
        examples = generate_examples(records[:1], examples_per_record=1, seed=11)

        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = Path(tmpdir) / "input.jsonl"
            output_path = Path(tmpdir) / "predictions.jsonl"
            write_jsonl(examples, input_path)
            predictions = run_annotation_benchmark(StaticAnnotator(), input_path, output_path)
            written = json.loads(output_path.read_text(encoding="utf-8").splitlines()[0])

        self.assertEqual(predictions[0]["pred_cl_id"], "CL:0000624")
        self.assertIn("Cell type: CD4+ T cell", written["raw_response"])


if __name__ == "__main__":
    unittest.main()
