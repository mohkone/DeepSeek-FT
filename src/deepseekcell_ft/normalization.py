"""Normalization helpers for marker genes, cell labels, and ontology IDs."""

from __future__ import annotations

import re
from collections.abc import Iterable

GENE_SPLIT_RE = re.compile(r"[,;|/\s]+")
SPACE_RE = re.compile(r"\s+")
CL_RE = re.compile(r"^CL:\d{7}$", re.IGNORECASE)


def normalize_gene_symbol(symbol: str) -> str:
    """Return a conservative canonical form for a gene symbol."""

    symbol = symbol.strip().strip("\"'`")
    symbol = symbol.replace(" ", "")
    return symbol.upper()


def parse_marker_list(value: str | Iterable[str]) -> tuple[str, ...]:
    """Parse markers from a string or iterable and remove duplicates in order."""

    if value is None:
        return ()

    if isinstance(value, str):
        raw_parts = GENE_SPLIT_RE.split(value)
    else:
        raw_parts = list(value)

    markers: list[str] = []
    seen: set[str] = set()
    for part in raw_parts:
        marker = normalize_gene_symbol(str(part))
        if marker and marker not in seen:
            markers.append(marker)
            seen.add(marker)
    return tuple(markers)


def normalize_cell_label(label: str) -> str:
    """Normalize cell labels for exact-match evaluation."""

    label = label.replace("_", " ").replace("-", " ")
    label = SPACE_RE.sub(" ", label.strip().lower())
    return label


def normalize_tissue(tissue: str) -> str:
    """Normalize tissue labels without losing display casing elsewhere."""

    return SPACE_RE.sub(" ", tissue.strip())


def normalize_cl_id(cl_id: str | None) -> str | None:
    """Normalize Cell Ontology IDs and return None for empty values."""

    if not cl_id:
        return None
    value = cl_id.strip().upper()
    if not value:
        return None
    if value.startswith("CL_"):
        value = value.replace("CL_", "CL:", 1)
    return value if CL_RE.match(value) else value
