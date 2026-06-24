from __future__ import annotations

import csv
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from deepseekcell_ft.dataset_builder import load_marker_records
from deepseekcell_ft.source_ingestion import (
    MarkerTableConfig,
    merge_marker_record_sets,
    normalize_marker_table,
    summarize_marker_records,
)


class SourceIngestionTests(unittest.TestCase):
    def test_normalize_one_gene_per_row_table(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            raw_path = Path(tmpdir) / "cellmarker_like.csv"
            output_path = Path(tmpdir) / "normalized.csv"
            with raw_path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=[
                        "tissueType",
                        "cellName",
                        "CellOntologyID",
                        "geneSymbol",
                        "speciesType",
                        "PMID",
                    ],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "tissueType": "PBMC",
                        "cellName": "CD4+ T cell",
                        "CellOntologyID": "CL:0000624",
                        "geneSymbol": "IL7R",
                        "speciesType": "Human",
                        "PMID": "123",
                    }
                )
                writer.writerow(
                    {
                        "tissueType": "PBMC",
                        "cellName": "CD4+ T cell",
                        "CellOntologyID": "CL:0000624",
                        "geneSymbol": "LTB",
                        "speciesType": "Human",
                        "PMID": "456",
                    }
                )
                writer.writerow(
                    {
                        "tissueType": "PBMC",
                        "cellName": "CD4+ T cell",
                        "CellOntologyID": "CL:0000624",
                        "geneSymbol": "Il7r",
                        "speciesType": "Mouse",
                        "PMID": "789",
                    }
                )

            records = normalize_marker_table(
                raw_path,
                output_path,
                MarkerTableConfig(source_name="CellMarker", species="Human"),
            )

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].source, "CellMarker")
        self.assertEqual(records[0].markers, ("IL7R", "LTB"))
        self.assertEqual(records[0].evidence, "123 | 456")

    def test_merge_marker_record_sets(self) -> None:
        marker_db = ROOT / "data" / "raw" / "marker_evidence.example.csv"
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "merged.csv"
            records = merge_marker_record_sets([marker_db, marker_db], output_path)
            reloaded = load_marker_records(output_path)

        self.assertEqual(len(records), len(reloaded))
        cd4 = next(record for record in reloaded if record.cell_type == "CD4+ T cell")
        self.assertEqual(cd4.markers.count("IL7R"), 1)

    def test_summarize_marker_records(self) -> None:
        records = load_marker_records(ROOT / "data" / "raw" / "marker_evidence.example.csv")
        summary = summarize_marker_records(records)
        self.assertGreater(summary["records"], 0)
        self.assertGreater(summary["unique_markers"], 0)

    def test_normalize_panglaodb_like_table(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            raw_path = Path(tmpdir) / "panglaodb.tsv"
            output_path = Path(tmpdir) / "normalized.csv"
            raw_path.write_text(
                "species\tofficial gene symbol\tcell type\torgan\n"
                "Mm Hs\tIL7R\tT cells\tBlood\n"
                "Mm Hs\tLTB\tT cells\tBlood\n"
                "Mm\tCd3e\tT cells\tBlood\n",
                encoding="utf-8",
            )

            records = normalize_marker_table(
                raw_path,
                output_path,
                MarkerTableConfig(source_name="PanglaoDB", species="Human", min_markers=2),
            )

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].tissue, "Blood")
        self.assertEqual(records[0].cell_type, "T cells")
        self.assertEqual(records[0].markers, ("IL7R", "LTB"))


if __name__ == "__main__":
    unittest.main()
