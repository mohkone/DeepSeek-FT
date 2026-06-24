"""Render supplementary label coverage and reranker confusion artifacts."""

from __future__ import annotations

import csv
import html
import json
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPLIT_DIR = ROOT / "data" / "processed" / "panglaodb_cl_curated_label_overlap_splits"
PREDICTIONS_PATH = ROOT / "outputs" / "deepseek_lora_rerank_label_overlap_predictions.jsonl"
LABEL_CSV_PATH = ROOT / "outputs" / "label_support_ontology_coverage.csv"
LABEL_MD_PATH = ROOT / "outputs" / "label_support_ontology_coverage.md"
CONFUSION_MATRIX_PATH = ROOT / "outputs" / "deepseek_lora_rerank_confusion_matrix.csv"
TOP_CONFUSIONS_CSV_PATH = ROOT / "outputs" / "deepseek_lora_rerank_top_confusions.csv"
TOP_CONFUSIONS_SVG_PATH = ROOT / "outputs" / "deepseek_lora_rerank_top_confusions.svg"


def read_jsonl(path: Path) -> list[dict]:
    records = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def format_float(value: float) -> str:
    return f"{value:.4f}"


def build_label_support_rows() -> list[dict[str, str | int | float]]:
    by_label: dict[str, dict[str, object]] = {}
    split_names = ["train", "validation", "test"]
    for split_name in split_names:
        for record in read_jsonl(SPLIT_DIR / f"{split_name}.jsonl"):
            metadata = record.get("metadata", {})
            label = str(metadata.get("cell_type", "")).strip()
            if not label:
                continue
            cl_id = str(metadata.get("cell_ontology_id") or "").strip()
            row = by_label.setdefault(
                label,
                {
                    "label": label,
                    "total_examples": 0,
                    "train_examples": 0,
                    "validation_examples": 0,
                    "test_examples": 0,
                    "examples_with_cl_id": 0,
                    "cl_ids": Counter(),
                },
            )
            row["total_examples"] = int(row["total_examples"]) + 1
            row[f"{split_name}_examples"] = int(row[f"{split_name}_examples"]) + 1
            if cl_id:
                row["examples_with_cl_id"] = int(row["examples_with_cl_id"]) + 1
                row["cl_ids"][cl_id] += 1

    rows: list[dict[str, str | int | float]] = []
    for row in by_label.values():
        total = int(row["total_examples"])
        with_cl = int(row["examples_with_cl_id"])
        cl_ids = row["cl_ids"]
        rows.append(
            {
                "label": str(row["label"]),
                "total_examples": total,
                "train_examples": int(row["train_examples"]),
                "validation_examples": int(row["validation_examples"]),
                "test_examples": int(row["test_examples"]),
                "examples_with_cl_id": with_cl,
                "ontology_coverage": with_cl / total if total else 0.0,
                "cell_ontology_ids": ";".join(sorted(cl_ids)),
            }
        )
    rows.sort(key=lambda row: str(row["label"]).lower())
    return rows


def write_label_support(rows: list[dict[str, str | int | float]]) -> None:
    fieldnames = [
        "label",
        "total_examples",
        "train_examples",
        "validation_examples",
        "test_examples",
        "examples_with_cl_id",
        "ontology_coverage",
        "cell_ontology_ids",
    ]
    LABEL_CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LABEL_CSV_PATH.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            out = dict(row)
            out["ontology_coverage"] = format_float(float(out["ontology_coverage"]))
            writer.writerow(out)

    lines = [
        "| Label | Total | Train | Validation | Test | With CL ID | Ontology coverage | CL IDs |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in rows:
        lines.append(
            "| {label} | {total_examples} | {train_examples} | {validation_examples} | "
            "{test_examples} | {examples_with_cl_id} | {ontology_coverage} | {cell_ontology_ids} |".format(
                label=str(row["label"]).replace("|", "\\|"),
                total_examples=row["total_examples"],
                train_examples=row["train_examples"],
                validation_examples=row["validation_examples"],
                test_examples=row["test_examples"],
                examples_with_cl_id=row["examples_with_cl_id"],
                ontology_coverage=format_float(float(row["ontology_coverage"])),
                cell_ontology_ids=str(row["cell_ontology_ids"]) or "NA",
            )
        )
    LABEL_MD_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_confusion_artifacts() -> tuple[list[str], dict[str, Counter[str]], list[dict[str, int | str]]]:
    predictions = read_jsonl(PREDICTIONS_PATH)
    labels = sorted(
        {str(record.get("y_true", "")).strip() for record in predictions}
        | {str(record.get("y_pred", "")).strip() for record in predictions},
        key=str.lower,
    )
    matrix: dict[str, Counter[str]] = defaultdict(Counter)
    for record in predictions:
        true_label = str(record.get("y_true", "")).strip()
        pred_label = str(record.get("y_pred", "")).strip()
        if true_label and pred_label:
            matrix[true_label][pred_label] += 1

    top_confusions = []
    for true_label, pred_counts in matrix.items():
        for pred_label, count in pred_counts.items():
            if true_label != pred_label:
                top_confusions.append(
                    {"true_label": true_label, "predicted_label": pred_label, "count": count}
                )
    top_confusions.sort(
        key=lambda row: (-int(row["count"]), str(row["true_label"]).lower(), str(row["predicted_label"]).lower())
    )
    return labels, matrix, top_confusions


def write_confusion_csv(labels: list[str], matrix: dict[str, Counter[str]]) -> None:
    with CONFUSION_MATRIX_PATH.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["true_label", *labels])
        for true_label in labels:
            writer.writerow([true_label, *[matrix[true_label][pred_label] for pred_label in labels]])


def write_top_confusions_csv(rows: list[dict[str, int | str]]) -> None:
    with TOP_CONFUSIONS_CSV_PATH.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["true_label", "predicted_label", "count"])
        writer.writeheader()
        writer.writerows(rows)


def render_top_confusions_svg(rows: list[dict[str, int | str]], limit: int = 15) -> str:
    top_rows = rows[:limit]
    width = 980
    row_height = 32
    margin_left = 320
    margin_right = 40
    margin_top = 74
    margin_bottom = 46
    plot_width = width - margin_left - margin_right
    height = margin_top + margin_bottom + max(1, len(top_rows)) * row_height
    max_count = max([int(row["count"]) for row in top_rows] or [1])

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">',
        "<title>Top LoRA rerank confusions</title>",
        "<desc>Highest-count off-diagonal true versus predicted label pairs for DeepSeek LoRA reranking.</desc>",
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        '<text x="28" y="32" font-family="Arial, sans-serif" font-size="20" font-weight="700" fill="#111827">Top DeepSeek LoRA rerank confusions</text>',
        '<text x="28" y="53" font-family="Arial, sans-serif" font-size="12" fill="#4b5563">Off-diagonal label pairs on the PanglaoDB label-overlap test set</text>',
    ]

    if not top_rows:
        parts.append(
            '<text x="28" y="95" font-family="Arial, sans-serif" font-size="14" fill="#374151">No off-diagonal confusions.</text>'
        )
    for index, row in enumerate(top_rows):
        y = margin_top + index * row_height
        true_label = html.escape(str(row["true_label"]))
        predicted_label = html.escape(str(row["predicted_label"]))
        count = int(row["count"])
        bar_width = (count / max_count) * plot_width
        fill = "#dc2626" if count == max_count else "#f97316"
        parts.append(
            f'<text x="28" y="{y + 20}" font-family="Arial, sans-serif" font-size="12" fill="#111827">{true_label} -> {predicted_label}</text>'
        )
        parts.append(
            f'<rect x="{margin_left}" y="{y + 6}" width="{bar_width:.1f}" height="18" rx="2" fill="{fill}"/>'
        )
        parts.append(
            f'<text x="{margin_left + bar_width + 8:.1f}" y="{y + 20}" font-family="Arial, sans-serif" font-size="12" fill="#111827">{count}</text>'
        )

    parts.append("</svg>")
    return "\n".join(parts)


def main() -> None:
    label_rows = build_label_support_rows()
    write_label_support(label_rows)
    labels, matrix, top_confusions = build_confusion_artifacts()
    write_confusion_csv(labels, matrix)
    write_top_confusions_csv(top_confusions)
    TOP_CONFUSIONS_SVG_PATH.write_text(render_top_confusions_svg(top_confusions), encoding="utf-8")
    print(
        json.dumps(
            {
                "label_support_csv": str(LABEL_CSV_PATH),
                "label_support_md": str(LABEL_MD_PATH),
                "labels": len(label_rows),
                "confusion_matrix_csv": str(CONFUSION_MATRIX_PATH),
                "top_confusions_csv": str(TOP_CONFUSIONS_CSV_PATH),
                "top_confusions_svg": str(TOP_CONFUSIONS_SVG_PATH),
                "off_diagonal_pairs": len(top_confusions),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
