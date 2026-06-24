"""Adapters for traditional annotation baselines."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any


class ExternalBaselineError(RuntimeError):
    """Raised when an external baseline cannot be executed."""


def require_executable(name: str) -> str:
    executable = shutil.which(name)
    if executable is None:
        raise ExternalBaselineError(f"Required executable not found on PATH: {name}")
    return executable


def run_r_script(script_path: str | Path, args: list[str], timeout_seconds: int = 3600) -> subprocess.CompletedProcess[str]:
    """Run an R script and capture output."""

    executable = require_executable("Rscript")
    command = [executable, str(script_path), *args]
    return subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
    )


def write_external_predictions(records: list[dict[str, Any]], path: str | Path) -> None:
    """Write baseline predictions as JSONL compatible with evaluation.py."""

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=True) + "\n")


def single_r_command(
    expression_path: str | Path,
    labels_path: str | Path,
    output_path: str | Path,
    reference_name: str = "celldex::HumanPrimaryCellAtlasData",
) -> list[str]:
    """Build a command argument list for a lab-provided SingleR wrapper script."""

    return [
        "--expression",
        str(expression_path),
        "--labels",
        str(labels_path),
        "--output",
        str(output_path),
        "--reference",
        reference_name,
    ]


def sctype_command(
    expression_path: str | Path,
    tissue: str,
    output_path: str | Path,
    marker_db_path: str | Path | None = None,
) -> list[str]:
    """Build a command argument list for a lab-provided scType wrapper script."""

    args = [
        "--expression",
        str(expression_path),
        "--tissue",
        tissue,
        "--output",
        str(output_path),
    ]
    if marker_db_path:
        args.extend(["--marker-db", str(marker_db_path)])
    return args
