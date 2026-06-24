from __future__ import annotations

import csv
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from deepseekcell_ft.ontology import (
    accept_ontology_decisions,
    accept_ontology_suggestion,
    auto_accept_ontology_curation,
    apply_ontology_curation,
    enrich_marker_db_with_cl_ids,
    label_variants,
    load_label_to_cl_id,
    map_label_to_cl_id,
    parse_cell_ontology_obo,
    write_cell_ontology_label_map,
    write_ontology_curation_priority_report,
    write_ontology_curation_template,
)


OBO_TEXT = """
format-version: 1.2

[Term]
id: CL:0000236
name: B cell
synonym: "B lymphocyte" EXACT []

[Term]
id: CL:0000624
name: CD4-positive, alpha-beta T cell
synonym: "CD4+ T cell" EXACT []

[Term]
id: CL:9999999
name: obsolete cell
is_obsolete: true
""".strip()


class OntologyTests(unittest.TestCase):
    def test_parse_cell_ontology_obo(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            obo_path = Path(tmpdir) / "cl.obo"
            obo_path.write_text(OBO_TEXT, encoding="utf-8")
            terms = parse_cell_ontology_obo(obo_path)

        self.assertEqual(len(terms), 3)
        self.assertEqual(terms[0].cl_id, "CL:0000236")
        self.assertEqual(terms[0].synonyms, [("B lymphocyte", "EXACT")])
        self.assertTrue(terms[2].is_obsolete)

    def test_write_label_map_and_enrich_marker_db(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            obo_path = tmpdir_path / "cl.obo"
            map_path = tmpdir_path / "labels.csv"
            marker_path = tmpdir_path / "markers.csv"
            enriched_path = tmpdir_path / "markers.enriched.csv"
            unmapped_path = tmpdir_path / "unmapped.csv"
            obo_path.write_text(OBO_TEXT, encoding="utf-8")
            write_cell_ontology_label_map(obo_path, map_path)
            with marker_path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=[
                        "tissue",
                        "cell_type",
                        "cell_ontology_id",
                        "markers",
                        "source",
                        "evidence",
                    ],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "tissue": "PBMC",
                        "cell_type": "CD4+ T cell",
                        "cell_ontology_id": "",
                        "markers": "IL7R, LTB",
                        "source": "test",
                        "evidence": "",
                    }
                )
                writer.writerow(
                    {
                        "tissue": "PBMC",
                        "cell_type": "Unknown cell",
                        "cell_ontology_id": "",
                        "markers": "GENE1, GENE2",
                        "source": "test",
                        "evidence": "",
                    }
                )

            summary = enrich_marker_db_with_cl_ids(
                marker_path,
                map_path,
                enriched_path,
                unmapped_output_path=unmapped_path,
            )
            mapping = load_label_to_cl_id(map_path)
            with enriched_path.open(encoding="utf-8") as handle:
                enriched_rows = list(csv.DictReader(handle))

        self.assertEqual(mapping["cd4+ t cell"], "CL:0000624")
        self.assertEqual(summary["new_matches"], 1)
        self.assertEqual(summary["unmapped_records"], 1)
        self.assertEqual(enriched_rows[0]["cell_ontology_id"], "CL:0000624")

    def test_label_variants_support_plural_database_labels(self) -> None:
        mapping = {
            "fibroblast": "CL:0000057",
            "naive b cell": "CL:0000788",
            "microglial cell": "CL:0000129",
        }

        self.assertIn("fibroblast", label_variants("Fibroblasts"))
        self.assertEqual(map_label_to_cl_id("Fibroblasts", mapping), "CL:0000057")
        self.assertEqual(map_label_to_cl_id("B cells naive", mapping), "CL:0000788")
        self.assertEqual(map_label_to_cl_id("Microglia", mapping), "CL:0000129")
        self.assertIn("cajal retzius cell", label_variants("Cajal-Retzius cells"))

    def test_curation_template_and_apply(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            ontology_map = tmpdir_path / "ontology.csv"
            unmapped = tmpdir_path / "unmapped.csv"
            curation = tmpdir_path / "curation.csv"
            marker_db = tmpdir_path / "markers.csv"
            enriched = tmpdir_path / "markers.curated.csv"

            with ontology_map.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=[
                        "label",
                        "normalized_label",
                        "cl_id",
                        "term_name",
                        "match_source",
                    ],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "label": "pituitary gland cell",
                        "normalized_label": "pituitary gland cell",
                        "cl_id": "CL:0000640",
                        "term_name": "pituitary gland cell",
                        "match_source": "name",
                    }
                )

            with unmapped.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=["tissue", "cell_type", "source", "markers"],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "tissue": "Brain",
                        "cell_type": "Anterior pituitary gland cells",
                        "source": "PanglaoDB",
                        "markers": "POU1F1, PRL",
                    }
                )

            summary = write_ontology_curation_template(
                unmapped,
                ontology_map,
                curation,
                max_suggestions=1,
            )
            with curation.open("r", encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
            rows[0]["accepted_cl_id"] = rows[0]["suggested_cl_id"]
            with curation.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
                writer.writeheader()
                writer.writerows(rows)

            with marker_db.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=[
                        "tissue",
                        "cell_type",
                        "cell_ontology_id",
                        "markers",
                        "source",
                        "evidence",
                    ],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "tissue": "Brain",
                        "cell_type": "Anterior pituitary gland cells",
                        "cell_ontology_id": "",
                        "markers": "POU1F1, PRL",
                        "source": "PanglaoDB",
                        "evidence": "",
                    }
                )

            applied = apply_ontology_curation(marker_db, curation, enriched)
            with enriched.open("r", encoding="utf-8", newline="") as handle:
                enriched_rows = list(csv.DictReader(handle))

        self.assertEqual(summary["unmapped_labels"], 1)
        self.assertEqual(rows[0]["suggested_cl_id"], "CL:0000640")
        self.assertEqual(applied["applied_records"], 1)
        self.assertEqual(enriched_rows[0]["cell_ontology_id"], "CL:0000640")

    def test_auto_accept_ontology_curation_only_accepts_strict_variants(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            curation = Path(tmpdir) / "curation.csv"
            accepted = Path(tmpdir) / "accepted.csv"
            fieldnames = [
                "cell_type",
                "records",
                "tissues",
                "sources",
                "rank",
                "suggested_cl_id",
                "suggested_label",
                "suggested_term_name",
                "suggested_match_source",
                "suggestion_score",
                "accepted_cl_id",
                "accepted_label",
                "notes",
            ]
            with curation.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerow(
                    {
                        "cell_type": "Cajal-Retzius cells",
                        "records": "1",
                        "tissues": "Brain",
                        "sources": "PanglaoDB",
                        "rank": "1",
                        "suggested_cl_id": "CL:0000695",
                        "suggested_label": "Cajal-Retzius cell",
                        "suggested_term_name": "Cajal-Retzius cell",
                        "suggested_match_source": "name",
                        "suggestion_score": "0.807",
                        "accepted_cl_id": "",
                        "accepted_label": "",
                        "notes": "",
                    }
                )
                writer.writerow(
                    {
                        "cell_type": "Natural killer T cells",
                        "records": "1",
                        "tissues": "Immune system",
                        "sources": "PanglaoDB",
                        "rank": "1",
                        "suggested_cl_id": "CL:0000623",
                        "suggested_label": "natural killer cell",
                        "suggested_term_name": "natural killer cell",
                        "suggested_match_source": "name",
                        "suggestion_score": "0.880",
                        "accepted_cl_id": "",
                        "accepted_label": "",
                        "notes": "",
                    }
                )

            summary = auto_accept_ontology_curation(curation, accepted, min_score=0.8)
            with accepted.open("r", encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))

        self.assertEqual(summary["auto_accepted_labels"], 1)
        self.assertEqual(rows[0]["accepted_cl_id"], "CL:0000695")
        self.assertEqual(rows[1]["accepted_cl_id"], "")

    def test_accept_ontology_suggestion_by_rank(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            curation = Path(tmpdir) / "curation.csv"
            accepted = Path(tmpdir) / "accepted.csv"
            fieldnames = [
                "cell_type",
                "records",
                "tissues",
                "sources",
                "rank",
                "suggested_cl_id",
                "suggested_label",
                "suggested_term_name",
                "suggested_match_source",
                "suggestion_score",
                "accepted_cl_id",
                "accepted_label",
                "notes",
            ]
            with curation.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerow(
                    {
                        "cell_type": "Bergmann glia",
                        "records": "1",
                        "tissues": "Brain",
                        "sources": "PanglaoDB",
                        "rank": "1",
                        "suggested_cl_id": "CL:0000644",
                        "suggested_label": "Bergmann glial cell",
                        "suggested_term_name": "Bergmann glial cell",
                        "suggested_match_source": "name",
                        "suggestion_score": "0.616",
                        "accepted_cl_id": "",
                        "accepted_label": "",
                        "notes": "",
                    }
                )

            summary = accept_ontology_suggestion(
                curation,
                accepted,
                cell_type="Bergmann glia",
                rank=1,
                notes="reviewed",
            )
            with accepted.open("r", encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))

        self.assertEqual(summary["accepted_cl_id"], "CL:0000644")
        self.assertEqual(summary["accepted_labels_total"], 1)
        self.assertEqual(rows[0]["accepted_cl_id"], "CL:0000644")
        self.assertEqual(rows[0]["notes"], "reviewed")

    def test_accept_ontology_decisions_batch(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            curation = Path(tmpdir) / "curation.csv"
            decisions = Path(tmpdir) / "decisions.csv"
            accepted = Path(tmpdir) / "accepted.csv"
            fieldnames = [
                "cell_type",
                "records",
                "tissues",
                "sources",
                "rank",
                "suggested_cl_id",
                "suggested_label",
                "suggested_term_name",
                "suggested_match_source",
                "suggestion_score",
                "accepted_cl_id",
                "accepted_label",
                "notes",
            ]
            with curation.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerow(
                    {
                        "cell_type": "Bergmann glia",
                        "records": "1",
                        "tissues": "Brain",
                        "sources": "PanglaoDB",
                        "rank": "1",
                        "suggested_cl_id": "CL:0000644",
                        "suggested_label": "Bergmann glial cell",
                        "suggested_term_name": "Bergmann glial cell",
                        "suggested_match_source": "name",
                        "suggestion_score": "0.616",
                        "accepted_cl_id": "",
                        "accepted_label": "",
                        "notes": "",
                    }
                )
                writer.writerow(
                    {
                        "cell_type": "Airway smooth muscle cells",
                        "records": "1",
                        "tissues": "Smooth muscle",
                        "sources": "PanglaoDB",
                        "rank": "1",
                        "suggested_cl_id": "CL:0000192",
                        "suggested_label": "smooth muscle cell",
                        "suggested_term_name": "smooth muscle cell",
                        "suggested_match_source": "name",
                        "suggestion_score": "0.807",
                        "accepted_cl_id": "",
                        "accepted_label": "",
                        "notes": "",
                    }
                )

            with decisions.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["cell_type", "rank", "cl_id", "notes"])
                writer.writeheader()
                writer.writerow(
                    {
                        "cell_type": "Bergmann glia",
                        "rank": "1",
                        "cl_id": "",
                        "notes": "reviewed",
                    }
                )
                writer.writerow(
                    {
                        "cell_type": "Airway smooth muscle cells",
                        "rank": "",
                        "cl_id": "CL:0000192",
                        "notes": "accepted broader smooth muscle label",
                    }
                )

            summary = accept_ontology_decisions(curation, decisions, accepted)
            with accepted.open("r", encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))

        self.assertEqual(summary["applied_decisions"], 2)
        self.assertEqual(summary["accepted_labels_total"], 2)
        self.assertEqual(rows[0]["accepted_cl_id"], "CL:0000644")
        self.assertEqual(rows[1]["accepted_cl_id"], "CL:0000192")

    def test_accept_ontology_decisions_skips_missing_when_requested(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            curation = Path(tmpdir) / "curation.csv"
            decisions = Path(tmpdir) / "decisions.csv"
            accepted = Path(tmpdir) / "accepted.csv"
            fieldnames = [
                "cell_type",
                "records",
                "tissues",
                "sources",
                "rank",
                "suggested_cl_id",
                "suggested_label",
                "suggested_term_name",
                "suggested_match_source",
                "suggestion_score",
                "accepted_cl_id",
                "accepted_label",
                "notes",
            ]
            with curation.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerow(
                    {
                        "cell_type": "Bergmann glia",
                        "records": "1",
                        "tissues": "Brain",
                        "sources": "PanglaoDB",
                        "rank": "1",
                        "suggested_cl_id": "CL:0000644",
                        "suggested_label": "Bergmann glial cell",
                        "suggested_term_name": "Bergmann glial cell",
                        "suggested_match_source": "name",
                        "suggestion_score": "0.616",
                        "accepted_cl_id": "",
                        "accepted_label": "",
                        "notes": "",
                    }
                )

            with decisions.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["cell_type", "rank", "cl_id", "notes"])
                writer.writeheader()
                writer.writerow(
                    {
                        "cell_type": "Interneurons",
                        "rank": "1",
                        "cl_id": "CL:0000099",
                        "notes": "already mapped upstream",
                    }
                )
                writer.writerow(
                    {
                        "cell_type": "Bergmann glia",
                        "rank": "1",
                        "cl_id": "",
                        "notes": "reviewed",
                    }
                )

            summary = accept_ontology_decisions(
                curation,
                decisions,
                accepted,
                skip_missing=True,
            )
            with accepted.open("r", encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))

        self.assertEqual(summary["applied_decisions"], 1)
        self.assertEqual(summary["skipped_decisions"], 1)
        self.assertEqual(summary["missing_cell_types"], ["Interneurons"])
        self.assertEqual(rows[0]["accepted_cl_id"], "CL:0000644")

    def test_accept_ontology_decisions_blank_mapping_is_review_note_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            curation = Path(tmpdir) / "curation.csv"
            decisions = Path(tmpdir) / "decisions.csv"
            accepted = Path(tmpdir) / "accepted.csv"
            fieldnames = [
                "cell_type",
                "records",
                "tissues",
                "sources",
                "rank",
                "suggested_cl_id",
                "suggested_label",
                "suggested_term_name",
                "suggested_match_source",
                "suggestion_score",
                "accepted_cl_id",
                "accepted_label",
                "notes",
            ]
            with curation.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerow(
                    {
                        "cell_type": "Olfactory epithelial cells",
                        "records": "1",
                        "tissues": "Olfactory system",
                        "sources": "PanglaoDB",
                        "rank": "1",
                        "suggested_cl_id": "CL:0000540",
                        "suggested_label": "neuron",
                        "suggested_term_name": "neuron",
                        "suggested_match_source": "name",
                        "suggestion_score": "0.600",
                        "accepted_cl_id": "",
                        "accepted_label": "",
                        "notes": "",
                    }
                )

            with decisions.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["cell_type", "rank", "cl_id", "notes"])
                writer.writeheader()
                writer.writerow(
                    {
                        "cell_type": "Olfactory epithelial cells",
                        "rank": "",
                        "cl_id": "",
                        "notes": "uncertain; do not force a mapping",
                    }
                )

            summary = accept_ontology_decisions(curation, decisions, accepted)
            with accepted.open("r", encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))

        self.assertEqual(summary["applied_decisions"], 0)
        self.assertEqual(summary["skipped_decisions"], 1)
        self.assertEqual(summary["accepted_labels_total"], 0)
        self.assertEqual(rows[0]["accepted_cl_id"], "")
        self.assertEqual(rows[0]["notes"], "uncertain; do not force a mapping")


    def test_write_ontology_curation_priority_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            curation = tmpdir_path / "curation.csv"
            split_dir = tmpdir_path / "splits"
            output = tmpdir_path / "priority.csv"
            split_dir.mkdir()
            fieldnames = [
                "cell_type",
                "records",
                "tissues",
                "sources",
                "rank",
                "suggested_cl_id",
                "suggested_label",
                "suggested_term_name",
                "suggested_match_source",
                "suggestion_score",
                "accepted_cl_id",
                "accepted_label",
                "notes",
            ]
            with curation.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerow(
                    {
                        "cell_type": "Test label",
                        "records": "1",
                        "tissues": "Brain",
                        "sources": "PanglaoDB",
                        "rank": "1",
                        "suggested_cl_id": "CL:1",
                        "suggested_label": "test label",
                        "suggested_term_name": "test label",
                        "suggested_match_source": "name",
                        "suggestion_score": "0.9",
                        "accepted_cl_id": "",
                        "accepted_label": "",
                        "notes": "",
                    }
                )
                writer.writerow(
                    {
                        "cell_type": "Train label",
                        "records": "1",
                        "tissues": "Brain",
                        "sources": "PanglaoDB",
                        "rank": "1",
                        "suggested_cl_id": "CL:2",
                        "suggested_label": "train label",
                        "suggested_term_name": "train label",
                        "suggested_match_source": "name",
                        "suggestion_score": "0.8",
                        "accepted_cl_id": "",
                        "accepted_label": "",
                        "notes": "",
                    }
                )
                writer.writerow(
                    {
                        "cell_type": "Accepted label",
                        "records": "1",
                        "tissues": "Thyroid",
                        "sources": "PanglaoDB",
                        "rank": "1",
                        "suggested_cl_id": "CL:wrong",
                        "suggested_label": "wrong label",
                        "suggested_term_name": "wrong label",
                        "suggested_match_source": "name",
                        "suggestion_score": "0.9",
                        "accepted_cl_id": "",
                        "accepted_label": "",
                        "notes": "",
                    }
                )
                writer.writerow(
                    {
                        "cell_type": "Accepted label",
                        "records": "1",
                        "tissues": "Thyroid",
                        "sources": "PanglaoDB",
                        "rank": "2",
                        "suggested_cl_id": "CL:right",
                        "suggested_label": "right label",
                        "suggested_term_name": "right label",
                        "suggested_match_source": "name",
                        "suggestion_score": "0.8",
                        "accepted_cl_id": "CL:right",
                        "accepted_label": "right label",
                        "notes": "reviewed",
                    }
                )

            def write_split(name: str, labels: list[str]) -> None:
                with (split_dir / f"{name}.jsonl").open("w", encoding="utf-8") as handle:
                    for label in labels:
                        handle.write('{"metadata":{"cell_type":"' + label + '"}}\n')

            write_split("train", ["Train label", "Test label"])
            write_split("validation", [])
            write_split("test", ["Test label"])

            summary = write_ontology_curation_priority_report(curation, split_dir, output)
            with output.open("r", encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))

        self.assertEqual(summary["labels"], 2)
        self.assertEqual(summary["labels_in_test"], 1)
        self.assertEqual(rows[0]["cell_type"], "Test label")
        self.assertEqual(rows[0]["test_records"], "1")
        self.assertNotIn("Accepted label", {row["cell_type"] for row in rows})


if __name__ == "__main__":
    unittest.main()
