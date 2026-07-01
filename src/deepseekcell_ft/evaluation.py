"""Evaluation metrics for cell type annotation predictions."""

from __future__ import annotations

import json
import csv
from collections import Counter
from pathlib import Path
from statistics import mean
from typing import Any

from .annotation import parse_annotation_response
from .dataset_builder import load_marker_records, read_jsonl
from .normalization import normalize_cell_label, normalize_cl_id
from .ontology import label_variants


def _safe_divide(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0


def accuracy(y_true: list[str], y_pred: list[str]) -> float:
    if not y_true:
        return 0.0
    matches = sum(
        normalize_cell_label(true) == normalize_cell_label(pred)
        for true, pred in zip(y_true, y_pred, strict=False)
    )
    return matches / len(y_true)


def macro_f1(y_true: list[str], y_pred: list[str]) -> float:
    labels = sorted({normalize_cell_label(label) for label in y_true})
    if not labels:
        return 0.0

    f1_scores: list[float] = []
    normalized_true = [normalize_cell_label(label) for label in y_true]
    normalized_pred = [normalize_cell_label(label) for label in y_pred]

    for label in labels:
        tp = sum(1 for true, pred in zip(normalized_true, normalized_pred, strict=False) if true == pred == label)
        fp = sum(1 for true, pred in zip(normalized_true, normalized_pred, strict=False) if true != label and pred == label)
        fn = sum(1 for true, pred in zip(normalized_true, normalized_pred, strict=False) if true == label and pred != label)
        precision = _safe_divide(tp, tp + fp)
        recall = _safe_divide(tp, tp + fn)
        f1_scores.append(_safe_divide(2 * precision * recall, precision + recall))
    return sum(f1_scores) / len(f1_scores)


def ontology_accuracy(true_ids: list[str | None], pred_ids: list[str | None]) -> float | None:
    pairs = [
        (normalize_cl_id(true), normalize_cl_id(pred))
        for true, pred in zip(true_ids, pred_ids, strict=False)
        if true
    ]
    if not pairs:
        return None
    if not any(pred for _, pred in pairs):
        return None
    return sum(true == pred for true, pred in pairs) / len(pairs)


def expected_calibration_error(
    correct: list[bool],
    confidences: list[float | None],
    n_bins: int = 10,
) -> float | None:
    usable = [
        (is_correct, float(confidence))
        for is_correct, confidence in zip(correct, confidences, strict=False)
        if confidence is not None
    ]
    if not usable:
        return None
    bins: list[list[tuple[bool, float]]] = [[] for _ in range(n_bins)]
    for is_correct, confidence in usable:
        confidence = min(1.0, max(0.0, confidence))
        index = min(n_bins - 1, int(confidence * n_bins))
        bins[index].append((is_correct, confidence))

    total = len(usable)
    ece = 0.0
    for bucket in bins:
        if not bucket:
            continue
        bucket_accuracy = sum(is_correct for is_correct, _ in bucket) / len(bucket)
        bucket_confidence = sum(confidence for _, confidence in bucket) / len(bucket)
        ece += (len(bucket) / total) * abs(bucket_accuracy - bucket_confidence)
    return ece


def evaluate_predictions(
    records: list[dict[str, Any]],
    confidence_bins: int = 10,
) -> dict[str, Any]:
    """Evaluate JSON-like prediction records."""

    y_true = [str(record.get("y_true", "")) for record in records]
    y_pred = [str(record.get("y_pred", "")) for record in records]
    true_ids = [record.get("true_cl_id") for record in records]
    pred_ids = [record.get("pred_cl_id") for record in records]
    confidences = [record.get("confidence") for record in records]
    runtimes = [
        float(record["runtime_seconds"])
        for record in records
        if record.get("runtime_seconds") is not None
    ]
    costs = [float(record["cost_usd"]) for record in records if record.get("cost_usd") is not None]
    correct = [
        normalize_cell_label(true) == normalize_cell_label(pred)
        for true, pred in zip(y_true, y_pred, strict=False)
    ]

    per_label_counts = Counter(normalize_cell_label(label) for label in y_true)
    metrics: dict[str, Any] = {
        "n": len(records),
        "accuracy": accuracy(y_true, y_pred),
        "macro_f1": macro_f1(y_true, y_pred),
        "cell_ontology_accuracy": ontology_accuracy(true_ids, pred_ids),
        "expected_calibration_error": expected_calibration_error(
            correct,
            confidences,
            n_bins=confidence_bins,
        ),
        "mean_runtime_seconds": mean(runtimes) if runtimes else None,
        "total_runtime_seconds": sum(runtimes) if runtimes else None,
        "total_cost_usd": sum(costs) if costs else None,
        "labels": dict(per_label_counts),
    }
    return metrics


def load_prediction_records(path: str | Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with Path(path).open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            missing = {"y_true", "y_pred"} - set(record)
            if missing:
                raise ValueError(f"{path}:{line_number} missing fields: {sorted(missing)}")
            records.append(record)
    return records


def reparse_prediction_records(
    predictions_path: str | Path,
    output_path: str | Path,
) -> dict[str, Any]:
    """Re-extract prediction fields from saved raw LLM responses."""

    records = load_prediction_records(predictions_path)
    output_records: list[dict[str, Any]] = []
    changed_labels = 0
    parsed_confidences = 0
    parsed_cl_ids = 0

    for record in records:
        updated = dict(record)
        raw_response = str(updated.get("raw_response") or "")
        parsed = parse_annotation_response(raw_response)
        previous_label = str(updated.get("y_pred", ""))

        updated.setdefault("original_y_pred", previous_label)
        updated.setdefault("original_pred_cl_id", updated.get("pred_cl_id"))
        updated.setdefault("original_confidence", updated.get("confidence"))
        updated["y_pred"] = parsed.cell_type
        updated["pred_cl_id"] = parsed.cell_ontology_id
        updated["confidence"] = parsed.confidence
        updated["reasoning"] = parsed.reasoning
        updated["raw_response"] = parsed.raw_response

        changed_labels += int(normalize_cell_label(previous_label) != normalize_cell_label(parsed.cell_type))
        parsed_confidences += int(parsed.confidence is not None)
        parsed_cl_ids += int(parsed.cell_ontology_id is not None)
        output_records.append(updated)

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in output_records:
            handle.write(json.dumps(record, ensure_ascii=True) + "\n")

    before_metrics = evaluate_predictions(records)
    after_metrics = evaluate_predictions(output_records)
    return {
        "input": str(predictions_path),
        "output": str(output_path),
        "records": len(records),
        "changed_labels": changed_labels,
        "parsed_confidences": parsed_confidences,
        "parsed_cl_ids": parsed_cl_ids,
        "before_accuracy": before_metrics["accuracy"],
        "after_accuracy": after_metrics["accuracy"],
        "before_macro_f1": before_metrics["macro_f1"],
        "after_macro_f1": after_metrics["macro_f1"],
        "before_cell_ontology_accuracy": before_metrics["cell_ontology_accuracy"],
        "after_cell_ontology_accuracy": after_metrics["cell_ontology_accuracy"],
    }


def sync_prediction_gold_ontology_ids(
    predictions_path: str | Path,
    input_jsonl_path: str | Path,
    output_path: str | Path,
    allow_mismatches: bool = False,
) -> dict[str, Any]:
    """Refresh prediction gold CL IDs from the aligned instruction JSONL."""

    records = load_prediction_records(predictions_path)
    examples = read_jsonl(input_jsonl_path)
    if len(records) != len(examples):
        raise ValueError(
            f"prediction/input length mismatch: {len(records)} predictions, "
            f"{len(examples)} instruction records"
        )

    mismatches: list[dict[str, Any]] = []
    output_records: list[dict[str, Any]] = []
    changed = 0
    cleared = 0
    filled = 0

    for index, (record, example) in enumerate(zip(records, examples, strict=True), start=1):
        metadata = example.get("metadata") or {}
        expected_label = str(metadata.get("cell_type", ""))
        expected_tissue = str(metadata.get("tissue", ""))
        expected_markers = metadata.get("markers")
        actual_markers = record.get("markers")

        mismatch_reasons: list[str] = []
        if normalize_cell_label(str(record.get("y_true", ""))) != normalize_cell_label(expected_label):
            mismatch_reasons.append("cell_type")
        if expected_tissue and str(record.get("tissue", "")) != expected_tissue:
            mismatch_reasons.append("tissue")
        if expected_markers is not None and list(actual_markers or []) != list(expected_markers):
            mismatch_reasons.append("markers")
        if mismatch_reasons:
            mismatches.append({"index": index, "reasons": mismatch_reasons})

        updated = dict(record)
        previous_cl_id = normalize_cl_id(updated.get("true_cl_id"))
        refreshed_cl_id = normalize_cl_id(metadata.get("cell_ontology_id"))
        updated.setdefault("original_true_cl_id", previous_cl_id)
        updated["true_cl_id"] = refreshed_cl_id or None
        updated["true_cl_id_source"] = "instruction_metadata"

        if previous_cl_id != refreshed_cl_id:
            changed += 1
            if previous_cl_id and not refreshed_cl_id:
                cleared += 1
            elif refreshed_cl_id and not previous_cl_id:
                filled += 1
        output_records.append(updated)

    if mismatches and not allow_mismatches:
        first = mismatches[0]
        raise ValueError(
            "prediction/input records are not aligned; "
            f"first mismatch at row {first['index']}: {', '.join(first['reasons'])}"
        )

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in output_records:
            handle.write(json.dumps(record, ensure_ascii=True) + "\n")

    before_metrics = evaluate_predictions(records)
    after_metrics = evaluate_predictions(output_records)
    return {
        "input": str(predictions_path),
        "instruction_jsonl": str(input_jsonl_path),
        "output": str(output_path),
        "records": len(records),
        "changed_true_cl_ids": changed,
        "filled_true_cl_ids": filled,
        "cleared_true_cl_ids": cleared,
        "alignment_mismatches": len(mismatches),
        "before_records_with_true_cl_id": sum(bool(record.get("true_cl_id")) for record in records),
        "after_records_with_true_cl_id": sum(bool(record.get("true_cl_id")) for record in output_records),
        "before_cell_ontology_accuracy": before_metrics["cell_ontology_accuracy"],
        "after_cell_ontology_accuracy": after_metrics["cell_ontology_accuracy"],
        "after_accuracy": after_metrics["accuracy"],
        "after_macro_f1": after_metrics["macro_f1"],
    }


def analyze_prediction_records(
    records: list[dict[str, Any]],
    examples_output: str | Path | None = None,
    max_examples: int = 25,
) -> dict[str, Any]:
    """Summarize prediction errors and optionally write a compact error CSV."""

    metrics = evaluate_predictions(records)
    normalized_pairs = [
        (
            normalize_cell_label(str(record.get("y_true", ""))),
            normalize_cell_label(str(record.get("y_pred", ""))),
        )
        for record in records
    ]
    mismatches = [
        record
        for record, (true_label, pred_label) in zip(records, normalized_pairs, strict=False)
        if true_label != pred_label
    ]
    confusion_counts = Counter(
        f"{true_label} -> {pred_label}"
        for true_label, pred_label in normalized_pairs
        if true_label != pred_label
    )
    predicted_label_counts = Counter(pred_label for _, pred_label in normalized_pairs)
    true_id_records = [record for record in records if record.get("true_cl_id")]
    predicted_id_records = [record for record in records if record.get("pred_cl_id")]
    cl_matches = sum(
        normalize_cl_id(record.get("true_cl_id")) == normalize_cl_id(record.get("pred_cl_id"))
        for record in true_id_records
    )
    missing_confidence = sum(1 for record in records if record.get("confidence") is None)
    blank_predictions = sum(
        1 for record in records if not str(record.get("y_pred", "")).strip()
    )

    if examples_output:
        output_path = Path(examples_output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        fieldnames = [
            "tissue",
            "markers",
            "y_true",
            "y_pred",
            "true_cl_id",
            "pred_cl_id",
            "confidence",
            "reasoning",
            "raw_response",
        ]
        with output_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            for record in mismatches[:max_examples]:
                row = {field: record.get(field) for field in fieldnames}
                if isinstance(row["markers"], list):
                    row["markers"] = ", ".join(str(marker) for marker in row["markers"])
                writer.writerow(row)

    return {
        "metrics": metrics,
        "correct": records and metrics["accuracy"] * len(records) or 0,
        "errors": len(mismatches),
        "blank_predictions": blank_predictions,
        "missing_confidence": missing_confidence,
        "records_with_true_cl_id": len(true_id_records),
        "records_with_pred_cl_id": len(predicted_id_records),
        "cl_id_matches": cl_matches,
        "top_predicted_labels": dict(predicted_label_counts.most_common(20)),
        "top_confusions": dict(confusion_counts.most_common(20)),
        "examples_output": str(examples_output) if examples_output else None,
    }


def map_prediction_ontology_ids(
    predictions_path: str | Path,
    marker_db_path: str | Path,
    output_path: str | Path,
    preserve_existing: bool = False,
) -> dict[str, Any]:
    """Fill prediction CL IDs from unambiguous predicted-label matches."""

    records = load_prediction_records(predictions_path)
    marker_records = load_marker_records(marker_db_path)
    label_to_ids: dict[str, set[str]] = {}
    label_to_display: dict[str, str] = {}
    for marker_record in marker_records:
        if not marker_record.cell_ontology_id:
            continue
        for label in label_variants(marker_record.cell_type):
            label_to_ids.setdefault(label, set()).add(marker_record.cell_ontology_id)
            label_to_display.setdefault(label, marker_record.cell_type)

    unambiguous = {
        label: next(iter(ids))
        for label, ids in label_to_ids.items()
        if len(ids) == 1
    }
    ambiguous_labels = {
        label: sorted(ids)
        for label, ids in label_to_ids.items()
        if len(ids) > 1
    }

    mapped = 0
    preserved = 0
    unmapped = 0
    ambiguous = 0
    overwritten = 0
    output_records: list[dict[str, Any]] = []

    for record in records:
        updated = dict(record)
        current_cl_id = normalize_cl_id(updated.get("pred_cl_id"))
        label = normalize_cell_label(str(updated.get("y_pred", "")))
        matched_label = next(
            (
                candidate
                for candidate in label_variants(str(updated.get("y_pred", "")))
                if candidate in unambiguous or candidate in ambiguous_labels
            ),
            label,
        )
        updated.setdefault("original_pred_cl_id", current_cl_id)

        if preserve_existing and current_cl_id:
            preserved += 1
        elif matched_label in unambiguous:
            mapped_cl_id = unambiguous[matched_label]
            if current_cl_id and current_cl_id != mapped_cl_id:
                overwritten += 1
            updated["pred_cl_id"] = mapped_cl_id
            updated["pred_cl_id_source"] = "marker_db_label_map"
            updated["pred_cl_label_match"] = label_to_display[matched_label]
            updated["pred_cl_label_variant"] = matched_label
            mapped += 1
        elif matched_label in ambiguous_labels:
            ambiguous += 1
            updated["pred_cl_id_source"] = "ambiguous_marker_db_label_map"
            updated["pred_cl_id_candidates"] = ambiguous_labels[matched_label]
            updated["pred_cl_label_variant"] = matched_label
        else:
            unmapped += 1
            updated["pred_cl_id_source"] = "unmapped_predicted_label"
        output_records.append(updated)

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in output_records:
            handle.write(json.dumps(record, ensure_ascii=True) + "\n")

    before_metrics = evaluate_predictions(records)
    after_metrics = evaluate_predictions(output_records)
    return {
        "input": str(predictions_path),
        "marker_db": str(marker_db_path),
        "output": str(output_path),
        "records": len(records),
        "mapped": mapped,
        "preserved": preserved,
        "overwritten": overwritten,
        "unmapped": unmapped,
        "ambiguous": ambiguous,
        "unambiguous_label_map_size": len(unambiguous),
        "ambiguous_label_map_size": len(ambiguous_labels),
        "before_cell_ontology_accuracy": before_metrics["cell_ontology_accuracy"],
        "after_cell_ontology_accuracy": after_metrics["cell_ontology_accuracy"],
        "after_accuracy": after_metrics["accuracy"],
        "after_macro_f1": after_metrics["macro_f1"],
    }


def _unambiguous_marker_label_to_cl_id(marker_db_path: str | Path) -> dict[str, str]:
    marker_records = load_marker_records(marker_db_path)
    label_to_ids: dict[str, set[str]] = {}
    for marker_record in marker_records:
        if not marker_record.cell_ontology_id:
            continue
        for label in label_variants(marker_record.cell_type):
            label_to_ids.setdefault(label, set()).add(marker_record.cell_ontology_id)
    return {
        label: next(iter(ids))
        for label, ids in label_to_ids.items()
        if len(ids) == 1
    }


def _load_label_harmonization_rows(path: str | Path) -> dict[str, dict[str, str]]:
    mapping: dict[str, dict[str, str]] = {}
    with Path(path).open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for line_number, row in enumerate(reader, start=2):
            source_label = (
                row.get("predicted_label")
                or row.get("source_label")
                or row.get("y_pred")
                or ""
            ).strip()
            target_label = (
                row.get("harmonized_label")
                or row.get("target_label")
                or row.get("cell_type")
                or ""
            ).strip()
            if not source_label or not target_label:
                raise ValueError(
                    f"{path}:{line_number} requires predicted_label and harmonized_label"
                )
            target_cl_id = normalize_cl_id(
                row.get("harmonized_cl_id")
                or row.get("target_cl_id")
                or row.get("cell_ontology_id")
                or row.get("cl_id")
            )
            entry = {
                "predicted_label": source_label,
                "harmonized_label": target_label,
                "harmonized_cl_id": target_cl_id or "",
                "notes": (row.get("notes") or "").strip(),
            }
            for variant in label_variants(source_label):
                existing = mapping.get(variant)
                if existing and existing["harmonized_label"] != target_label:
                    raise ValueError(
                        f"{path}:{line_number} duplicate predicted-label mapping: "
                        f"{source_label!r}"
                    )
                mapping[variant] = entry
    return mapping


def harmonize_prediction_labels(
    predictions_path: str | Path,
    mapping_path: str | Path,
    output_path: str | Path,
    marker_db_path: str | Path | None = None,
) -> dict[str, Any]:
    """Rewrite prediction labels from an explicit curation table."""

    records = load_prediction_records(predictions_path)
    mapping = _load_label_harmonization_rows(mapping_path)
    marker_label_to_cl_id = (
        _unambiguous_marker_label_to_cl_id(marker_db_path)
        if marker_db_path
        else {}
    )

    harmonized = 0
    unchanged = 0
    filled_cl_ids = 0
    missing_cl_ids = 0
    output_records: list[dict[str, Any]] = []

    for record in records:
        updated = dict(record)
        original_label = str(updated.get("y_pred", ""))
        entry = next(
            (
                mapping[variant]
                for variant in label_variants(original_label)
                if variant in mapping
            ),
            None,
        )
        if entry is None:
            unchanged += 1
            output_records.append(updated)
            continue

        harmonized += 1
        original_cl_id = normalize_cl_id(updated.get("pred_cl_id"))
        target_label = entry["harmonized_label"]
        target_cl_id = normalize_cl_id(entry["harmonized_cl_id"])
        if not target_cl_id and marker_label_to_cl_id:
            target_cl_id = next(
                (
                    marker_label_to_cl_id[variant]
                    for variant in label_variants(target_label)
                    if variant in marker_label_to_cl_id
                ),
                None,
            )
        if target_cl_id:
            filled_cl_ids += int(original_cl_id != target_cl_id)
        else:
            missing_cl_ids += 1

        updated.setdefault("original_y_pred", original_label)
        updated.setdefault("original_pred_cl_id", original_cl_id)
        updated["y_pred"] = target_label
        updated["pred_cl_id"] = target_cl_id
        updated["label_harmonization_source"] = str(mapping_path)
        updated["label_harmonization_predicted_label"] = entry["predicted_label"]
        updated["pred_cl_id_source"] = (
            "prediction_label_harmonization"
            if target_cl_id
            else "prediction_label_harmonization_label_only"
        )
        if entry["notes"]:
            updated["label_harmonization_notes"] = entry["notes"]
        output_records.append(updated)

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in output_records:
            handle.write(json.dumps(record, ensure_ascii=True) + "\n")

    before_metrics = evaluate_predictions(records)
    after_metrics = evaluate_predictions(output_records)
    return {
        "input": str(predictions_path),
        "mapping": str(mapping_path),
        "marker_db": str(marker_db_path) if marker_db_path else None,
        "output": str(output_path),
        "records": len(records),
        "harmonized": harmonized,
        "unchanged": unchanged,
        "filled_cl_ids": filled_cl_ids,
        "missing_cl_ids": missing_cl_ids,
        "mapping_size": len(mapping),
        "before_accuracy": before_metrics["accuracy"],
        "after_accuracy": after_metrics["accuracy"],
        "before_macro_f1": before_metrics["macro_f1"],
        "after_macro_f1": after_metrics["macro_f1"],
        "before_cell_ontology_accuracy": before_metrics["cell_ontology_accuracy"],
        "after_cell_ontology_accuracy": after_metrics["cell_ontology_accuracy"],
    }


def _candidate_label(candidate: dict[str, Any] | None) -> str:
    if not candidate:
        return ""
    return normalize_cell_label(str(candidate.get("cell_type", "")))


def _candidate_rank_for_label(candidates: list[dict[str, Any]], label: str) -> int | None:
    normalized_label = normalize_cell_label(label)
    for candidate in candidates:
        if _candidate_label(candidate) == normalized_label:
            return int(candidate.get("rank", 0))
    return None


def analyze_rerank_prediction_records(
    records: list[dict[str, Any]],
    examples_output: str | Path | None = None,
    max_examples: int = 25,
) -> dict[str, Any]:
    """Audit candidate-reranking behavior beyond final accuracy."""

    metrics = evaluate_predictions(records)
    rows_with_candidates = [
        record
        for record in records
        if isinstance(record.get("candidates"), list) and record.get("candidates")
    ]
    missing_candidates = len(records) - len(rows_with_candidates)

    top1_correct = 0
    oracle_correct = 0
    rerank_correct = 0
    reranker_harmed_top1 = 0
    reranker_fixed_top1 = 0
    selected_rank_counts: Counter[int | str] = Counter()
    selection_source_counts: Counter[str] = Counter()
    candidate_count_counts: Counter[int] = Counter()
    harm_examples: list[dict[str, Any]] = []

    for record in rows_with_candidates:
        candidates = list(record["candidates"])
        true_label = normalize_cell_label(str(record.get("y_true", "")))
        pred_label = normalize_cell_label(str(record.get("y_pred", "")))
        top_candidate = candidates[0]
        top_label = _candidate_label(top_candidate)
        top_is_correct = top_label == true_label
        pred_is_correct = pred_label == true_label
        oracle_rank = _candidate_rank_for_label(candidates, str(record.get("y_true", "")))
        selected_rank = _candidate_rank_for_label(candidates, str(record.get("y_pred", "")))

        top1_correct += int(top_is_correct)
        oracle_correct += int(oracle_rank is not None)
        rerank_correct += int(pred_is_correct)
        reranker_harmed_top1 += int(top_is_correct and not pred_is_correct)
        reranker_fixed_top1 += int(not top_is_correct and pred_is_correct)
        selected_rank_counts.update([selected_rank if selected_rank is not None else "not_in_candidates"])
        selection_source_counts.update([str(record.get("selection_source") or "missing")])
        candidate_count_counts.update([len(candidates)])

        if top_is_correct and not pred_is_correct and len(harm_examples) < max_examples:
            harm_examples.append(record)

    if examples_output:
        output_path = Path(examples_output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        fieldnames = [
            "tissue",
            "markers",
            "y_true",
            "y_pred",
            "true_cl_id",
            "pred_cl_id",
            "selection_source",
            "top_candidate",
            "top_candidate_cl_id",
            "selected_rank",
            "raw_response",
        ]
        with output_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            for record in harm_examples:
                candidates = list(record.get("candidates") or [])
                top_candidate = candidates[0] if candidates else {}
                selected_rank = _candidate_rank_for_label(candidates, str(record.get("y_pred", "")))
                markers = record.get("markers")
                writer.writerow(
                    {
                        "tissue": record.get("tissue"),
                        "markers": ", ".join(str(marker) for marker in markers)
                        if isinstance(markers, list)
                        else markers,
                        "y_true": record.get("y_true"),
                        "y_pred": record.get("y_pred"),
                        "true_cl_id": record.get("true_cl_id"),
                        "pred_cl_id": record.get("pred_cl_id"),
                        "selection_source": record.get("selection_source"),
                        "top_candidate": top_candidate.get("cell_type"),
                        "top_candidate_cl_id": top_candidate.get("cell_ontology_id"),
                        "selected_rank": selected_rank,
                        "raw_response": record.get("raw_response"),
                    }
                )

    denominator = len(rows_with_candidates)
    return {
        "metrics": metrics,
        "records": len(records),
        "records_with_candidates": denominator,
        "missing_candidates": missing_candidates,
        "top1_candidate_accuracy": _safe_divide(top1_correct, denominator),
        "oracle_top_k_accuracy": _safe_divide(oracle_correct, denominator),
        "rerank_accuracy": _safe_divide(rerank_correct, denominator),
        "reranker_harmed_top1": reranker_harmed_top1,
        "reranker_fixed_top1": reranker_fixed_top1,
        "selected_rank_counts": dict(selected_rank_counts),
        "selection_source_counts": dict(selection_source_counts),
        "candidate_count_counts": dict(candidate_count_counts),
        "harm_examples_output": str(examples_output) if examples_output else None,
    }
