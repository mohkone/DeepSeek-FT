"""Download helpers for public marker resources."""

from __future__ import annotations

import gzip
import shutil
import urllib.request
from pathlib import Path

PANGLAODB_MARKERS_URL = "https://panglaodb.se/markers/PanglaoDB_markers_27_Mar_2020.tsv.gz"
CELL_ONTOLOGY_OBO_URL = "http://purl.obolibrary.org/obo/cl.obo"


def download_panglaodb_markers(
    output_path: str | Path,
    url: str = PANGLAODB_MARKERS_URL,
) -> Path:
    """Download and decompress the PanglaoDB marker table."""

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    compressed_path = output_path.with_suffix(output_path.suffix + ".gz")

    with urllib.request.urlopen(url, timeout=60) as response:
        with compressed_path.open("wb") as handle:
            shutil.copyfileobj(response, handle)

    with gzip.open(compressed_path, "rb") as source:
        with output_path.open("wb") as target:
            shutil.copyfileobj(source, target)

    compressed_path.unlink(missing_ok=True)
    return output_path


def download_cell_ontology_obo(
    output_path: str | Path,
    url: str = CELL_ONTOLOGY_OBO_URL,
) -> Path:
    """Download the Cell Ontology OBO release."""

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url, timeout=60) as response:
        with output_path.open("wb") as handle:
            shutil.copyfileobj(response, handle)
    return output_path
