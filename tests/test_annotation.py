from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from deepseekcell_ft.annotation import MarkerOverlapAnnotator, parse_annotation_response
from deepseekcell_ft.dataset_builder import load_marker_records


class AnnotationTests(unittest.TestCase):
    def test_parse_annotation_response(self) -> None:
        prediction = parse_annotation_response(
            "Cell type: CD4+ T cell\n"
            "Cell Ontology ID: CL:0000624\n"
            "Confidence: 0.82\n\n"
            "Reasoning: IL7R and LTB support helper T cells."
        )
        self.assertEqual(prediction.cell_type, "CD4+ T cell")
        self.assertEqual(prediction.cell_ontology_id, "CL:0000624")
        self.assertAlmostEqual(prediction.confidence or 0.0, 0.82)

    def test_parse_markdown_prompt_response(self) -> None:
        prediction = parse_annotation_response(
            "### Prediction:\n"
            "- **Cell Type:** Neutrophil\n"
            "- **Cell Ontology ID:** GO:0005622 (Neutrophil)\n"
            "- **Confidence Score:** 0.95\n"
            "- **Biological Reasoning:** CD33 supports a myeloid annotation."
        )

        self.assertEqual(prediction.cell_type, "Neutrophil")
        self.assertIsNone(prediction.cell_ontology_id)
        self.assertAlmostEqual(prediction.confidence or 0.0, 0.95)
        self.assertIn("CD33", prediction.reasoning or "")

    def test_parse_text_label_in_ontology_field_as_fallback(self) -> None:
        prediction = parse_annotation_response(
            "Based on the markers, I would predict the most specific cell type to be:\n\n"
            "Cell Ontology ID: Neural stem cells\n"
            "Confidence score: 0.8\n"
            "Biological reasoning: The genes support neural development."
        )

        self.assertEqual(prediction.cell_type, "Neural stem cells")
        self.assertAlmostEqual(prediction.confidence or 0.0, 0.8)

    def test_marker_overlap_annotator(self) -> None:
        records = load_marker_records(ROOT / "data" / "raw" / "marker_evidence.example.csv")
        annotator = MarkerOverlapAnnotator(records)
        prediction = annotator.predict("PBMC", "IL7R, LTB, IL32")
        self.assertEqual(prediction.cell_type, "CD4+ T cell")
        self.assertEqual(prediction.cell_ontology_id, "CL:0000624")


if __name__ == "__main__":
    unittest.main()
