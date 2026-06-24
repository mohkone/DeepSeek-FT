"""Render manuscript figures from DeepSeekCell-FT experiment summaries."""

from __future__ import annotations

import csv
import html
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SUMMARY_PATH = ROOT / "outputs" / "experiment_summary.json"
CSV_PATH = ROOT / "outputs" / "noise_robustness_accuracy.csv"
SVG_PATH = ROOT / "outputs" / "noise_robustness_accuracy.svg"


NOISE_ORDER = [
    ("clean", 0, 0),
    ("drop50/noise3", 50, 3),
    ("drop75/noise5", 75, 5),
    ("drop90/noise8", 90, 8),
]


def load_predictions() -> dict[str, dict]:
    with SUMMARY_PATH.open("r", encoding="utf-8") as handle:
        summary = json.load(handle)
    return {row["name"]: row for row in summary["predictions"]}


def build_rows(predictions: dict[str, dict]) -> list[dict[str, str | float | int]]:
    specs = [
        (
            "clean",
            "marker-overlap",
            "label_overlap_marker_overlap",
        ),
        (
            "clean",
            "DeepSeek-7B LoRA rerank",
            "label_overlap_deepseek_lora_rerank",
        ),
        (
            "drop50/noise3",
            "marker-overlap",
            "label_overlap_drop50_noise3_marker_overlap",
        ),
        (
            "drop50/noise3",
            "DeepSeek-7B LoRA rerank",
            "label_overlap_drop50_noise3_deepseek_lora_rerank",
        ),
        (
            "drop75/noise5",
            "marker-overlap",
            "label_overlap_drop75_noise5_marker_overlap",
        ),
        (
            "drop75/noise5",
            "DeepSeek-7B LoRA rerank",
            "label_overlap_drop75_noise5_deepseek_lora_rerank",
        ),
        (
            "drop90/noise8",
            "marker-overlap",
            "label_overlap_drop90_noise8_marker_overlap",
        ),
        (
            "drop90/noise8",
            "DeepSeek-7B LoRA rerank",
            "label_overlap_drop90_noise8_deepseek_lora_rerank",
        ),
    ]
    noise_lookup = {label: (drop_rate, noise_count) for label, drop_rate, noise_count in NOISE_ORDER}
    rows: list[dict[str, str | float | int]] = []
    for noise_label, method, name in specs:
        if name not in predictions:
            continue
        drop_rate, noise_count = noise_lookup[noise_label]
        metric = predictions[name]
        rows.append(
            {
                "noise_setting": noise_label,
                "drop_rate_percent": drop_rate,
                "noise_markers": noise_count,
                "method": method,
                "accuracy": metric["accuracy"],
                "macro_f1": metric["macro_f1"],
                "cell_ontology_accuracy": metric["cell_ontology_accuracy"],
                "expected_calibration_error": metric["expected_calibration_error"],
                "mean_runtime_seconds": metric["mean_runtime_seconds"],
            }
        )
    return rows


def write_csv(rows: list[dict[str, str | float | int]]) -> None:
    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    with CSV_PATH.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def render_svg(rows: list[dict[str, str | float | int]]) -> str:
    width = 900
    height = 520
    margin_left = 88
    margin_right = 34
    margin_top = 48
    margin_bottom = 92
    plot_width = width - margin_left - margin_right
    plot_height = height - margin_top - margin_bottom
    min_y = 0.30
    max_y = 1.00
    x_values = [drop for _, drop, _ in NOISE_ORDER]
    min_x = min(x_values)
    max_x = max(x_values)

    def x_pos(drop_rate: float) -> float:
        return margin_left + ((drop_rate - min_x) / (max_x - min_x)) * plot_width

    def y_pos(value: float) -> float:
        return margin_top + ((max_y - value) / (max_y - min_y)) * plot_height

    by_method: dict[str, list[dict[str, str | float | int]]] = {}
    for row in rows:
        by_method.setdefault(str(row["method"]), []).append(row)
    for method_rows in by_method.values():
        method_rows.sort(key=lambda row: float(row["drop_rate_percent"]))

    colors = {
        "marker-overlap": "#2563eb",
        "DeepSeek-7B LoRA rerank": "#dc2626",
    }

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" '
        'aria-labelledby="title desc">',
        "<title>Noise robustness accuracy</title>",
        "<desc>Accuracy curves for marker-overlap and DeepSeek-7B LoRA reranking under marker dropout and distractor noise.</desc>",
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        f'<text x="{margin_left}" y="30" font-family="Arial, sans-serif" font-size="20" font-weight="700" fill="#111827">Noise robustness on label-overlap test set</text>',
        f'<text x="{margin_left}" y="50" font-family="Arial, sans-serif" font-size="12" fill="#4b5563">Accuracy after dropping marker genes and adding distractor markers</text>',
    ]

    for tick in [0.4, 0.6, 0.8, 1.0]:
        y = y_pos(tick)
        parts.append(
            f'<line x1="{margin_left}" y1="{y:.1f}" x2="{width - margin_right}" y2="{y:.1f}" stroke="#e5e7eb"/>'
        )
        parts.append(
            f'<text x="{margin_left - 14}" y="{y + 4:.1f}" text-anchor="end" font-family="Arial, sans-serif" font-size="12" fill="#4b5563">{tick:.1f}</text>'
        )

    parts.append(
        f'<line x1="{margin_left}" y1="{margin_top}" x2="{margin_left}" y2="{height - margin_bottom}" stroke="#111827"/>'
    )
    parts.append(
        f'<line x1="{margin_left}" y1="{height - margin_bottom}" x2="{width - margin_right}" y2="{height - margin_bottom}" stroke="#111827"/>'
    )

    for label, drop_rate, noise_count in NOISE_ORDER:
        x = x_pos(drop_rate)
        parts.append(
            f'<line x1="{x:.1f}" y1="{height - margin_bottom}" x2="{x:.1f}" y2="{height - margin_bottom + 6}" stroke="#111827"/>'
        )
        parts.append(
            f'<text x="{x:.1f}" y="{height - margin_bottom + 24}" text-anchor="middle" font-family="Arial, sans-serif" font-size="12" fill="#374151">{html.escape(label)}</text>'
        )
        parts.append(
            f'<text x="{x:.1f}" y="{height - margin_bottom + 40}" text-anchor="middle" font-family="Arial, sans-serif" font-size="11" fill="#6b7280">drop {drop_rate}% / +{noise_count}</text>'
        )

    parts.append(
        f'<text x="{margin_left + plot_width / 2:.1f}" y="{height - 18}" text-anchor="middle" font-family="Arial, sans-serif" font-size="13" fill="#111827">Perturbation setting</text>'
    )
    parts.append(
        f'<text transform="translate(24 {margin_top + plot_height / 2:.1f}) rotate(-90)" text-anchor="middle" font-family="Arial, sans-serif" font-size="13" fill="#111827">Accuracy</text>'
    )

    for method, method_rows in by_method.items():
        color = colors.get(method, "#111827")
        points = [
            (x_pos(float(row["drop_rate_percent"])), y_pos(float(row["accuracy"])), float(row["accuracy"]))
            for row in method_rows
        ]
        point_attr = " ".join(f"{x:.1f},{y:.1f}" for x, y, _ in points)
        parts.append(
            f'<polyline points="{point_attr}" fill="none" stroke="{color}" stroke-width="3" stroke-linejoin="round" stroke-linecap="round"/>'
        )
        for x, y, value in points:
            parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5" fill="{color}" stroke="#ffffff" stroke-width="2"/>')
            parts.append(
                f'<text x="{x:.1f}" y="{y - 10:.1f}" text-anchor="middle" font-family="Arial, sans-serif" font-size="11" fill="{color}">{value:.3f}</text>'
            )

    legend_x = width - margin_right - 260
    legend_y = margin_top + 8
    for index, method in enumerate(["marker-overlap", "DeepSeek-7B LoRA rerank"]):
        y = legend_y + index * 24
        color = colors[method]
        parts.append(f'<line x1="{legend_x}" y1="{y}" x2="{legend_x + 28}" y2="{y}" stroke="{color}" stroke-width="3"/>')
        parts.append(f'<circle cx="{legend_x + 14}" cy="{y}" r="4" fill="{color}"/>')
        parts.append(
            f'<text x="{legend_x + 38}" y="{y + 4}" font-family="Arial, sans-serif" font-size="13" fill="#111827">{html.escape(method)}</text>'
        )

    parts.append("</svg>")
    return "\n".join(parts)


def main() -> None:
    predictions = load_predictions()
    rows = build_rows(predictions)
    if not rows:
        raise SystemExit("No robustness rows found in outputs/experiment_summary.json")
    write_csv(rows)
    SVG_PATH.write_text(render_svg(rows), encoding="utf-8")
    print(json.dumps({"csv": str(CSV_PATH), "svg": str(SVG_PATH), "rows": len(rows)}, indent=2))


if __name__ == "__main__":
    main()

