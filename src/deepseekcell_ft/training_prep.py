"""Preflight checks for LoRA fine-tuning splits."""

from __future__ import annotations

import hashlib
import importlib.metadata
import importlib.util
import json
import math
import subprocess
import sys
from collections import Counter, defaultdict
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from .dataset_builder import read_jsonl

TRAINING_DEPENDENCIES = ("torch", "transformers", "datasets", "peft", "trl", "accelerate")


def _record_text(record: dict[str, Any]) -> str:
    messages = record.get("messages")
    if isinstance(messages, list):
        parts = []
        for message in messages:
            if isinstance(message, dict):
                role = str(message.get("role", "unknown"))
                content = str(message.get("content", ""))
                parts.append(f"{role}: {content}")
        if parts:
            return "\n".join(parts)

    if {"instruction", "input", "output"} <= set(record):
        return (
            f"Instruction: {record['instruction']}\n\n"
            f"Input:\n{record['input']}\n\n"
            f"Output:\n{record['output']}"
        )

    return json.dumps(record, sort_keys=True, ensure_ascii=True)


def _estimate_tokens(text: str) -> int:
    """Approximate token count for model-agnostic preflight checks."""

    if not text:
        return 0
    return max(1, math.ceil(len(text) / 4))


def _percentile(values: Sequence[int], percentile: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, math.ceil((percentile / 100.0) * len(ordered)) - 1))
    return ordered[index]


def _mean(values: Sequence[int]) -> float:
    return round(sum(values) / len(values), 2) if values else 0.0


def _metadata(record: dict[str, Any]) -> dict[str, Any]:
    metadata = record.get("metadata")
    return metadata if isinstance(metadata, dict) else {}


def _record_format(record: dict[str, Any]) -> str:
    if isinstance(record.get("messages"), list):
        return "chat"
    if {"instruction", "input", "output"} <= set(record):
        return "instruction"
    return "unknown"


def _split_summary(records: Sequence[dict[str, Any]], max_seq_length: int) -> dict[str, Any]:
    label_counts: Counter[str] = Counter()
    tissue_counts: Counter[str] = Counter()
    source_counts: Counter[str] = Counter()
    missing_metadata_fields: Counter[str] = Counter()
    formats: Counter[str] = Counter()
    char_lengths: list[int] = []
    token_lengths: list[int] = []
    records_with_cl_id = 0

    for record in records:
        formats[_record_format(record)] += 1
        metadata = _metadata(record)
        if not metadata:
            missing_metadata_fields["metadata"] += 1

        cell_type = metadata.get("cell_type")
        tissue = metadata.get("tissue")
        source = metadata.get("source")
        cl_id = metadata.get("cell_ontology_id")
        markers = metadata.get("markers")

        if cell_type:
            label_counts[str(cell_type)] += 1
        else:
            missing_metadata_fields["cell_type"] += 1
        if tissue:
            tissue_counts[str(tissue)] += 1
        else:
            missing_metadata_fields["tissue"] += 1
        if source:
            source_counts[str(source)] += 1
        else:
            missing_metadata_fields["source"] += 1
        if cl_id:
            records_with_cl_id += 1
        else:
            missing_metadata_fields["cell_ontology_id"] += 1
        if not markers:
            missing_metadata_fields["markers"] += 1

        text = _record_text(record)
        char_lengths.append(len(text))
        token_lengths.append(_estimate_tokens(text))

    records_count = len(records)
    over_limit = sum(1 for tokens in token_lengths if tokens > max_seq_length)
    return {
        "records": records_count,
        "formats": dict(sorted(formats.items())),
        "unique_labels": len(label_counts),
        "unique_tissues": len(tissue_counts),
        "unique_sources": len(source_counts),
        "records_with_cl_id": records_with_cl_id,
        "cl_coverage": round(records_with_cl_id / records_count, 4) if records_count else 0.0,
        "missing_metadata_fields": dict(sorted(missing_metadata_fields.items())),
        "top_labels": [
            {"label": label, "records": count}
            for label, count in label_counts.most_common(10)
        ],
        "estimated_chars": {
            "min": min(char_lengths) if char_lengths else 0,
            "mean": _mean(char_lengths),
            "p95": _percentile(char_lengths, 95),
            "max": max(char_lengths) if char_lengths else 0,
        },
        "estimated_tokens": {
            "min": min(token_lengths) if token_lengths else 0,
            "mean": _mean(token_lengths),
            "p95": _percentile(token_lengths, 95),
            "max": max(token_lengths) if token_lengths else 0,
            "over_max_seq_length": over_limit,
        },
    }


def _resolve_field(record: dict[str, Any], field: str) -> Any:
    if "." in field:
        value: Any = record
        for part in field.split("."):
            if not isinstance(value, dict):
                return None
            value = value.get(part)
        return value

    metadata = _metadata(record)
    if field in metadata:
        return metadata[field]
    return record.get(field)


def _group_key(record: dict[str, Any], group_by: Sequence[str]) -> tuple[str, ...]:
    key = []
    for field in group_by:
        value = _resolve_field(record, field)
        if value is None:
            key.append("__missing__")
        elif isinstance(value, (dict, list, tuple)):
            key.append(json.dumps(value, sort_keys=True, ensure_ascii=True))
        else:
            key.append(str(value))
    return tuple(key)


def _leakage_report(
    split_records: dict[str, list[dict[str, Any]]],
    group_by: Sequence[str],
) -> dict[str, Any]:
    groups: dict[tuple[str, ...], Counter[str]] = defaultdict(Counter)
    signatures: dict[str, set[str]] = defaultdict(set)
    for split_name, records in split_records.items():
        for record in records:
            if group_by:
                groups[_group_key(record, group_by)][split_name] += 1
            digest = hashlib.sha256(_record_text(record).encode("utf-8")).hexdigest()
            signatures[digest].add(split_name)

    leaked_groups = {key: counts for key, counts in groups.items() if len(counts) > 1}
    duplicate_signatures = {
        digest: sorted(splits) for digest, splits in signatures.items() if len(splits) > 1
    }
    return {
        "group_by": list(group_by),
        "group_check_enabled": bool(group_by),
        "unique_groups": len(groups),
        "leaked_groups": len(leaked_groups),
        "leaked_group_examples": [
            {
                "group": dict(zip(group_by, key, strict=False)),
                "splits": dict(sorted(counts.items())),
            }
            for key, counts in sorted(leaked_groups.items())[:10]
        ],
        "duplicate_records_across_splits": len(duplicate_signatures),
    }


def _label_overlap_report(split_records: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    labels_by_split = {
        split_name: {
            str(metadata["cell_type"])
            for record in records
            if (metadata := _metadata(record)).get("cell_type")
        }
        for split_name, records in split_records.items()
    }
    train_labels = labels_by_split.get("train", set())
    report: dict[str, Any] = {
        split_name: len(labels) for split_name, labels in labels_by_split.items()
    }
    for split_name in ("validation", "test"):
        labels = labels_by_split.get(split_name, set())
        unseen = sorted(labels - train_labels)
        report[f"{split_name}_labels_seen_in_train"] = len(labels & train_labels)
        report[f"{split_name}_labels_unseen_in_train"] = len(unseen)
        report[f"{split_name}_unseen_label_examples"] = unseen[:20]
    return report


def _dependency_report() -> dict[str, Any]:
    dependencies: dict[str, dict[str, Any]] = {}
    missing: list[str] = []
    for package_name in TRAINING_DEPENDENCIES:
        installed = importlib.util.find_spec(package_name) is not None
        version = None
        if installed:
            try:
                version = importlib.metadata.version(package_name)
            except importlib.metadata.PackageNotFoundError:
                version = "unknown"
        else:
            missing.append(package_name)
        dependencies[package_name] = {
            "installed": installed,
            "version": version,
        }
    return {
        "dependencies": dependencies,
        "missing": missing,
        "install_command": 'python -m pip install -e ".[train]"' if missing else None,
    }


def _hardware_report() -> dict[str, Any]:
    report: dict[str, Any] = {
        "torch_available": importlib.util.find_spec("torch") is not None,
        "torch_probe_succeeded": False,
        "torch_probe_error": None,
        "torch_version": None,
        "cuda_available": False,
        "cuda_device_count": 0,
        "cuda_devices": [],
        "mps_available": False,
        "recommended_for_7b_lora": False,
    }
    if not report["torch_available"]:
        return report

    try:
        report["torch_version"] = importlib.metadata.version("torch")
    except importlib.metadata.PackageNotFoundError:
        pass

    probe_code = r"""
import json
report = {
    "torch_probe_succeeded": True,
    "torch_version": None,
    "cuda_available": False,
    "cuda_device_count": 0,
    "cuda_devices": [],
    "mps_available": False,
    "recommended_for_7b_lora": False,
}
import torch
report["torch_version"] = getattr(torch, "__version__", "unknown")
cuda_available = bool(torch.cuda.is_available())
report["cuda_available"] = cuda_available
if cuda_available:
    device_count = int(torch.cuda.device_count())
    devices = []
    for index in range(device_count):
        device = {"index": index, "name": torch.cuda.get_device_name(index)}
        try:
            props = torch.cuda.get_device_properties(index)
            device["total_memory_gb"] = round(props.total_memory / (1024**3), 2)
        except Exception:
            pass
        devices.append(device)
    report["cuda_device_count"] = device_count
    report["cuda_devices"] = devices
    report["recommended_for_7b_lora"] = bool(device_count)
mps_backend = getattr(getattr(torch, "backends", None), "mps", None)
report["mps_available"] = bool(
    mps_backend and mps_backend.is_available() and mps_backend.is_built()
)
print(json.dumps(report, sort_keys=True))
"""
    try:
        probe = subprocess.run(
            [sys.executable, "-c", probe_code],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except Exception as exc:
        report["torch_probe_error"] = str(exc)
        return report

    if probe.returncode != 0:
        stderr = (probe.stderr or "").strip()
        stdout = (probe.stdout or "").strip()
        report["torch_probe_error"] = stderr or stdout or f"exit code {probe.returncode}"
        return report

    try:
        probed = json.loads(probe.stdout)
    except json.JSONDecodeError:
        report["torch_probe_error"] = (probe.stdout or "").strip() or "invalid probe output"
        return report
    report.update(probed)
    return report


def _training_command(
    base_model: str,
    split_dir: Path,
    model_output_dir: str | Path,
    max_seq_length: int,
) -> list[str]:
    return [
        "python -m deepseekcell_ft.cli train-lora `",
        f"  --base-model {base_model} `",
        f"  --train-jsonl {split_dir / 'train.jsonl'} `",
        f"  --validation-jsonl {split_dir / 'validation.jsonl'} `",
        f"  --output-dir {model_output_dir} `",
        f"  --max-seq-length {max_seq_length}",
    ]


def inspect_finetune_splits(
    split_dir: str | Path,
    output_path: str | Path | None = None,
    base_model: str = "deepseek-ai/deepseek-llm-7b-chat",
    model_output_dir: str | Path = "models/deepseekcell-ft-lora",
    max_seq_length: int = 2048,
    group_by: Sequence[str] = ("tissue", "cell_type", "source"),
) -> dict[str, Any]:
    """Inspect curated fine-tuning splits before launching a training job."""

    split_dir = Path(split_dir)
    split_paths = {
        "train": split_dir / "train.jsonl",
        "validation": split_dir / "validation.jsonl",
        "test": split_dir / "test.jsonl",
    }
    missing_paths = [str(path) for path in split_paths.values() if not path.exists()]
    if missing_paths:
        raise FileNotFoundError(", ".join(missing_paths))

    split_records = {
        split_name: read_jsonl(path)
        for split_name, path in split_paths.items()
    }
    all_records = [
        record
        for records in split_records.values()
        for record in records
    ]
    summaries = {
        split_name: _split_summary(records, max_seq_length=max_seq_length)
        for split_name, records in split_records.items()
    }
    total_summary = _split_summary(all_records, max_seq_length=max_seq_length)
    dependencies = _dependency_report()
    hardware = _hardware_report()
    leakage = _leakage_report(split_records, group_by)
    label_overlap = _label_overlap_report(split_records)

    warnings: list[str] = []
    if dependencies["missing"]:
        warnings.append("optional training dependencies are not fully installed")
    if hardware["torch_available"] and not hardware["torch_probe_succeeded"]:
        warnings.append("torch hardware probe failed; inspect hardware.torch_probe_error")
    if dependencies["dependencies"].get("torch", {}).get("installed") and not (
        hardware["cuda_available"] or hardware["mps_available"]
    ):
        warnings.append("no GPU accelerator detected; 7B LoRA training is not practical on CPU")
    if leakage["leaked_groups"]:
        warnings.append("metadata groups appear in more than one split")
    if leakage["duplicate_records_across_splits"]:
        warnings.append("duplicate training records appear across splits")
    if total_summary["estimated_tokens"]["over_max_seq_length"]:
        warnings.append("some records exceed max_seq_length")
    if any(summary["records"] == 0 for summary in summaries.values()):
        warnings.append("one or more splits are empty")
    if total_summary["cl_coverage"] < 0.95:
        warnings.append("Cell Ontology coverage is below 95%")
    for split_name in ("validation", "test"):
        unseen_key = f"{split_name}_labels_unseen_in_train"
        seen_key = f"{split_name}_labels_seen_in_train"
        if label_overlap.get(unseen_key, 0) and label_overlap.get(seen_key, 0) == 0:
            warnings.append(
                f"{split_name} labels are entirely unseen in train; this is label-held-out evaluation"
            )

    report = {
        "split_dir": str(split_dir),
        "base_model": base_model,
        "model_output_dir": str(model_output_dir),
        "max_seq_length": max_seq_length,
        "splits": summaries,
        "total": total_summary,
        "label_overlap": label_overlap,
        "leakage": leakage,
        "training_dependencies": dependencies,
        "hardware": hardware,
        "suggested_train_command": _training_command(
            base_model=base_model,
            split_dir=split_dir,
            model_output_dir=model_output_dir,
            max_seq_length=max_seq_length,
        ),
        "warnings": warnings,
    }

    if output_path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
        report["output"] = str(output_path)
    return report
