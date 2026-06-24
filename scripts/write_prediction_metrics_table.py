"""Write a compact metric table from prediction JSONL files."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from deepseekcell_ft.evaluation import evaluate_predictions, load_prediction_records


def parse_prediction_spec(spec: str) -> tuple[str, Path]:
    if "=" in spec:
        name, path = spec.split("=", 1)
        return name.strip(), Path(path.strip())
    path = Path(spec)
    return path.stem, path


def format_metric(value: float | int | None) -> str:
    if value is None:
        return "NA"
    if isinstance(value, int):
        return str(value)
    return f"{value:.4f}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Write a compact prediction metric table.")
    parser.add_argument(
        "--prediction",
        action="append",
        required=True,
        help="Prediction spec as Method=path; may be repeated",
    )
    parser.add_argument("--output-markdown", type=Path)
    parser.add_argument("--output-csv", type=Path)
    parser.add_argument("--output-json", type=Path)
    parser.add_argument("--skip-missing", action="store_true")
    args = parser.parse_args()

    rows: list[dict[str, object]] = []
    for spec in args.prediction:
        method, path = parse_prediction_spec(spec)
        if not path.exists():
            if args.skip_missing:
                continue
            raise FileNotFoundError(path)
        metrics = evaluate_predictions(load_prediction_records(path))
        rows.append(
            {
                "method": method,
                "path": str(path),
                "n": metrics["n"],
                "accuracy": metrics["accuracy"],
                "macro_f1": metrics["macro_f1"],
                "cell_ontology_accuracy": metrics["cell_ontology_accuracy"],
            }
        )

    if args.output_json:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(json.dumps(rows, indent=2, sort_keys=True), encoding="utf-8")

    if args.output_csv:
        args.output_csv.parent.mkdir(parents=True, exist_ok=True)
        with args.output_csv.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    "method",
                    "n",
                    "accuracy",
                    "macro_f1",
                    "cell_ontology_accuracy",
                    "path",
                ],
            )
            writer.writeheader()
            writer.writerows(rows)

    markdown_lines = [
        "| Method | n | Accuracy | Macro-F1 | CL Accuracy |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for row in rows:
        markdown_lines.append(
            "| {method} | {n} | {accuracy} | {macro_f1} | {cell_ontology_accuracy} |".format(
                method=row["method"],
                n=row["n"],
                accuracy=format_metric(row["accuracy"]),
                macro_f1=format_metric(row["macro_f1"]),
                cell_ontology_accuracy=format_metric(row["cell_ontology_accuracy"]),
            )
        )
    markdown = "\n".join(markdown_lines) + "\n"
    if args.output_markdown:
        args.output_markdown.parent.mkdir(parents=True, exist_ok=True)
        args.output_markdown.write_text(markdown, encoding="utf-8")
    print(markdown, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
