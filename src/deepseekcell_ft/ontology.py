"""Small utilities for Cell Ontology label and ID handling."""

from __future__ import annotations

import csv
import difflib
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .normalization import normalize_cell_label, normalize_cl_id
from .source_ingestion import write_marker_records

SYNONYM_RE = re.compile(r'^synonym:\s+"(.+?)"\s+([A-Z]+)\s+')
PARENTHETICAL_RE = re.compile(r"\s*\([^)]*\)\s*")


@dataclass
class CellOntologyTerm:
    cl_id: str
    name: str
    synonyms: list[tuple[str, str]] = field(default_factory=list)
    is_obsolete: bool = False


def parse_cell_ontology_obo(path: str | Path) -> list[CellOntologyTerm]:
    """Parse CL terms from an OBO file."""

    terms: list[CellOntologyTerm] = []
    current: dict[str, Any] | None = None

    def flush() -> None:
        if not current:
            return
        cl_id = normalize_cl_id(current.get("id"))
        name = current.get("name")
        if cl_id and name and cl_id.startswith("CL:"):
            terms.append(
                CellOntologyTerm(
                    cl_id=cl_id,
                    name=name,
                    synonyms=list(current.get("synonyms", [])),
                    is_obsolete=bool(current.get("is_obsolete")),
                )
            )

    with Path(path).open("r", encoding="utf-8", errors="replace") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if line == "[Term]":
                flush()
                current = {"synonyms": []}
                continue
            if line.startswith("["):
                flush()
                current = None
                continue
            if current is None or not line:
                continue
            if line.startswith("id: "):
                current["id"] = line[4:].strip()
            elif line.startswith("name: "):
                current["name"] = line[6:].strip()
            elif line == "is_obsolete: true":
                current["is_obsolete"] = True
            elif line.startswith("synonym: "):
                match = SYNONYM_RE.match(line)
                if match:
                    current["synonyms"].append((match.group(1), match.group(2)))
    flush()
    return terms


def build_cell_ontology_label_rows(
    terms: list[CellOntologyTerm],
    synonym_scopes: set[str] | None = None,
    include_obsolete: bool = False,
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Build unambiguous label-to-CL rows from CL names and synonyms."""

    synonym_scopes = synonym_scopes or {"EXACT"}
    candidate_rows: list[dict[str, str]] = []
    for term in terms:
        if term.is_obsolete and not include_obsolete:
            continue
        candidate_rows.append(
            {
                "label": term.name,
                "normalized_label": normalize_cell_label(term.name),
                "cl_id": term.cl_id,
                "term_name": term.name,
                "match_source": "name",
            }
        )
        for synonym, scope in term.synonyms:
            if scope in synonym_scopes:
                candidate_rows.append(
                    {
                        "label": synonym,
                        "normalized_label": normalize_cell_label(synonym),
                        "cl_id": term.cl_id,
                        "term_name": term.name,
                        "match_source": f"synonym:{scope}",
                    }
                )

    ids_by_label: dict[str, set[str]] = defaultdict(set)
    for row in candidate_rows:
        ids_by_label[row["normalized_label"]].add(row["cl_id"])

    ambiguous_labels = {
        label for label, ids in ids_by_label.items() if len(ids) > 1
    }
    unique_rows: dict[str, dict[str, str]] = {}
    ambiguous_rows: list[dict[str, str]] = []
    for row in candidate_rows:
        normalized_label = row["normalized_label"]
        if normalized_label in ambiguous_labels:
            ambiguous_rows.append(row)
            continue
        unique_rows.setdefault(normalized_label, row)

    rows = sorted(unique_rows.values(), key=lambda item: (item["normalized_label"], item["cl_id"]))
    ambiguous_rows.sort(key=lambda item: (item["normalized_label"], item["cl_id"]))
    return rows, ambiguous_rows


def write_cell_ontology_label_map(
    obo_path: str | Path,
    output_path: str | Path,
    ambiguous_output_path: str | Path | None = None,
    synonym_scopes: set[str] | None = None,
    include_obsolete: bool = False,
) -> dict[str, Any]:
    """Write a CSV label map from a Cell Ontology OBO file."""

    terms = parse_cell_ontology_obo(obo_path)
    rows, ambiguous_rows = build_cell_ontology_label_rows(
        terms,
        synonym_scopes=synonym_scopes,
        include_obsolete=include_obsolete,
    )
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["label", "normalized_label", "cl_id", "term_name", "match_source"]
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    if ambiguous_output_path:
        ambiguous_output_path = Path(ambiguous_output_path)
        ambiguous_output_path.parent.mkdir(parents=True, exist_ok=True)
        with ambiguous_output_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(ambiguous_rows)

    return {
        "terms": len(terms),
        "label_rows": len(rows),
        "ambiguous_rows": len(ambiguous_rows),
        "output": str(output_path),
        "ambiguous_output": str(ambiguous_output_path) if ambiguous_output_path else None,
    }


def load_label_to_cl_id(path: str | Path) -> dict[str, str]:
    """Load a CSV or TSV mapping with label/cell_type and cl_id columns."""

    path = Path(path)
    delimiter = "\t" if path.suffix.lower() in {".tsv", ".tab"} else ","
    mapping: dict[str, str] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, delimiter=delimiter)
        for line_number, row in enumerate(reader, start=2):
            label = row.get("label") or row.get("cell_type") or row.get("name")
            normalized_label = row.get("normalized_label")
            cl_id = row.get("cl_id") or row.get("cell_ontology_id") or row.get("id")
            if not (label or normalized_label) or not cl_id:
                raise ValueError(
                    f"{path}:{line_number} requires label/normalized_label and cl_id"
                )
            normalized = normalize_cl_id(cl_id)
            if normalized:
                if normalized_label:
                    mapping[normalize_cell_label(normalized_label)] = normalized
                if label:
                    mapping[normalize_cell_label(label)] = normalized
    return mapping


def _singularize_token(token: str) -> str:
    special = {
        "cells": "cell",
        "neurons": "neuron",
        "blasts": "blast",
        "platelets": "platelet",
        "erythrocytes": "erythrocyte",
        "reticulocytes": "reticulocyte",
        "monocytes": "monocyte",
        "lymphocytes": "lymphocyte",
        "fibroblasts": "fibroblast",
        "astrocytes": "astrocyte",
        "oligodendrocytes": "oligodendrocyte",
        "osteoblasts": "osteoblast",
        "osteoclasts": "osteoclast",
        "keratinocytes": "keratinocyte",
        "melanocytes": "melanocyte",
        "pinealocytes": "pinealocyte",
        "cholangiocytes": "cholangiocyte",
        "sebocytes": "sebocyte",
        "thymocytes": "thymocyte",
    }
    if token in special:
        return special[token]
    if token.endswith("cytes") and len(token) > 6:
        return f"{token[:-5]}cyte"
    if token.endswith("blasts") and len(token) > 7:
        return f"{token[:-1]}"
    if token.endswith("s") and not token.endswith("ss") and len(token) > 3:
        return token[:-1]
    return token


def label_variants(label: str) -> list[str]:
    """Generate conservative exact-match variants for database cell labels."""

    base = normalize_cell_label(label)
    variants: list[str] = []

    def add(value: str) -> None:
        normalized = normalize_cell_label(value)
        if normalized and normalized not in variants:
            variants.append(normalized)

    add(base)
    add(PARENTHETICAL_RE.sub(" ", base))

    for candidate in list(variants):
        tokens = candidate.split()
        if not tokens:
            continue
        singular_tokens = list(tokens)
        singular_tokens[-1] = _singularize_token(tokens[-1])
        add(" ".join(singular_tokens))

        if len(tokens) >= 3 and tokens[0] in {"b", "t"} and tokens[1] in {"cell", "cells"}:
            tail = list(tokens[2:])
            if tail:
                tail[-1] = _singularize_token(tail[-1])
            add(" ".join([*tail, tokens[0], "cell"]))
        if len(tokens) >= 3 and tokens[0] in {"b", "t"} and tokens[-1] in {"cell", "cells"}:
            middle = list(tokens[1:-1])
            if middle:
                middle[-1] = _singularize_token(middle[-1])
            add(" ".join([*middle, tokens[0], "cell"]))

    curated = {
        "nk cell": ["natural killer cell"],
        "nk cells": ["natural killer cell"],
        "microglia": ["microglial cell"],
        "hematopoietic stem cells": ["hematopoietic stem cell"],
        "erythroid like and erythroid precursor cells": ["erythroid progenitor cell"],
        "neural stem/precursor cells": ["neural stem cell", "neural progenitor cell"],
        "pulmonary alveolar type i cells": ["type I pneumocyte"],
        "pulmonary alveolar type ii cells": ["type II pneumocyte"],
        "gamma (pp) cells": ["pancreatic PP cell"],
        "gamma pp cells": ["pancreatic PP cell"],
    }
    for candidate in list(variants):
        for alias in curated.get(candidate, []):
            add(alias)
    return variants


def map_label_to_cl_id_with_match(
    label: str,
    mapping: dict[str, str],
    use_variants: bool = True,
) -> tuple[str | None, str | None]:
    """Map a label to a CL ID and return the normalized variant that matched."""

    candidates = label_variants(label) if use_variants else [normalize_cell_label(label)]
    for candidate in candidates:
        if candidate in mapping:
            return mapping[candidate], candidate
    return None, None


def map_label_to_cl_id(label: str, mapping: dict[str, str]) -> str | None:
    """Map a cell label to a CL ID using exact normalized label matching."""

    mapped, _ = map_label_to_cl_id_with_match(label, mapping)
    return mapped


def enrich_marker_db_with_cl_ids(
    marker_db_path: str | Path,
    ontology_map_path: str | Path,
    output_path: str | Path,
    unmapped_output_path: str | Path | None = None,
    overwrite: bool = False,
    use_variants: bool = True,
) -> dict[str, Any]:
    """Fill missing Cell Ontology IDs in a marker evidence CSV."""

    from .dataset_builder import load_marker_records

    mapping = load_label_to_cl_id(ontology_map_path)
    records = load_marker_records(marker_db_path)
    enriched = []
    unmapped_rows: list[dict[str, str]] = []
    matched = 0
    existing = 0
    overwritten = 0
    direct_matches = 0
    variant_matches = 0

    for record in records:
        mapped_cl_id, matched_variant = map_label_to_cl_id_with_match(
            record.cell_type,
            mapping,
            use_variants=use_variants,
        )
        next_cl_id = record.cell_ontology_id
        if record.cell_ontology_id and not overwrite:
            existing += 1
        elif mapped_cl_id:
            matched += 1
            if matched_variant == normalize_cell_label(record.cell_type):
                direct_matches += 1
            else:
                variant_matches += 1
            if record.cell_ontology_id and overwrite and record.cell_ontology_id != mapped_cl_id:
                overwritten += 1
            next_cl_id = mapped_cl_id
        else:
            unmapped_rows.append(
                {
                    "tissue": record.tissue,
                    "cell_type": record.cell_type,
                    "source": record.source or "",
                    "markers": ", ".join(record.markers),
                }
            )

        enriched.append(
            type(record)(
                tissue=record.tissue,
                cell_type=record.cell_type,
                cell_ontology_id=next_cl_id,
                markers=record.markers,
                source=record.source,
                evidence=record.evidence,
                metadata=record.metadata,
            )
        )

    write_marker_records(enriched, output_path)
    if unmapped_output_path:
        unmapped_output_path = Path(unmapped_output_path)
        unmapped_output_path.parent.mkdir(parents=True, exist_ok=True)
        with unmapped_output_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=["tissue", "cell_type", "source", "markers"],
            )
            writer.writeheader()
            writer.writerows(unmapped_rows)

    records_with_cl_id = sum(1 for record in enriched if record.cell_ontology_id)
    label_counts = Counter(record.cell_type for record in records)
    return {
        "records": len(records),
        "records_with_cl_id": records_with_cl_id,
        "records_without_cl_id": len(records) - records_with_cl_id,
        "existing_cl_ids_preserved": existing,
        "new_matches": matched,
        "direct_label_matches": direct_matches,
        "variant_label_matches": variant_matches,
        "overwritten_cl_ids": overwritten,
        "unmapped_records": len(unmapped_rows),
        "unique_unmapped_labels": len({row["cell_type"] for row in unmapped_rows}),
        "duplicate_label_records": sum(count - 1 for count in label_counts.values() if count > 1),
        "output": str(output_path),
        "unmapped_output": str(unmapped_output_path) if unmapped_output_path else None,
    }


def _load_ontology_label_rows(path: str | Path) -> list[dict[str, str]]:
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _token_set(value: str) -> set[str]:
    return set(normalize_cell_label(value).split())


def _candidate_score(
    query_norm: str,
    query_tokens: set[str],
    candidate_norm: str,
    candidate_tokens: set[str],
) -> float:
    ratio = difflib.SequenceMatcher(None, query_norm, candidate_norm).ratio()
    overlap = (
        len(query_tokens & candidate_tokens) / len(query_tokens | candidate_tokens)
        if query_tokens or candidate_tokens
        else 0.0
    )
    return (0.65 * ratio) + (0.35 * overlap)


def _prepare_ontology_rows(ontology_rows: Sequence[dict[str, str]]) -> list[dict[str, Any]]:
    prepared: list[dict[str, Any]] = []
    for row in ontology_rows:
        row_label = row.get("normalized_label") or row.get("label") or ""
        normalized_label = normalize_cell_label(row_label)
        if not normalized_label or not row.get("cl_id"):
            continue
        prepared.append(
            {
                **row,
                "_normalized_label": normalized_label,
                "_tokens": _token_set(normalized_label),
            }
        )
    return prepared


def _best_ontology_candidates(
    label: str,
    ontology_rows: Sequence[dict[str, Any]],
    max_suggestions: int,
) -> list[dict[str, str]]:
    variants = [
        (variant, _token_set(variant))
        for variant in label_variants(label)
    ]
    best_by_cl_id: dict[str, dict[str, str]] = {}
    for row in ontology_rows:
        candidate_norm = row["_normalized_label"]
        candidate_tokens = row["_tokens"]
        scores = [
            _candidate_score(variant, variant_tokens, candidate_norm, candidate_tokens)
            for variant, variant_tokens in variants
            if variant_tokens & candidate_tokens
            or variant in candidate_norm
            or candidate_norm in variant
        ]
        if not scores:
            continue
        score = max(scores)
        cl_id = row.get("cl_id", "")
        candidate = {
            "suggested_cl_id": cl_id,
            "suggested_label": row.get("label", ""),
            "suggested_term_name": row.get("term_name", ""),
            "suggested_match_source": row.get("match_source", ""),
            "suggestion_score": f"{score:.3f}",
        }
        previous = best_by_cl_id.get(cl_id)
        if previous is None or float(candidate["suggestion_score"]) > float(previous["suggestion_score"]):
            best_by_cl_id[cl_id] = candidate

    candidates = sorted(
        best_by_cl_id.values(),
        key=lambda item: (
            -float(item["suggestion_score"]),
            item["suggested_term_name"],
            item["suggested_cl_id"],
        ),
    )
    return candidates[:max_suggestions]


def write_ontology_curation_template(
    unmapped_path: str | Path,
    ontology_map_path: str | Path,
    output_path: str | Path,
    max_suggestions: int = 5,
) -> dict[str, Any]:
    """Write a manual curation template for unmapped marker labels."""

    ontology_rows = _prepare_ontology_rows(_load_ontology_label_rows(ontology_map_path))
    grouped: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "records": 0,
            "tissues": set(),
            "sources": set(),
        }
    )
    with Path(unmapped_path).open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            cell_type = row.get("cell_type", "").strip()
            if not cell_type:
                continue
            bucket = grouped[cell_type]
            bucket["records"] += 1
            if row.get("tissue"):
                bucket["tissues"].add(row["tissue"])
            if row.get("source"):
                bucket["sources"].add(row["source"])

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
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
    rows_written = 0
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for cell_type, bucket in sorted(grouped.items(), key=lambda item: item[0].lower()):
            suggestions = _best_ontology_candidates(cell_type, ontology_rows, max_suggestions)
            if not suggestions:
                suggestions = [
                    {
                        "suggested_cl_id": "",
                        "suggested_label": "",
                        "suggested_term_name": "",
                        "suggested_match_source": "",
                        "suggestion_score": "",
                    }
                ]
            for rank, suggestion in enumerate(suggestions, start=1):
                writer.writerow(
                    {
                        "cell_type": cell_type,
                        "records": bucket["records"],
                        "tissues": "; ".join(sorted(bucket["tissues"])),
                        "sources": "; ".join(sorted(bucket["sources"])),
                        "rank": rank,
                        **suggestion,
                        "accepted_cl_id": "",
                        "accepted_label": "",
                        "notes": "",
                    }
                )
                rows_written += 1

    return {
        "unmapped_labels": len(grouped),
        "suggestion_rows": rows_written,
        "output": str(output_path),
    }


def apply_ontology_curation(
    marker_db_path: str | Path,
    curation_path: str | Path,
    output_path: str | Path,
    unmapped_output_path: str | Path | None = None,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Apply accepted CL IDs from a curation CSV to a marker database."""

    from .dataset_builder import load_marker_records

    accepted: dict[str, tuple[str, str | None]] = {}
    with Path(curation_path).open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for line_number, row in enumerate(reader, start=2):
            cell_type = row.get("cell_type", "").strip()
            cl_id = normalize_cl_id(row.get("accepted_cl_id"))
            accepted_label = (row.get("accepted_label") or row.get("suggested_label") or "").strip()
            if not cell_type or not cl_id:
                continue
            key = normalize_cell_label(cell_type)
            if key in accepted and accepted[key][0] != cl_id:
                raise ValueError(
                    f"{curation_path}:{line_number} conflicts with another accepted CL ID for {cell_type}"
                )
            accepted[key] = (cl_id, accepted_label or None)

    records = load_marker_records(marker_db_path)
    enriched = []
    unmapped_rows: list[dict[str, str]] = []
    applied = 0
    preserved = 0
    overwritten = 0
    for record in records:
        key = normalize_cell_label(record.cell_type)
        next_cl_id = record.cell_ontology_id
        if record.cell_ontology_id and not overwrite:
            preserved += 1
        elif key in accepted:
            cl_id, _ = accepted[key]
            if record.cell_ontology_id and record.cell_ontology_id != cl_id:
                overwritten += 1
            if next_cl_id != cl_id:
                applied += 1
            next_cl_id = cl_id
        elif not record.cell_ontology_id:
            unmapped_rows.append(
                {
                    "tissue": record.tissue,
                    "cell_type": record.cell_type,
                    "source": record.source or "",
                    "markers": ", ".join(record.markers),
                }
            )

        enriched.append(
            type(record)(
                tissue=record.tissue,
                cell_type=record.cell_type,
                cell_ontology_id=next_cl_id,
                markers=record.markers,
                source=record.source,
                evidence=record.evidence,
                metadata=record.metadata,
            )
        )

    write_marker_records(enriched, output_path)
    if unmapped_output_path:
        unmapped_output_path = Path(unmapped_output_path)
        unmapped_output_path.parent.mkdir(parents=True, exist_ok=True)
        with unmapped_output_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=["tissue", "cell_type", "source", "markers"],
            )
            writer.writeheader()
            writer.writerows(unmapped_rows)

    records_with_cl_id = sum(1 for record in enriched if record.cell_ontology_id)
    return {
        "accepted_labels": len(accepted),
        "applied_records": applied,
        "existing_cl_ids_preserved": preserved,
        "overwritten_cl_ids": overwritten,
        "records": len(records),
        "records_with_cl_id": records_with_cl_id,
        "records_without_cl_id": len(records) - records_with_cl_id,
        "unmapped_records": len(unmapped_rows),
        "output": str(output_path),
        "unmapped_output": str(unmapped_output_path) if unmapped_output_path else None,
    }


def auto_accept_ontology_curation(
    curation_path: str | Path,
    output_path: str | Path,
    min_score: float = 0.8,
) -> dict[str, Any]:
    """Fill accepted CL IDs for strict singular/plural or punctuation variants only."""

    with Path(curation_path).open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)

    required = {
        "cell_type",
        "suggested_cl_id",
        "suggested_label",
        "suggested_term_name",
        "suggestion_score",
        "accepted_cl_id",
        "accepted_label",
    }
    missing = required - set(fieldnames)
    if missing:
        raise ValueError(f"{curation_path} missing required columns: {sorted(missing)}")

    accepted_by_label: set[str] = {
        normalize_cell_label(row["cell_type"])
        for row in rows
        if row.get("accepted_cl_id")
    }
    auto_accepted_labels: set[str] = set()

    for row in rows:
        label_key = normalize_cell_label(row.get("cell_type", ""))
        if not label_key or label_key in accepted_by_label:
            continue
        try:
            score = float(row.get("suggestion_score") or 0.0)
        except ValueError:
            score = 0.0
        if score < min_score or not row.get("suggested_cl_id"):
            continue

        variants = set(label_variants(row["cell_type"]))
        suggested_labels = {
            normalize_cell_label(row.get("suggested_label", "")),
            normalize_cell_label(row.get("suggested_term_name", "")),
        }
        if variants & suggested_labels:
            row["accepted_cl_id"] = row["suggested_cl_id"]
            row["accepted_label"] = row.get("suggested_label") or row.get("suggested_term_name", "")
            accepted_by_label.add(label_key)
            auto_accepted_labels.add(label_key)

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    return {
        "input": str(curation_path),
        "output": str(output_path),
        "min_score": min_score,
        "auto_accepted_labels": len(auto_accepted_labels),
        "accepted_labels_total": len(accepted_by_label),
        "rows": len(rows),
    }


def accept_ontology_suggestion(
    curation_path: str | Path,
    output_path: str | Path,
    cell_type: str,
    rank: int | None = None,
    cl_id: str | None = None,
    accepted_label: str | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    """Accept one suggested or manually supplied CL ID for a curation label."""

    with Path(curation_path).open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)

    required = {
        "cell_type",
        "rank",
        "suggested_cl_id",
        "suggested_label",
        "suggested_term_name",
        "accepted_cl_id",
        "accepted_label",
        "notes",
    }
    missing = required - set(fieldnames)
    if missing:
        raise ValueError(f"{curation_path} missing required columns: {sorted(missing)}")

    normalized_target = normalize_cell_label(cell_type)
    matching_rows = [
        row for row in rows if normalize_cell_label(row.get("cell_type", "")) == normalized_target
    ]
    if not matching_rows:
        raise ValueError(f"cell type not found in curation file: {cell_type}")

    normalized_cl_id = normalize_cl_id(cl_id)
    target_row: dict[str, str] | None = None
    if normalized_cl_id:
        target_row = next(
            (row for row in matching_rows if normalize_cl_id(row.get("suggested_cl_id")) == normalized_cl_id),
            None,
        )
        if target_row is None:
            target_row = matching_rows[0]
    else:
        wanted_rank = str(rank or 1)
        target_row = next((row for row in matching_rows if row.get("rank") == wanted_rank), None)
        if target_row is None:
            raise ValueError(f"rank {wanted_rank} not found for cell type: {cell_type}")
        normalized_cl_id = normalize_cl_id(target_row.get("suggested_cl_id"))
        if not normalized_cl_id:
            raise ValueError(f"selected row has no suggested CL ID for cell type: {cell_type}")

    for row in matching_rows:
        row["accepted_cl_id"] = ""
        row["accepted_label"] = ""
        if notes is not None:
            row["notes"] = ""

    target_row["accepted_cl_id"] = normalized_cl_id or ""
    target_row["accepted_label"] = (
        accepted_label
        or target_row.get("suggested_label")
        or target_row.get("suggested_term_name")
        or ""
    )
    if notes is not None:
        target_row["notes"] = notes

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    accepted_labels = {
        normalize_cell_label(row.get("cell_type", ""))
        for row in rows
        if row.get("accepted_cl_id")
    }
    return {
        "input": str(curation_path),
        "output": str(output_path),
        "cell_type": target_row.get("cell_type", cell_type),
        "accepted_cl_id": target_row["accepted_cl_id"],
        "accepted_label": target_row["accepted_label"],
        "accepted_labels_total": len(accepted_labels),
    }


def accept_ontology_decisions(
    curation_path: str | Path,
    decisions_path: str | Path,
    output_path: str | Path,
    skip_missing: bool = False,
) -> dict[str, Any]:
    """Apply a compact CSV of reviewed ontology decisions to a curation template."""

    with Path(curation_path).open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)

    required = {
        "cell_type",
        "rank",
        "suggested_cl_id",
        "suggested_label",
        "suggested_term_name",
        "accepted_cl_id",
        "accepted_label",
        "notes",
    }
    missing = required - set(fieldnames)
    if missing:
        raise ValueError(f"{curation_path} missing required columns: {sorted(missing)}")

    rows_by_label: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        rows_by_label[normalize_cell_label(row.get("cell_type", ""))].append(row)

    applied_decisions = 0
    skipped_decisions = 0
    missing_cell_types: set[str] = set()
    with Path(decisions_path).open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for line_number, decision in enumerate(reader, start=2):
            cell_type = (decision.get("cell_type") or "").strip()
            if not cell_type:
                skipped_decisions += 1
                continue
            matching_rows = rows_by_label.get(normalize_cell_label(cell_type))
            if not matching_rows:
                if skip_missing:
                    skipped_decisions += 1
                    missing_cell_types.add(cell_type)
                    continue
                raise ValueError(f"{decisions_path}:{line_number} cell type not found: {cell_type}")

            accepted_cl_id = normalize_cl_id(
                decision.get("cl_id") or decision.get("accepted_cl_id")
            )
            wanted_rank = (decision.get("rank") or "").strip()
            if not accepted_cl_id and not wanted_rank:
                decision_notes = (decision.get("notes") or "").strip()
                if decision_notes:
                    for row in matching_rows:
                        row["accepted_cl_id"] = ""
                        row["accepted_label"] = ""
                    matching_rows[0]["notes"] = decision_notes
                skipped_decisions += 1
                continue

            target_row: dict[str, str] | None = None
            if accepted_cl_id:
                target_row = next(
                    (
                        row
                        for row in matching_rows
                        if normalize_cl_id(row.get("suggested_cl_id")) == accepted_cl_id
                    ),
                    None,
                )
                if target_row is None:
                    target_row = matching_rows[0]
            else:
                target_row = next(
                    (row for row in matching_rows if row.get("rank") == wanted_rank),
                    None,
                )
                if target_row is None:
                    raise ValueError(
                        f"{decisions_path}:{line_number} rank {wanted_rank} not found for {cell_type}"
                    )
                accepted_cl_id = normalize_cl_id(target_row.get("suggested_cl_id"))
                if not accepted_cl_id:
                    raise ValueError(
                        f"{decisions_path}:{line_number} selected row has no suggested CL ID"
                    )

            for row in matching_rows:
                row["accepted_cl_id"] = ""
                row["accepted_label"] = ""

            target_row["accepted_cl_id"] = accepted_cl_id or ""
            target_row["accepted_label"] = (
                (decision.get("accepted_label") or "").strip()
                or target_row.get("suggested_label")
                or target_row.get("suggested_term_name")
                or ""
            )
            decision_notes = (decision.get("notes") or "").strip()
            if decision_notes:
                target_row["notes"] = decision_notes
            applied_decisions += 1

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    accepted_labels = {
        normalize_cell_label(row.get("cell_type", ""))
        for row in rows
        if row.get("accepted_cl_id")
    }
    return {
        "input": str(curation_path),
        "decisions": str(decisions_path),
        "output": str(output_path),
        "applied_decisions": applied_decisions,
        "skipped_decisions": skipped_decisions,
        "missing_cell_types": sorted(missing_cell_types),
        "accepted_labels_total": len(accepted_labels),
    }


def _read_split_metadata_counts(path: str | Path) -> Counter[str]:
    counts: Counter[str] = Counter()
    path = Path(path)
    if not path.exists():
        return counts
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number} is not valid JSON") from exc
            metadata = record.get("metadata") or {}
            cell_type = metadata.get("cell_type")
            if cell_type:
                counts[normalize_cell_label(str(cell_type))] += 1
    return counts


def write_ontology_curation_priority_report(
    curation_path: str | Path,
    split_dir: str | Path,
    output_path: str | Path,
    include_accepted: bool = False,
) -> dict[str, Any]:
    """Rank curation labels by their presence in train/validation/test splits."""

    split_dir = Path(split_dir)
    split_counts = {
        "train": _read_split_metadata_counts(split_dir / "train.jsonl"),
        "validation": _read_split_metadata_counts(split_dir / "validation.jsonl"),
        "test": _read_split_metadata_counts(split_dir / "test.jsonl"),
    }

    with Path(curation_path).open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        curation_rows = list(reader)

    accepted_by_label: dict[str, tuple[str, str]] = {}
    for row in curation_rows:
        cell_type = row.get("cell_type", "").strip()
        accepted_cl_id = row.get("accepted_cl_id", "").strip()
        if cell_type and accepted_cl_id:
            accepted_by_label[normalize_cell_label(cell_type)] = (
                accepted_cl_id,
                row.get("accepted_label", ""),
            )

    grouped: dict[str, dict[str, Any]] = {}
    for row in curation_rows:
        cell_type = row.get("cell_type", "").strip()
        if not cell_type:
            continue
        key = normalize_cell_label(cell_type)
        accepted_cl_id, accepted_label = accepted_by_label.get(key, ("", ""))
        if accepted_cl_id and not include_accepted:
            continue
        bucket = grouped.setdefault(
            key,
            {
                "cell_type": cell_type,
                "accepted_cl_id": accepted_cl_id,
                "accepted_label": accepted_label,
                "top_suggestion": None,
                "records_in_template": row.get("records", ""),
                "tissues": row.get("tissues", ""),
                "sources": row.get("sources", ""),
            },
        )
        if accepted_cl_id and not bucket["accepted_cl_id"]:
            bucket["accepted_cl_id"] = accepted_cl_id
            bucket["accepted_label"] = row.get("accepted_label", "")
        if row.get("rank") == "1" and bucket["top_suggestion"] is None:
            bucket["top_suggestion"] = row

    rows: list[dict[str, Any]] = []
    for key, bucket in grouped.items():
        top = bucket["top_suggestion"] or {}
        train_count = split_counts["train"][key]
        validation_count = split_counts["validation"][key]
        test_count = split_counts["test"][key]
        total_count = train_count + validation_count + test_count
        priority_score = (1000 * test_count) + (100 * validation_count) + train_count
        rows.append(
            {
                "cell_type": bucket["cell_type"],
                "priority_score": priority_score,
                "test_records": test_count,
                "validation_records": validation_count,
                "train_records": train_count,
                "total_split_records": total_count,
                "template_records": bucket["records_in_template"],
                "tissues": bucket["tissues"],
                "sources": bucket["sources"],
                "accepted_cl_id": bucket["accepted_cl_id"],
                "accepted_label": bucket["accepted_label"],
                "suggested_cl_id": top.get("suggested_cl_id", ""),
                "suggested_label": top.get("suggested_label", ""),
                "suggested_term_name": top.get("suggested_term_name", ""),
                "suggestion_score": top.get("suggestion_score", ""),
                "suggested_rank": top.get("rank", ""),
            }
        )

    rows.sort(
        key=lambda item: (
            -int(item["priority_score"]),
            item["cell_type"].lower(),
        )
    )

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "cell_type",
        "priority_score",
        "test_records",
        "validation_records",
        "train_records",
        "total_split_records",
        "template_records",
        "tissues",
        "sources",
        "accepted_cl_id",
        "accepted_label",
        "suggested_cl_id",
        "suggested_label",
        "suggested_term_name",
        "suggestion_score",
        "suggested_rank",
    ]
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    return {
        "output": str(output_path),
        "labels": len(rows),
        "labels_in_test": sum(1 for row in rows if int(row["test_records"]) > 0),
        "labels_in_validation": sum(1 for row in rows if int(row["validation_records"]) > 0),
        "labels_in_train": sum(1 for row in rows if int(row["train_records"]) > 0),
    }
