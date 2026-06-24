"""Experiment summary reports for manuscript tables."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .evaluation import evaluate_predictions, load_prediction_records


@dataclass(frozen=True)
class NamedPath:
    name: str
    path: Path


def parse_named_path(spec: str) -> NamedPath:
    """Parse either name=path or a bare path."""

    if "=" in spec:
        name, path = spec.split("=", 1)
        name = name.strip()
        if not name:
            raise ValueError(f"missing name in path spec: {spec}")
        return NamedPath(name=name, path=Path(path.strip()))
    path = Path(spec)
    return NamedPath(name=path.stem, path=path)


def _round_metric(value: Any) -> Any:
    if isinstance(value, float):
        return round(value, 6)
    return value


def _infer_method(name: str, path: Path) -> str:
    text = f"{name} {path}".lower()
    if "singler" in text:
        return "SingleR"
    if "rerank" in text:
        return "DeepSeek-7B LoRA rerank"
    if "prompt" in text:
        if "qwen" in text:
            return "Prompt-only Qwen"
        if "llama" in text:
            return "Prompt-only Llama"
        if "deepseek" in text:
            return "Prompt-only DeepSeek"
        return "Prompt-only LLM"
    if "lora" in text or "deepseek_lora" in text:
        return "DeepSeek-7B LoRA"
    if "marker" in text or "overlap" in text:
        return "marker-overlap"
    return "unknown"


def _prediction_summary(named_path: NamedPath) -> dict[str, Any]:
    records = load_prediction_records(named_path.path)
    metrics = evaluate_predictions(records)
    return {
        "name": named_path.name,
        "path": str(named_path.path),
        "method": _infer_method(named_path.name, named_path.path),
        "n": metrics["n"],
        "accuracy": _round_metric(metrics["accuracy"]),
        "macro_f1": _round_metric(metrics["macro_f1"]),
        "cell_ontology_accuracy": _round_metric(metrics["cell_ontology_accuracy"]),
        "expected_calibration_error": _round_metric(metrics["expected_calibration_error"]),
        "mean_runtime_seconds": _round_metric(metrics["mean_runtime_seconds"]),
        "total_runtime_seconds": _round_metric(metrics["total_runtime_seconds"]),
        "total_cost_usd": metrics["total_cost_usd"],
        "unique_labels": len(metrics["labels"]),
    }


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _preflight_summary(named_path: NamedPath) -> dict[str, Any]:
    report = _load_json(named_path.path)
    splits = report.get("splits", {})
    total = report.get("total", {})
    label_overlap = report.get("label_overlap", {})
    leakage = report.get("leakage", {})
    hardware = report.get("hardware", {})
    dependencies = report.get("training_dependencies", {})
    return {
        "name": named_path.name,
        "path": str(named_path.path),
        "split_dir": report.get("split_dir"),
        "records": total.get("records"),
        "train_records": splits.get("train", {}).get("records"),
        "validation_records": splits.get("validation", {}).get("records"),
        "test_records": splits.get("test", {}).get("records"),
        "unique_labels": total.get("unique_labels"),
        "cl_coverage": _round_metric(total.get("cl_coverage")),
        "max_estimated_tokens": total.get("estimated_tokens", {}).get("max"),
        "duplicate_records_across_splits": leakage.get("duplicate_records_across_splits"),
        "validation_labels_seen_in_train": label_overlap.get("validation_labels_seen_in_train"),
        "validation_labels_unseen_in_train": label_overlap.get("validation_labels_unseen_in_train"),
        "test_labels_seen_in_train": label_overlap.get("test_labels_seen_in_train"),
        "test_labels_unseen_in_train": label_overlap.get("test_labels_unseen_in_train"),
        "training_dependencies_missing": dependencies.get("missing", []),
        "cuda_available": hardware.get("cuda_available"),
        "mps_available": hardware.get("mps_available"),
        "warnings": report.get("warnings", []),
    }


def _format_value(value: Any) -> str:
    if value is None:
        return "NA"
    if isinstance(value, float):
        return f"{value:.4f}"
    if isinstance(value, list):
        return "; ".join(str(item) for item in value) if value else "none"
    return str(value)


def _markdown_table(headers: list[str], rows: list[list[Any]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(_format_value(value) for value in row) + " |")
    return "\n".join(lines)


def render_summary_markdown(summary: dict[str, Any]) -> str:
    prediction_rows = [
        [
            row["name"],
            row["method"],
            row["n"],
            row["accuracy"],
            row["macro_f1"],
            row["cell_ontology_accuracy"],
            row["expected_calibration_error"],
            row["mean_runtime_seconds"],
            row["unique_labels"],
        ]
        for row in summary["predictions"]
    ]
    preflight_rows = [
        [
            row["name"],
            row["records"],
            f"{row['train_records']}/{row['validation_records']}/{row['test_records']}",
            row["unique_labels"],
            row["cl_coverage"],
            row["duplicate_records_across_splits"],
            row["test_labels_seen_in_train"],
            row["test_labels_unseen_in_train"],
            row["cuda_available"],
            row["warnings"],
        ]
        for row in summary["preflights"]
    ]
    sections = [
        "# DeepSeekCell-FT Experiment Summary",
        "",
        "## Prediction Metrics",
        "",
        _markdown_table(
            [
                "Experiment",
                "Method",
                "n",
                "Accuracy",
                "Macro F1",
                "CL Accuracy",
                "ECE",
                "Mean Runtime (s)",
                "Labels",
            ],
            prediction_rows,
        ),
        "",
        "## Split And Training Preflight",
        "",
        _markdown_table(
            [
                "Split",
                "Records",
                "Train/Val/Test",
                "Labels",
                "CL Coverage",
                "Duplicate Records",
                "Test Labels Seen",
                "Test Labels Unseen",
                "CUDA",
                "Warnings",
            ],
            preflight_rows,
        ),
        "",
    ]
    return "\n".join(sections)


def write_experiment_summary(
    prediction_specs: list[str],
    preflight_specs: list[str],
    output_json: str | Path,
    output_markdown: str | Path | None = None,
) -> dict[str, Any]:
    """Write JSON and Markdown summaries from benchmark outputs."""

    predictions = [_prediction_summary(parse_named_path(spec)) for spec in prediction_specs]
    preflights = [_preflight_summary(parse_named_path(spec)) for spec in preflight_specs]
    summary = {
        "predictions": predictions,
        "preflights": preflights,
    }

    output_json = Path(output_json)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    summary["output_json"] = str(output_json)

    if output_markdown:
        output_markdown = Path(output_markdown)
        output_markdown.parent.mkdir(parents=True, exist_ok=True)
        output_markdown.write_text(render_summary_markdown(summary), encoding="utf-8")
        summary["output_markdown"] = str(output_markdown)
    return summary
