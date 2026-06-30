"""Benchmark runners that produce evaluation-ready prediction JSONL."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .annotation import (
    CandidateRerankAnnotator,
    LoraAdapterAnnotator,
    MarkerOverlapAnnotator,
    PromptOnlyCausalLMAnnotator,
    ScTypeAnnotator,
)
from .dataset_builder import load_marker_records, read_jsonl


def extract_case(record: dict[str, Any]) -> dict[str, Any]:
    """Extract tissue, markers, and gold labels from a generated instruction record."""

    metadata = record.get("metadata") or {}
    required = {"tissue", "markers", "cell_type"}
    missing = required - set(metadata)
    if missing:
        raise ValueError(f"record metadata missing fields: {sorted(missing)}")
    return {
        "tissue": metadata["tissue"],
        "markers": metadata["markers"],
        "y_true": metadata["cell_type"],
        "true_cl_id": metadata.get("cell_ontology_id"),
    }


def run_annotation_benchmark(
    annotator: object,
    input_jsonl: str | Path,
    output_jsonl: str | Path,
) -> list[dict[str, Any]]:
    """Run an annotator over an instruction JSONL split."""

    records = read_jsonl(input_jsonl)
    predictions: list[dict[str, Any]] = []

    for record in records:
        case = extract_case(record)
        prediction = annotator.predict(case["tissue"], case["markers"])
        predictions.append(
            {
                "tissue": case["tissue"],
                "markers": case["markers"],
                "y_true": case["y_true"],
                "y_pred": prediction.cell_type,
                "true_cl_id": case["true_cl_id"],
                "pred_cl_id": prediction.cell_ontology_id,
                "confidence": prediction.confidence,
                "runtime_seconds": prediction.runtime_seconds,
                "cost_usd": prediction.cost_usd,
                "reasoning": prediction.reasoning,
                "raw_response": prediction.raw_response,
            }
        )

    output_jsonl = Path(output_jsonl)
    output_jsonl.parent.mkdir(parents=True, exist_ok=True)
    with output_jsonl.open("w", encoding="utf-8", newline="\n") as handle:
        for prediction in predictions:
            handle.write(json.dumps(prediction, ensure_ascii=True) + "\n")
    return predictions


def run_marker_overlap_benchmark(
    marker_db_path: str | Path,
    input_jsonl: str | Path,
    output_jsonl: str | Path,
) -> list[dict[str, Any]]:
    """Run the marker-overlap baseline over an instruction JSONL split."""

    annotator = MarkerOverlapAnnotator(load_marker_records(marker_db_path))
    return run_annotation_benchmark(annotator, input_jsonl, output_jsonl)


def run_sctype_benchmark(
    marker_db_path: str | Path,
    input_jsonl: str | Path,
    output_jsonl: str | Path,
    negative_weight: float = 1.0,
) -> list[dict[str, Any]]:
    """Run the scType-style marker-set baseline over an instruction JSONL split."""

    annotator = ScTypeAnnotator(
        load_marker_records(marker_db_path),
        negative_weight=negative_weight,
    )
    return run_annotation_benchmark(annotator, input_jsonl, output_jsonl)


def run_prompt_benchmark(
    base_model_path: str,
    input_jsonl: str | Path,
    output_jsonl: str | Path,
    max_new_tokens: int = 128,
    temperature: float = 0.0,
) -> list[dict[str, Any]]:
    """Run a prompt-only causal LLM over an instruction JSONL split."""

    annotator = PromptOnlyCausalLMAnnotator(
        model_name_or_path=base_model_path,
        max_new_tokens=max_new_tokens,
        temperature=temperature,
    )
    return run_annotation_benchmark(annotator, input_jsonl, output_jsonl)


def run_lora_benchmark(
    base_model_path: str,
    adapter_path: str,
    input_jsonl: str | Path,
    output_jsonl: str | Path,
    max_new_tokens: int = 128,
    temperature: float = 0.0,
) -> list[dict[str, Any]]:
    """Run a trained LoRA adapter over an instruction JSONL split."""

    annotator = LoraAdapterAnnotator(
        base_model_name_or_path=base_model_path,
        adapter_name_or_path=adapter_path,
        max_new_tokens=max_new_tokens,
        temperature=temperature,
    )
    return run_annotation_benchmark(annotator, input_jsonl, output_jsonl)


def run_lora_candidate_rerank_benchmark(
    marker_db_path: str | Path,
    base_model_path: str,
    adapter_path: str,
    input_jsonl: str | Path,
    output_jsonl: str | Path,
    top_k: int = 5,
    max_new_tokens: int = 128,
    temperature: float = 0.0,
) -> list[dict[str, Any]]:
    """Run LoRA candidate reranking over an instruction JSONL split."""

    annotator = CandidateRerankAnnotator(
        marker_records=load_marker_records(marker_db_path),
        base_model_name_or_path=base_model_path,
        adapter_name_or_path=adapter_path,
        top_k=top_k,
        max_new_tokens=max_new_tokens,
        temperature=temperature,
    )
    records = read_jsonl(input_jsonl)
    predictions: list[dict[str, Any]] = []

    for record in records:
        case = extract_case(record)
        prediction = annotator.predict(case["tissue"], case["markers"])
        predictions.append(
            {
                "tissue": case["tissue"],
                "markers": case["markers"],
                "y_true": case["y_true"],
                "y_pred": prediction.cell_type,
                "true_cl_id": case["true_cl_id"],
                "pred_cl_id": prediction.cell_ontology_id,
                "confidence": prediction.confidence,
                "runtime_seconds": prediction.runtime_seconds,
                "cost_usd": prediction.cost_usd,
                "reasoning": prediction.reasoning,
                "raw_response": prediction.raw_response,
                "selection_source": annotator.last_selection_source,
                "candidates": annotator.last_candidates,
            }
        )

    output_jsonl = Path(output_jsonl)
    output_jsonl.parent.mkdir(parents=True, exist_ok=True)
    with output_jsonl.open("w", encoding="utf-8", newline="\n") as handle:
        for prediction in predictions:
            handle.write(json.dumps(prediction, ensure_ascii=True) + "\n")
    return predictions
