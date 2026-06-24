"""Build instruction-tuning datasets from curated marker evidence."""

from __future__ import annotations

import csv
import json
import random
from collections import defaultdict
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

from .normalization import normalize_cell_label, parse_marker_list
from .prompts import SYSTEM_PROMPT, build_assistant_response, build_reasoning, build_user_prompt
from .schemas import AnnotationExample, MarkerRecord

MARKER_COLUMNS = ("markers", "positive_markers", "cluster_markers", "marker_genes")


def _first_present(row: dict[str, str], columns: Iterable[str]) -> str | None:
    lowered = {key.lower(): value for key, value in row.items()}
    for column in columns:
        value = lowered.get(column.lower())
        if value:
            return value
    return None


def load_marker_records(path: str | Path) -> list[MarkerRecord]:
    """Load marker evidence from CSV."""

    path = Path(path)
    records: list[MarkerRecord] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for line_number, row in enumerate(reader, start=2):
            tissue = _first_present(row, ("tissue", "organ", "dataset_tissue"))
            cell_type = _first_present(row, ("cell_type", "celltype", "label", "annotation"))
            marker_value = _first_present(row, MARKER_COLUMNS)
            if not tissue or not cell_type or not marker_value:
                raise ValueError(
                    f"{path}:{line_number} requires tissue, cell_type, and marker columns"
                )

            records.append(
                MarkerRecord(
                    tissue=tissue,
                    cell_type=cell_type,
                    markers=parse_marker_list(marker_value),
                    cell_ontology_id=_first_present(
                        row,
                        ("cell_ontology_id", "cl_id", "ontology_id", "cellontology_id"),
                    ),
                    source=_first_present(row, ("source", "database", "reference")),
                    evidence=_first_present(row, ("evidence", "description", "note")),
                    metadata={
                        key: value
                        for key, value in row.items()
                        if key
                        and key.lower()
                        not in {
                            "tissue",
                            "organ",
                            "dataset_tissue",
                            "cell_type",
                            "celltype",
                            "label",
                            "annotation",
                            "markers",
                            "positive_markers",
                            "cluster_markers",
                            "marker_genes",
                            "cell_ontology_id",
                            "cl_id",
                            "ontology_id",
                            "cellontology_id",
                            "source",
                            "database",
                            "reference",
                            "evidence",
                            "description",
                            "note",
                        }
                    },
                )
            )
    return records


def _sample_markers(
    markers: Sequence[str],
    rng: random.Random,
    min_markers: int,
    max_markers: int,
    noise_markers: Sequence[str],
    noise_rate: float,
) -> tuple[str, ...]:
    if not markers:
        return ()

    upper = min(max_markers, len(markers))
    lower = min(min_markers, upper)
    size = rng.randint(lower, upper) if lower < upper else upper
    sampled = list(rng.sample(list(markers), k=size))

    if noise_markers and rng.random() < noise_rate:
        noise_count = 1 if len(noise_markers) < 3 else rng.randint(1, 2)
        sampled.extend(rng.sample(list(noise_markers), k=min(noise_count, len(noise_markers))))

    rng.shuffle(sampled)
    return tuple(sampled)


def generate_examples(
    records: Sequence[MarkerRecord],
    examples_per_record: int = 16,
    min_markers: int = 3,
    max_markers: int = 8,
    noise_markers: Sequence[str] | None = None,
    noise_rate: float = 0.15,
    seed: int = 13,
) -> list[AnnotationExample]:
    """Generate robust instruction examples from marker evidence."""

    if examples_per_record < 1:
        raise ValueError("examples_per_record must be at least 1")

    rng = random.Random(seed)
    all_markers = sorted({marker for record in records for marker in record.markers})
    explicit_noise = tuple(noise_markers or ())
    examples: list[AnnotationExample] = []

    for record in records:
        record_noise = tuple(marker for marker in all_markers if marker not in set(record.markers))
        candidate_noise = explicit_noise or record_noise
        for index in range(examples_per_record):
            markers = _sample_markers(
                record.markers,
                rng=rng,
                min_markers=min_markers,
                max_markers=max_markers,
                noise_markers=candidate_noise,
                noise_rate=noise_rate,
            )
            reasoning = build_reasoning(record.cell_type, markers, record.evidence)
            prompt = build_user_prompt(record.tissue, markers)
            response = build_assistant_response(
                cell_type=record.cell_type,
                cell_ontology_id=record.cell_ontology_id,
                confidence=0.90,
                reasoning=reasoning,
            )
            examples.append(
                AnnotationExample(
                    tissue=record.tissue,
                    markers=markers,
                    cell_type=record.cell_type,
                    cell_ontology_id=record.cell_ontology_id,
                    reasoning=reasoning,
                    source=record.source,
                    prompt=prompt,
                    response=response,
                    metadata={"augmentation_index": index},
                )
            )

    rng.shuffle(examples)
    return examples


def example_to_json_dict(example: AnnotationExample, output_format: str = "chat") -> dict[str, Any]:
    """Convert an example into a JSON-serializable fine-tuning record."""

    prompt = example.prompt or build_user_prompt(example.tissue, example.markers)
    response = example.response or build_assistant_response(
        cell_type=example.cell_type,
        cell_ontology_id=example.cell_ontology_id,
        reasoning=example.reasoning,
    )
    metadata = {
        "tissue": example.tissue,
        "cell_type": example.cell_type,
        "cell_ontology_id": example.cell_ontology_id,
        "markers": list(example.markers),
        "source": example.source,
        **example.metadata,
    }

    if output_format == "chat":
        return {
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
                {"role": "assistant", "content": response},
            ],
            "metadata": metadata,
        }
    if output_format == "instruction":
        return {
            "instruction": "Annotate the single-cell RNA-seq cluster from marker genes.",
            "input": prompt,
            "output": response,
            "metadata": metadata,
        }
    raise ValueError("output_format must be 'chat' or 'instruction'")


def write_jsonl(
    examples: Sequence[AnnotationExample],
    path: str | Path,
    output_format: str = "chat",
) -> None:
    """Write examples to JSONL."""

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for example in examples:
            handle.write(
                json.dumps(example_to_json_dict(example, output_format), ensure_ascii=True) + "\n"
            )


def read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    """Read a JSONL file."""

    records: list[dict[str, Any]] = []
    with Path(path).open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number} is not valid JSON") from exc
    return records


def _write_jsonl_records(records: Sequence[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=True) + "\n")


def perturb_instruction_markers(
    input_path: str | Path,
    output_path: str | Path,
    marker_db_path: str | Path,
    drop_rate: float = 0.5,
    add_noise_markers: int = 3,
    min_markers: int = 1,
    seed: int = 13,
) -> dict[str, Any]:
    """Create a harder split by dropping markers and adding distractors."""

    if not 0.0 <= drop_rate <= 1.0:
        raise ValueError("drop_rate must be between 0 and 1")
    if add_noise_markers < 0:
        raise ValueError("add_noise_markers must be non-negative")
    if min_markers < 1:
        raise ValueError("min_markers must be at least 1")

    records = read_jsonl(input_path)
    marker_records = load_marker_records(marker_db_path)
    all_markers = sorted({marker for marker_record in marker_records for marker in marker_record.markers})
    markers_by_label: dict[str, set[str]] = defaultdict(set)
    for marker_record in marker_records:
        markers_by_label[normalize_cell_label(marker_record.cell_type)].update(marker_record.markers)

    rng = random.Random(seed)
    perturbed: list[dict[str, Any]] = []
    original_counts: list[int] = []
    perturbed_counts: list[int] = []
    total_dropped = 0
    total_added = 0

    for record in records:
        metadata = dict(record.get("metadata") or {})
        tissue = str(metadata.get("tissue") or "")
        cell_type = str(metadata.get("cell_type") or "")
        original_markers = list(parse_marker_list(metadata.get("markers") or ()))
        if not original_markers:
            raise ValueError("record metadata markers must not be empty")

        kept = [marker for marker in original_markers if rng.random() >= drop_rate]
        if len(kept) < min_markers:
            kept = rng.sample(original_markers, k=min(min_markers, len(original_markers)))
        dropped = max(0, len(original_markers) - len(kept))

        same_label_markers = markers_by_label.get(normalize_cell_label(cell_type), set())
        distractors = [
            marker
            for marker in all_markers
            if marker not in set(original_markers) and marker not in same_label_markers
        ]
        added = rng.sample(distractors, k=min(add_noise_markers, len(distractors)))
        new_markers = list(dict.fromkeys(kept + added))
        rng.shuffle(new_markers)

        updated = dict(record)
        metadata.update(
            {
                "markers": new_markers,
                "original_markers": original_markers,
                "perturbation": {
                    "drop_rate": drop_rate,
                    "add_noise_markers": add_noise_markers,
                    "dropped_markers": dropped,
                    "added_markers": added,
                },
            }
        )
        updated["metadata"] = metadata

        prompt = build_user_prompt(tissue, new_markers)
        if isinstance(updated.get("messages"), list):
            messages = []
            for message in updated["messages"]:
                if isinstance(message, dict) and message.get("role") == "user":
                    message = {**message, "content": prompt}
                messages.append(message)
            updated["messages"] = messages
        if "input" in updated:
            updated["input"] = prompt

        perturbed.append(updated)
        original_counts.append(len(original_markers))
        perturbed_counts.append(len(new_markers))
        total_dropped += dropped
        total_added += len(added)

    output_path = Path(output_path)
    _write_jsonl_records(perturbed, output_path)
    return {
        "input": str(input_path),
        "output": str(output_path),
        "marker_db": str(marker_db_path),
        "records": len(perturbed),
        "drop_rate": drop_rate,
        "add_noise_markers": add_noise_markers,
        "min_markers": min_markers,
        "seed": seed,
        "mean_original_markers": sum(original_counts) / len(original_counts) if original_counts else 0.0,
        "mean_perturbed_markers": sum(perturbed_counts) / len(perturbed_counts) if perturbed_counts else 0.0,
        "total_dropped_markers": total_dropped,
        "total_added_markers": total_added,
    }


def _record_training_text(record: dict[str, Any]) -> str:
    messages = record.get("messages")
    if isinstance(messages, list):
        return json.dumps(
            [
                {
                    "role": message.get("role"),
                    "content": message.get("content"),
                }
                for message in messages
                if isinstance(message, dict)
            ],
            sort_keys=True,
            ensure_ascii=True,
        )
    if {"instruction", "input", "output"} <= set(record):
        return json.dumps(
            {
                "instruction": record["instruction"],
                "input": record["input"],
                "output": record["output"],
            },
            sort_keys=True,
            ensure_ascii=True,
        )
    return json.dumps(record, sort_keys=True, ensure_ascii=True)


def split_jsonl(
    input_path: str | Path,
    output_dir: str | Path,
    train_ratio: float = 0.8,
    validation_ratio: float = 0.1,
    seed: int = 13,
) -> dict[str, Path]:
    """Split a JSONL file into train, validation, and test JSONL files."""

    if train_ratio <= 0 or validation_ratio < 0 or train_ratio + validation_ratio >= 1:
        raise ValueError("ratios must leave a positive test split")

    records = read_jsonl(input_path)
    rng = random.Random(seed)
    rng.shuffle(records)

    train_end = int(len(records) * train_ratio)
    validation_end = train_end + int(len(records) * validation_ratio)
    splits = {
        "train": records[:train_end],
        "validation": records[train_end:validation_end],
        "test": records[validation_end:],
    }

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}
    for name, split_records in splits.items():
        path = output_dir / f"{name}.jsonl"
        _write_jsonl_records(split_records, path)
        paths[name] = path
    return paths


def _resolve_record_field(record: dict[str, Any], field: str) -> Any:
    if "." in field:
        value: Any = record
        for part in field.split("."):
            if not isinstance(value, dict) or part not in value:
                raise ValueError(f"group field not found: {field}")
            value = value[part]
        return value

    metadata = record.get("metadata")
    if isinstance(metadata, dict) and field in metadata:
        return metadata[field]
    if field in record:
        return record[field]
    raise ValueError(f"group field not found: {field}")


def _group_value(value: Any) -> str:
    if value is None:
        return "__none__"
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, sort_keys=True, ensure_ascii=True)
    return str(value)


def _record_group_key(record: dict[str, Any], group_by: Sequence[str]) -> tuple[str, ...]:
    return tuple(_group_value(_resolve_record_field(record, field)) for field in group_by)


def split_grouped_jsonl(
    input_path: str | Path,
    output_dir: str | Path,
    group_by: Sequence[str],
    train_ratio: float = 0.8,
    validation_ratio: float = 0.1,
    seed: int = 13,
) -> dict[str, Path]:
    """Split JSONL records while keeping all examples from each group together."""

    if not group_by:
        raise ValueError("group_by must contain at least one metadata field")
    if train_ratio <= 0 or validation_ratio < 0 or train_ratio + validation_ratio >= 1:
        raise ValueError("ratios must leave a positive test split")

    records = read_jsonl(input_path)
    if not records:
        raise ValueError("input JSONL contains no records")

    grouped: dict[tuple[str, ...], list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        grouped[_record_group_key(record, group_by)].append(record)

    targets = {
        "train": len(records) * train_ratio,
        "validation": len(records) * validation_ratio,
        "test": len(records) * (1.0 - train_ratio - validation_ratio),
    }
    active_splits = [name for name, target in targets.items() if target > 0]
    if len(grouped) < len(active_splits):
        raise ValueError(
            f"grouped split requires at least {len(active_splits)} groups; found {len(grouped)}"
        )

    rng = random.Random(seed)
    group_items = [
        {"key": key, "records": grouped[key], "tie_breaker": rng.random()}
        for key in grouped
    ]
    split_records: dict[str, list[dict[str, Any]]] = {
        "train": [],
        "validation": [],
        "test": [],
    }
    split_groups: dict[str, list[tuple[str, ...]]] = {
        "train": [],
        "validation": [],
        "test": [],
    }

    # Seed each active split with a small group so validation/test are not empty.
    seed_items = sorted(group_items, key=lambda item: (len(item["records"]), item["tie_breaker"]))
    seed_order = sorted(active_splits, key=lambda name: targets[name])
    assigned_keys: set[tuple[str, ...]] = set()
    for split_name in seed_order:
        item = seed_items.pop(0)
        key = item["key"]
        assigned_keys.add(key)
        split_records[split_name].extend(item["records"])
        split_groups[split_name].append(key)

    remaining_items = [
        item for item in group_items if item["key"] not in assigned_keys
    ]
    remaining_items.sort(key=lambda item: (-len(item["records"]), item["tie_breaker"]))
    for item in remaining_items:
        deficits = {
            name: targets[name] - len(split_records[name])
            for name in active_splits
        }
        split_name = max(deficits, key=deficits.get)
        key = item["key"]
        split_records[split_name].extend(item["records"])
        split_groups[split_name].append(key)

    for split_name in split_records:
        rng.shuffle(split_records[split_name])

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}
    for name, records_for_split in split_records.items():
        path = output_dir / f"{name}.jsonl"
        _write_jsonl_records(records_for_split, path)
        paths[name] = path

    manifest = {
        "input": str(input_path),
        "group_by": list(group_by),
        "seed": seed,
        "ratios": {
            "train": train_ratio,
            "validation": validation_ratio,
            "test": 1.0 - train_ratio - validation_ratio,
        },
        "records": len(records),
        "groups": len(grouped),
        "splits": {
            name: {
                "path": str(paths[name]),
                "records": len(split_records[name]),
                "groups": len(split_groups[name]),
            }
            for name in ("train", "validation", "test")
        },
        "group_assignments": [
            {
                "split": split_name,
                "group": dict(zip(group_by, key, strict=False)),
                "records": len(grouped[key]),
            }
            for split_name in ("train", "validation", "test")
            for key in split_groups[split_name]
        ],
    }
    manifest_path = output_dir / "split_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    paths["manifest"] = manifest_path
    return paths


def _allocate_stratum_record_groups(
    record_groups: list[list[dict[str, Any]]],
    train_ratio: float,
    validation_ratio: float,
    rng: random.Random,
) -> dict[str, list[dict[str, Any]]]:
    shuffled = list(record_groups)
    rng.shuffle(shuffled)
    test_ratio = 1.0 - train_ratio - validation_ratio
    ratios = {
        "train": train_ratio,
        "validation": validation_ratio,
        "test": test_ratio,
    }
    active_splits = [name for name, ratio in ratios.items() if ratio > 0]
    split_records: dict[str, list[dict[str, Any]]] = {
        "train": [],
        "validation": [],
        "test": [],
    }

    if len(shuffled) >= len(active_splits):
        for split_name in active_splits:
            split_records[split_name].extend(shuffled.pop())
    elif shuffled:
        split_records["train"].extend(shuffled.pop())

    total_records = sum(len(group) for group in record_groups)
    for record_group in shuffled:
        targets = {name: total_records * ratios[name] for name in active_splits}
        deficits = {
            name: targets[name] - len(split_records[name])
            for name in active_splits
        }
        split_name = max(deficits, key=deficits.get)
        split_records[split_name].extend(record_group)
    return split_records


def split_stratified_jsonl(
    input_path: str | Path,
    output_dir: str | Path,
    stratify_by: str = "cell_type",
    train_ratio: float = 0.8,
    validation_ratio: float = 0.1,
    seed: int = 13,
) -> dict[str, Path]:
    """Split JSONL records while preserving metadata label overlap across splits."""

    if train_ratio <= 0 or validation_ratio < 0 or train_ratio + validation_ratio >= 1:
        raise ValueError("ratios must leave a positive test split")

    records = read_jsonl(input_path)
    if not records:
        raise ValueError("input JSONL contains no records")

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        value = _resolve_record_field(record, stratify_by)
        grouped[_group_value(value)].append(record)

    rng = random.Random(seed)
    split_records: dict[str, list[dict[str, Any]]] = {
        "train": [],
        "validation": [],
        "test": [],
    }
    stratum_assignments: list[dict[str, Any]] = []
    for stratum, stratum_records in sorted(grouped.items()):
        duplicate_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for record in stratum_records:
            duplicate_groups[_record_training_text(record)].append(record)
        allocated = _allocate_stratum_record_groups(
            list(duplicate_groups.values()),
            train_ratio=train_ratio,
            validation_ratio=validation_ratio,
            rng=rng,
        )
        for split_name, records_for_split in allocated.items():
            split_records[split_name].extend(records_for_split)
            if records_for_split:
                stratum_assignments.append(
                    {
                        "split": split_name,
                        "stratum": stratum,
                        "records": len(records_for_split),
                    }
                )

    for records_for_split in split_records.values():
        rng.shuffle(records_for_split)

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}
    for name, records_for_split in split_records.items():
        path = output_dir / f"{name}.jsonl"
        _write_jsonl_records(records_for_split, path)
        paths[name] = path

    split_strata = {
        split_name: {
            assignment["stratum"]
            for assignment in stratum_assignments
            if assignment["split"] == split_name
        }
        for split_name in ("train", "validation", "test")
    }
    all_strata = set(grouped)
    manifest = {
        "input": str(input_path),
        "stratify_by": stratify_by,
        "seed": seed,
        "ratios": {
            "train": train_ratio,
            "validation": validation_ratio,
            "test": 1.0 - train_ratio - validation_ratio,
        },
        "records": len(records),
        "strata": len(grouped),
        "splits": {
            name: {
                "path": str(paths[name]),
                "records": len(split_records[name]),
                "strata": len(split_strata[name]),
                "missing_strata": len(all_strata - split_strata[name]),
            }
            for name in ("train", "validation", "test")
        },
        "stratum_assignments": stratum_assignments,
    }
    manifest_path = output_dir / "split_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    paths["manifest"] = manifest_path
    return paths
