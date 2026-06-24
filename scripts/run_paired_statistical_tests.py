"""Run paired statistical tests for manuscript method comparisons."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from deepseekcell_ft.evaluation import load_prediction_records
from deepseekcell_ft.statistics import paired_comparison


DEFAULT_COMPARISONS = [
    (
        "label_overlap_marker_vs_lora_rerank",
        "Marker overlap",
        "DeepSeek LoRA rerank",
        "outputs/panglaodb_cl_curated_marker_overlap_label_overlap.jsonl",
        "outputs/deepseek_lora_rerank_label_overlap_predictions.jsonl",
    ),
    (
        "label_overlap_lora_rerank_vs_lora_open_ended",
        "DeepSeek LoRA rerank",
        "DeepSeek LoRA open-ended",
        "outputs/deepseek_lora_rerank_label_overlap_predictions.jsonl",
        "outputs/deepseek_lora_label_overlap_predictions.mapped.jsonl",
    ),
    (
        "drop50_noise3_marker_vs_lora_rerank",
        "Marker overlap",
        "DeepSeek LoRA rerank",
        "outputs/marker_overlap_label_overlap_perturbed_drop50_noise3.jsonl",
        "outputs/deepseek_lora_rerank_label_overlap_perturbed_drop50_noise3.jsonl",
    ),
    (
        "drop75_noise5_marker_vs_lora_rerank",
        "Marker overlap",
        "DeepSeek LoRA rerank",
        "outputs/marker_overlap_label_overlap_perturbed_drop75_noise5.jsonl",
        "outputs/deepseek_lora_rerank_label_overlap_perturbed_drop75_noise5.jsonl",
    ),
    (
        "drop90_noise8_marker_vs_lora_rerank",
        "Marker overlap",
        "DeepSeek LoRA rerank",
        "outputs/marker_overlap_label_overlap_perturbed_drop90_noise8.jsonl",
        "outputs/deepseek_lora_rerank_label_overlap_perturbed_drop90_noise8.jsonl",
    ),
]


def format_metric(value: float | int | None) -> str:
    if value is None:
        return "NA"
    if isinstance(value, int):
        return str(value)
    return f"{value:.4f}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-json", type=Path, default=Path("outputs/paired_statistical_tests.json"))
    parser.add_argument("--output-csv", type=Path, default=Path("outputs/paired_statistical_tests.csv"))
    parser.add_argument("--output-markdown", type=Path, default=Path("outputs/paired_statistical_tests.md"))
    parser.add_argument("--bootstrap", type=int, default=500)
    parser.add_argument("--seed", type=int, default=13)
    parser.add_argument("--skip-missing", action="store_true")
    args = parser.parse_args()

    rows: list[dict[str, object]] = []
    for index, (name, method_a, method_b, path_a, path_b) in enumerate(DEFAULT_COMPARISONS):
        left = Path(path_a)
        right = Path(path_b)
        if not left.exists() or not right.exists():
            if args.skip_missing:
                continue
            missing = [str(path) for path in (left, right) if not path.exists()]
            raise FileNotFoundError(", ".join(missing))
        comparison = paired_comparison(
            load_prediction_records(left),
            load_prediction_records(right),
            n_bootstrap=args.bootstrap,
            seed=args.seed + index,
        )
        rows.append(
            {
                "comparison": name,
                "method_a": method_a,
                "method_b": method_b,
                "n": comparison.n,
                "method_a_accuracy": comparison.method_a_accuracy,
                "method_b_accuracy": comparison.method_b_accuracy,
                "accuracy_delta_a_minus_b": comparison.accuracy_delta,
                "accuracy_delta_ci_low": comparison.accuracy_delta_ci_low,
                "accuracy_delta_ci_high": comparison.accuracy_delta_ci_high,
                "method_a_macro_f1": comparison.method_a_macro_f1,
                "method_b_macro_f1": comparison.method_b_macro_f1,
                "macro_f1_delta_a_minus_b": comparison.macro_f1_delta,
                "macro_f1_delta_ci_low": comparison.macro_f1_delta_ci_low,
                "macro_f1_delta_ci_high": comparison.macro_f1_delta_ci_high,
                "a_only_correct": comparison.a_only_correct,
                "b_only_correct": comparison.b_only_correct,
                "both_correct": comparison.both_correct,
                "both_wrong": comparison.both_wrong,
                "mcnemar_p_value": comparison.mcnemar_p_value,
                "path_a": str(left),
                "path_b": str(right),
            }
        )

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(rows, indent=2, sort_keys=True), encoding="utf-8")

    with args.output_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]) if rows else [])
        if rows:
            writer.writeheader()
            writer.writerows(rows)

    markdown_lines = [
        "| Comparison | Method A | Method B | n | Accuracy A | Accuracy B | Delta A-B (95% CI) | Macro-F1 Delta (95% CI) | McNemar p |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in rows:
        markdown_lines.append(
            "| {comparison} | {method_a} | {method_b} | {n} | {acc_a} | {acc_b} | {acc_delta} ({acc_low}, {acc_high}) | {f1_delta} ({f1_low}, {f1_high}) | {p_value} |".format(
                comparison=row["comparison"],
                method_a=row["method_a"],
                method_b=row["method_b"],
                n=row["n"],
                acc_a=format_metric(row["method_a_accuracy"]),
                acc_b=format_metric(row["method_b_accuracy"]),
                acc_delta=format_metric(row["accuracy_delta_a_minus_b"]),
                acc_low=format_metric(row["accuracy_delta_ci_low"]),
                acc_high=format_metric(row["accuracy_delta_ci_high"]),
                f1_delta=format_metric(row["macro_f1_delta_a_minus_b"]),
                f1_low=format_metric(row["macro_f1_delta_ci_low"]),
                f1_high=format_metric(row["macro_f1_delta_ci_high"]),
                p_value=format_metric(row["mcnemar_p_value"]),
            )
        )
    markdown = "\n".join(markdown_lines) + "\n"
    args.output_markdown.write_text(markdown, encoding="utf-8")
    print(markdown, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
