"""Normalize external marker databases into the DeepSeekCell-FT schema."""

from __future__ import annotations

import csv
import re
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .dataset_builder import load_marker_records
from .normalization import normalize_cl_id, normalize_gene_symbol, parse_marker_list
from .schemas import MarkerRecord

STANDARD_FIELDS = (
    "tissue",
    "cell_type",
    "cell_ontology_id",
    "markers",
    "source",
    "evidence",
)

HEADER_RE = re.compile(r"[^a-z0-9]+")

COLUMN_ALIASES = {
    "tissue": (
        "tissue",
        "tissuetype",
        "tissuename",
        "organ",
        "organname",
        "dataset_tissue",
        "uberonlabel",
    ),
    "cell_type": (
        "celltype",
        "cell_type",
        "cellname",
        "cell_name",
        "cell",
        "annotation",
        "cellannotation",
        "celltypeannotation",
    ),
    "cell_ontology_id": (
        "cellontologyid",
        "cell_ontology_id",
        "cellontology_id",
        "cl_id",
        "clid",
        "ontologyid",
        "ontology_id",
    ),
    "marker": (
        "marker",
        "cellmarker",
        "cell_marker",
        "gene",
        "genesymbol",
        "gene_symbol",
        "officialgenesymbol",
        "official_gene_symbol",
        "official gene symbol",
        "marker_gene",
        "markergene",
    ),
    "markers": (
        "markers",
        "markergenes",
        "marker_genes",
        "positive_markers",
        "cluster_markers",
    ),
    "source": (
        "source",
        "database",
        "resource",
        "reference",
    ),
    "evidence": (
        "evidence",
        "description",
        "note",
        "pmid",
        "pubmedid",
        "publication",
        "reference",
    ),
    "species": (
        "species",
        "specie",
        "speciestype",
        "organism",
    ),
}


@dataclass(frozen=True)
class MarkerTableConfig:
    """Column mapping for an external marker table."""

    tissue_column: str | None = None
    cell_type_column: str | None = None
    marker_column: str | None = None
    markers_column: str | None = None
    cl_id_column: str | None = None
    source_column: str | None = None
    evidence_column: str | None = None
    species_column: str | None = None
    source_name: str | None = None
    species: str | None = None
    delimiter: str | None = None
    min_markers: int = 1


def normalize_header(value: str) -> str:
    """Normalize a header for alias matching."""

    return HEADER_RE.sub("", value.strip().lower())


def sniff_delimiter(path: str | Path, explicit: str | None = None) -> str:
    """Resolve a table delimiter from an option, extension, or file sample."""

    if explicit and explicit != "auto":
        if explicit == "tab":
            return "\t"
        return explicit

    path = Path(path)
    if path.suffix.lower() in {".tsv", ".tab", ".txt"}:
        return "\t"

    sample = path.read_text(encoding="utf-8-sig", errors="replace")[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",\t;")
        return dialect.delimiter
    except csv.Error:
        return ","


def _header_lookup(headers: Sequence[str]) -> dict[str, str]:
    return {normalize_header(header): header for header in headers}


def _resolve_column(
    headers: Sequence[str],
    semantic_name: str,
    explicit: str | None = None,
) -> str | None:
    lookup = _header_lookup(headers)
    if explicit:
        normalized = normalize_header(explicit)
        if normalized not in lookup:
            raise ValueError(f"Column not found for {semantic_name}: {explicit}")
        return lookup[normalized]

    for alias in COLUMN_ALIASES[semantic_name]:
        normalized = normalize_header(alias)
        if normalized in lookup:
            return lookup[normalized]
    return None


def _read_rows(path: str | Path, delimiter: str | None = None) -> tuple[list[str], list[dict[str, str]]]:
    resolved_delimiter = sniff_delimiter(path, delimiter)
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, delimiter=resolved_delimiter)
        headers = list(reader.fieldnames or [])
        rows = [{key: value for key, value in row.items() if key is not None} for row in reader]
    if not headers:
        raise ValueError(f"No headers found in {path}")
    return headers, rows


def _value(row: dict[str, str], column: str | None) -> str | None:
    if not column:
        return None
    value = row.get(column)
    if value is None:
        return None
    value = value.strip()
    return value or None


def _species_matches(value: str | None, requested: str | None) -> bool:
    if not requested:
        return True
    if not value:
        return False
    requested_normalized = normalize_header(requested)
    if normalize_header(value) == requested_normalized:
        return True

    requested_aliases = {
        "human": {"human", "homo", "sapiens", "hs", "hsa"},
        "homosapiens": {"human", "homo", "sapiens", "hs", "hsa"},
        "mouse": {"mouse", "mus", "musculus", "mm", "mmu"},
        "musmusculus": {"mouse", "mus", "musculus", "mm", "mmu"},
    }.get(requested_normalized, {requested_normalized})
    value_tokens = {normalize_header(token) for token in re.split(r"[^A-Za-z0-9]+", value) if token}
    return bool(value_tokens & requested_aliases)


def normalize_marker_table(
    input_path: str | Path,
    output_path: str | Path,
    config: MarkerTableConfig | None = None,
) -> list[MarkerRecord]:
    """Convert an external marker table into grouped marker evidence records."""

    config = config or MarkerTableConfig()
    headers, rows = _read_rows(input_path, config.delimiter)

    tissue_column = _resolve_column(headers, "tissue", config.tissue_column)
    cell_type_column = _resolve_column(headers, "cell_type", config.cell_type_column)
    marker_column = _resolve_column(headers, "marker", config.marker_column)
    markers_column = _resolve_column(headers, "markers", config.markers_column)
    cl_id_column = _resolve_column(headers, "cell_ontology_id", config.cl_id_column)
    source_column = _resolve_column(headers, "source", config.source_column)
    evidence_column = _resolve_column(headers, "evidence", config.evidence_column)
    species_column = _resolve_column(headers, "species", config.species_column)

    if not tissue_column:
        raise ValueError("Could not identify a tissue column. Pass --tissue-column.")
    if not cell_type_column:
        raise ValueError("Could not identify a cell type column. Pass --cell-type-column.")
    if not marker_column and not markers_column:
        raise ValueError("Could not identify marker columns. Pass --marker-column or --markers-column.")

    grouped: dict[tuple[str, str, str | None, str, str | None], dict[str, Any]] = {}
    source_name = config.source_name or Path(input_path).stem

    for row in rows:
        species_value = _value(row, species_column)
        if not _species_matches(species_value, config.species):
            continue

        tissue = _value(row, tissue_column)
        cell_type = _value(row, cell_type_column)
        if not tissue or not cell_type:
            continue

        markers: list[str] = []
        if marker_column:
            marker_value = _value(row, marker_column)
            if marker_value:
                markers.extend(parse_marker_list(marker_value))
        if markers_column:
            markers_value = _value(row, markers_column)
            if markers_value:
                markers.extend(parse_marker_list(markers_value))
        if not markers:
            continue

        cl_id = normalize_cl_id(_value(row, cl_id_column))
        row_source = config.source_name or _value(row, source_column) or source_name
        evidence = _value(row, evidence_column)
        key = (tissue, cell_type, cl_id, row_source, species_value)
        bucket = grouped.setdefault(
            key,
            {
                "markers": [],
                "marker_seen": set(),
                "evidence": [],
                "evidence_seen": set(),
            },
        )
        for marker in markers:
            normalized_marker = normalize_gene_symbol(marker)
            if normalized_marker not in bucket["marker_seen"]:
                bucket["markers"].append(normalized_marker)
                bucket["marker_seen"].add(normalized_marker)
        if evidence and evidence not in bucket["evidence_seen"]:
            bucket["evidence"].append(evidence)
            bucket["evidence_seen"].add(evidence)

    records: list[MarkerRecord] = []
    for (tissue, cell_type, cl_id, source, species_value), bucket in grouped.items():
        if len(bucket["markers"]) < config.min_markers:
            continue
        metadata = {"species": species_value} if species_value else {}
        records.append(
            MarkerRecord(
                tissue=tissue,
                cell_type=cell_type,
                cell_ontology_id=cl_id,
                markers=tuple(bucket["markers"]),
                source=source,
                evidence=" | ".join(bucket["evidence"]) or None,
                metadata=metadata,
            )
        )

    records.sort(key=lambda item: (item.tissue.lower(), item.cell_type.lower(), item.source or ""))
    write_marker_records(records, output_path)
    return records


def write_marker_records(records: Sequence[MarkerRecord], path: str | Path) -> None:
    """Write normalized marker records to the standard CSV schema."""

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=STANDARD_FIELDS)
        writer.writeheader()
        for record in records:
            writer.writerow(
                {
                    "tissue": record.tissue,
                    "cell_type": record.cell_type,
                    "cell_ontology_id": record.cell_ontology_id or "",
                    "markers": ", ".join(record.markers),
                    "source": record.source or "",
                    "evidence": record.evidence or "",
                }
            )


def merge_marker_record_sets(
    input_paths: Sequence[str | Path],
    output_path: str | Path,
    min_markers: int = 1,
) -> list[MarkerRecord]:
    """Merge standard marker evidence CSV files and deduplicate markers."""

    grouped: dict[tuple[str, str, str | None], dict[str, Any]] = defaultdict(
        lambda: {
            "markers": [],
            "marker_seen": set(),
            "sources": [],
            "source_seen": set(),
            "evidence": [],
            "evidence_seen": set(),
        }
    )

    for path in input_paths:
        for record in load_marker_records(path):
            key = (record.tissue, record.cell_type, record.cell_ontology_id)
            bucket = grouped[key]
            for marker in record.markers:
                if marker not in bucket["marker_seen"]:
                    bucket["markers"].append(marker)
                    bucket["marker_seen"].add(marker)
            if record.source and record.source not in bucket["source_seen"]:
                bucket["sources"].append(record.source)
                bucket["source_seen"].add(record.source)
            if record.evidence and record.evidence not in bucket["evidence_seen"]:
                bucket["evidence"].append(record.evidence)
                bucket["evidence_seen"].add(record.evidence)

    records: list[MarkerRecord] = []
    for (tissue, cell_type, cl_id), bucket in grouped.items():
        if len(bucket["markers"]) < min_markers:
            continue
        records.append(
            MarkerRecord(
                tissue=tissue,
                cell_type=cell_type,
                cell_ontology_id=cl_id,
                markers=tuple(bucket["markers"]),
                source="; ".join(bucket["sources"]) or None,
                evidence=" | ".join(bucket["evidence"]) or None,
            )
        )

    records.sort(key=lambda item: (item.tissue.lower(), item.cell_type.lower()))
    write_marker_records(records, output_path)
    return records


def summarize_marker_records(records: Iterable[MarkerRecord]) -> dict[str, Any]:
    """Return simple counts for a marker evidence collection."""

    materialized = list(records)
    tissues = {record.tissue for record in materialized}
    cell_types = {record.cell_type for record in materialized}
    markers = {marker for record in materialized for marker in record.markers}
    with_cl_id = sum(1 for record in materialized if record.cell_ontology_id)
    return {
        "records": len(materialized),
        "tissues": len(tissues),
        "cell_types": len(cell_types),
        "unique_markers": len(markers),
        "records_with_cl_id": with_cl_id,
        "mean_markers_per_record": (
            sum(len(record.markers) for record in materialized) / len(materialized)
            if materialized
            else 0.0
        ),
    }
