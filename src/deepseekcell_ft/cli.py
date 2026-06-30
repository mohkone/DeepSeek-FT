"""Command line interface for DeepSeekCell-FT."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .annotation import MarkerOverlapAnnotator
from .benchmark import (
    run_lora_benchmark,
    run_lora_candidate_rerank_benchmark,
    run_marker_overlap_benchmark,
    run_prompt_benchmark,
    run_sctype_benchmark,
)
from .dataset_builder import (
    generate_examples,
    load_marker_records,
    perturb_instruction_markers,
    split_grouped_jsonl,
    split_jsonl,
    split_stratified_jsonl,
    write_jsonl,
)
from .downloads import download_cell_ontology_obo, download_panglaodb_markers
from .evaluation import (
    analyze_prediction_records,
    analyze_rerank_prediction_records,
    evaluate_predictions,
    load_prediction_records,
    map_prediction_ontology_ids,
    reparse_prediction_records,
    sync_prediction_gold_ontology_ids,
)
from .finetune import LoraTrainingConfig, train_lora
from .marker_extraction import extract_ranked_markers, prepare_matrix_marker_benchmark
from .ontology import (
    accept_ontology_suggestion,
    accept_ontology_decisions,
    auto_accept_ontology_curation,
    apply_ontology_curation,
    enrich_marker_db_with_cl_ids,
    write_cell_ontology_label_map,
    write_ontology_curation_priority_report,
    write_ontology_curation_template,
)
from .reporting import write_experiment_summary
from .source_ingestion import (
    MarkerTableConfig,
    merge_marker_record_sets,
    normalize_marker_table,
    summarize_marker_records,
)
from .training_prep import inspect_finetune_splits


def build_dataset_command(args: argparse.Namespace) -> int:
    records = load_marker_records(args.input)
    examples = generate_examples(
        records,
        examples_per_record=args.examples_per_record,
        min_markers=args.min_markers,
        max_markers=args.max_markers,
        noise_rate=args.noise_rate,
        seed=args.seed,
    )
    write_jsonl(examples, args.output, output_format=args.format)
    print(f"Wrote {len(examples)} examples to {args.output}")
    return 0


def normalize_markers_command(args: argparse.Namespace) -> int:
    config = MarkerTableConfig(
        tissue_column=args.tissue_column,
        cell_type_column=args.cell_type_column,
        marker_column=args.marker_column,
        markers_column=args.markers_column,
        cl_id_column=args.cl_id_column,
        source_column=args.source_column,
        evidence_column=args.evidence_column,
        species_column=args.species_column,
        source_name=args.source,
        species=args.species,
        delimiter=args.delimiter,
        min_markers=args.min_markers,
    )
    records = normalize_marker_table(args.input, args.output, config)
    summary = summarize_marker_records(records)
    print(f"Wrote {len(records)} normalized marker records to {args.output}")
    print(json.dumps(summary, indent=2, sort_keys=True, ensure_ascii=True))
    return 0


def merge_marker_dbs_command(args: argparse.Namespace) -> int:
    records = merge_marker_record_sets(args.inputs, args.output, min_markers=args.min_markers)
    summary = summarize_marker_records(records)
    print(f"Wrote {len(records)} merged marker records to {args.output}")
    print(json.dumps(summary, indent=2, sort_keys=True, ensure_ascii=True))
    return 0


def validate_marker_db_command(args: argparse.Namespace) -> int:
    records = load_marker_records(args.input)
    summary = summarize_marker_records(records)
    print(json.dumps(summary, indent=2, sort_keys=True, ensure_ascii=True))
    return 0


def download_panglaodb_command(args: argparse.Namespace) -> int:
    output_path = download_panglaodb_markers(args.output)
    print(f"Downloaded PanglaoDB markers to {output_path}")
    return 0


def download_cell_ontology_command(args: argparse.Namespace) -> int:
    output_path = download_cell_ontology_obo(args.output)
    print(f"Downloaded Cell Ontology OBO to {output_path}")
    return 0


def build_ontology_map_command(args: argparse.Namespace) -> int:
    scopes = {scope.strip().upper() for scope in args.synonym_scopes.split(",") if scope.strip()}
    summary = write_cell_ontology_label_map(
        args.input,
        args.output,
        ambiguous_output_path=args.ambiguous_output,
        synonym_scopes=scopes,
        include_obsolete=args.include_obsolete,
    )
    print(json.dumps(summary, indent=2, sort_keys=True, ensure_ascii=True))
    return 0


def map_marker_db_ontology_command(args: argparse.Namespace) -> int:
    summary = enrich_marker_db_with_cl_ids(
        marker_db_path=args.marker_db,
        ontology_map_path=args.ontology_map,
        output_path=args.output,
        unmapped_output_path=args.unmapped_output,
        overwrite=args.overwrite,
        use_variants=not args.no_label_variants,
    )
    print(json.dumps(summary, indent=2, sort_keys=True, ensure_ascii=True))
    return 0


def propose_ontology_curation_command(args: argparse.Namespace) -> int:
    summary = write_ontology_curation_template(
        unmapped_path=args.unmapped,
        ontology_map_path=args.ontology_map,
        output_path=args.output,
        max_suggestions=args.max_suggestions,
    )
    print(json.dumps(summary, indent=2, sort_keys=True, ensure_ascii=True))
    return 0


def apply_ontology_curation_command(args: argparse.Namespace) -> int:
    summary = apply_ontology_curation(
        marker_db_path=args.marker_db,
        curation_path=args.curation,
        output_path=args.output,
        unmapped_output_path=args.unmapped_output,
        overwrite=args.overwrite,
    )
    print(json.dumps(summary, indent=2, sort_keys=True, ensure_ascii=True))
    return 0


def auto_accept_ontology_curation_command(args: argparse.Namespace) -> int:
    summary = auto_accept_ontology_curation(
        curation_path=args.curation,
        output_path=args.output,
        min_score=args.min_score,
    )
    print(json.dumps(summary, indent=2, sort_keys=True, ensure_ascii=True))
    return 0


def accept_ontology_suggestion_command(args: argparse.Namespace) -> int:
    summary = accept_ontology_suggestion(
        curation_path=args.curation,
        output_path=args.output,
        cell_type=args.cell_type,
        rank=args.rank,
        cl_id=args.cl_id,
        accepted_label=args.accepted_label,
        notes=args.notes,
    )
    print(json.dumps(summary, indent=2, sort_keys=True, ensure_ascii=True))
    return 0


def accept_ontology_decisions_command(args: argparse.Namespace) -> int:
    summary = accept_ontology_decisions(
        curation_path=args.curation,
        decisions_path=args.decisions,
        output_path=args.output,
        skip_missing=args.skip_missing,
    )
    print(json.dumps(summary, indent=2, sort_keys=True, ensure_ascii=True))
    return 0


def prioritize_ontology_curation_command(args: argparse.Namespace) -> int:
    summary = write_ontology_curation_priority_report(
        curation_path=args.curation,
        split_dir=args.split_dir,
        output_path=args.output,
        include_accepted=args.include_accepted,
    )
    print(json.dumps(summary, indent=2, sort_keys=True, ensure_ascii=True))
    return 0


def split_command(args: argparse.Namespace) -> int:
    paths = split_jsonl(
        args.input,
        args.output_dir,
        train_ratio=args.train_ratio,
        validation_ratio=args.validation_ratio,
        seed=args.seed,
    )
    for name, path in paths.items():
        print(f"{name}: {path}")
    return 0


def split_grouped_command(args: argparse.Namespace) -> int:
    group_by = [field.strip() for field in args.group_by.split(",") if field.strip()]
    paths = split_grouped_jsonl(
        args.input,
        args.output_dir,
        group_by=group_by,
        train_ratio=args.train_ratio,
        validation_ratio=args.validation_ratio,
        seed=args.seed,
    )
    for name, path in paths.items():
        print(f"{name}: {path}")
    return 0


def split_stratified_command(args: argparse.Namespace) -> int:
    paths = split_stratified_jsonl(
        args.input,
        args.output_dir,
        stratify_by=args.stratify_by,
        train_ratio=args.train_ratio,
        validation_ratio=args.validation_ratio,
        seed=args.seed,
    )
    for name, path in paths.items():
        print(f"{name}: {path}")
    return 0


def perturb_markers_command(args: argparse.Namespace) -> int:
    summary = perturb_instruction_markers(
        input_path=args.input,
        output_path=args.output,
        marker_db_path=args.marker_db,
        drop_rate=args.drop_rate,
        add_noise_markers=args.add_noise_markers,
        min_markers=args.min_markers,
        seed=args.seed,
    )
    print(json.dumps(summary, indent=2, sort_keys=True, ensure_ascii=True))
    return 0


def annotate_command(args: argparse.Namespace) -> int:
    records = load_marker_records(args.marker_db)
    annotator = MarkerOverlapAnnotator(records)
    prediction = annotator.predict(args.tissue, args.markers)
    print(json.dumps(prediction.to_json_dict(), indent=2, ensure_ascii=True))
    return 0


def evaluate_command(args: argparse.Namespace) -> int:
    records = load_prediction_records(args.predictions)
    metrics = evaluate_predictions(records, confidence_bins=args.confidence_bins)
    print(json.dumps(metrics, indent=2, sort_keys=True, ensure_ascii=True))
    return 0


def analyze_predictions_command(args: argparse.Namespace) -> int:
    records = load_prediction_records(args.predictions)
    analysis = analyze_prediction_records(
        records,
        examples_output=args.examples_output,
        max_examples=args.max_examples,
    )
    print(json.dumps(analysis, indent=2, sort_keys=True, ensure_ascii=True))
    return 0


def analyze_rerank_predictions_command(args: argparse.Namespace) -> int:
    records = load_prediction_records(args.predictions)
    analysis = analyze_rerank_prediction_records(
        records,
        examples_output=args.examples_output,
        max_examples=args.max_examples,
    )
    print(json.dumps(analysis, indent=2, sort_keys=True, ensure_ascii=True))
    return 0


def map_prediction_ontology_command(args: argparse.Namespace) -> int:
    summary = map_prediction_ontology_ids(
        predictions_path=args.predictions,
        marker_db_path=args.marker_db,
        output_path=args.output,
        preserve_existing=args.preserve_existing,
    )
    print(json.dumps(summary, indent=2, sort_keys=True, ensure_ascii=True))
    return 0


def reparse_predictions_command(args: argparse.Namespace) -> int:
    summary = reparse_prediction_records(
        predictions_path=args.predictions,
        output_path=args.output,
    )
    print(json.dumps(summary, indent=2, sort_keys=True, ensure_ascii=True))
    return 0


def sync_prediction_gold_ontology_command(args: argparse.Namespace) -> int:
    summary = sync_prediction_gold_ontology_ids(
        predictions_path=args.predictions,
        input_jsonl_path=args.input,
        output_path=args.output,
        allow_mismatches=args.allow_mismatches,
    )
    print(json.dumps(summary, indent=2, sort_keys=True, ensure_ascii=True))
    return 0


def benchmark_marker_overlap_command(args: argparse.Namespace) -> int:
    predictions = run_marker_overlap_benchmark(args.marker_db, args.input, args.output)
    metrics = evaluate_predictions(predictions, confidence_bins=args.confidence_bins)
    print(f"Wrote {len(predictions)} predictions to {args.output}")
    print(json.dumps(metrics, indent=2, sort_keys=True, ensure_ascii=True))
    return 0


def benchmark_sctype_command(args: argparse.Namespace) -> int:
    predictions = run_sctype_benchmark(
        args.marker_db,
        args.input,
        args.output,
        negative_weight=args.negative_weight,
    )
    metrics = evaluate_predictions(predictions, confidence_bins=args.confidence_bins)
    print(f"Wrote {len(predictions)} predictions to {args.output}")
    print(json.dumps(metrics, indent=2, sort_keys=True, ensure_ascii=True))
    return 0


def benchmark_prompt_command(args: argparse.Namespace) -> int:
    predictions = run_prompt_benchmark(
        base_model_path=args.base_model,
        input_jsonl=args.input,
        output_jsonl=args.output,
        max_new_tokens=args.max_new_tokens,
        temperature=args.temperature,
    )
    metrics = evaluate_predictions(predictions, confidence_bins=args.confidence_bins)
    print(f"Wrote {len(predictions)} predictions to {args.output}")
    print(json.dumps(metrics, indent=2, sort_keys=True, ensure_ascii=True))
    return 0


def benchmark_lora_command(args: argparse.Namespace) -> int:
    predictions = run_lora_benchmark(
        base_model_path=args.base_model,
        adapter_path=args.adapter,
        input_jsonl=args.input,
        output_jsonl=args.output,
        max_new_tokens=args.max_new_tokens,
        temperature=args.temperature,
    )
    metrics = evaluate_predictions(predictions, confidence_bins=args.confidence_bins)
    print(f"Wrote {len(predictions)} predictions to {args.output}")
    print(json.dumps(metrics, indent=2, sort_keys=True, ensure_ascii=True))
    return 0


def benchmark_lora_rerank_command(args: argparse.Namespace) -> int:
    predictions = run_lora_candidate_rerank_benchmark(
        marker_db_path=args.marker_db,
        base_model_path=args.base_model,
        adapter_path=args.adapter,
        input_jsonl=args.input,
        output_jsonl=args.output,
        top_k=args.top_k,
        max_new_tokens=args.max_new_tokens,
        temperature=args.temperature,
    )
    metrics = evaluate_predictions(predictions, confidence_bins=args.confidence_bins)
    print(f"Wrote {len(predictions)} predictions to {args.output}")
    print(json.dumps(metrics, indent=2, sort_keys=True, ensure_ascii=True))
    return 0


def train_lora_command(args: argparse.Namespace) -> int:
    config = LoraTrainingConfig(
        base_model=args.base_model,
        train_jsonl=args.train_jsonl,
        validation_jsonl=args.validation_jsonl,
        output_dir=args.output_dir,
        max_seq_length=args.max_seq_length,
        per_device_train_batch_size=args.per_device_train_batch_size,
        gradient_accumulation_steps=args.gradient_accumulation_steps,
        learning_rate=args.learning_rate,
        num_train_epochs=args.num_train_epochs,
        lora_r=args.lora_r,
        lora_alpha=args.lora_alpha,
        lora_dropout=args.lora_dropout,
    )
    train_lora(config)
    print(f"Saved LoRA model to {args.output_dir}")
    return 0


def preflight_finetune_command(args: argparse.Namespace) -> int:
    group_by = (
        []
        if args.disable_group_check
        else [field.strip() for field in args.group_by.split(",") if field.strip()]
    )
    summary = inspect_finetune_splits(
        split_dir=args.split_dir,
        output_path=args.output,
        base_model=args.base_model,
        model_output_dir=args.model_output_dir,
        max_seq_length=args.max_seq_length,
        group_by=group_by,
    )
    print(json.dumps(summary, indent=2, sort_keys=True, ensure_ascii=True))
    return 0


def summarize_experiments_command(args: argparse.Namespace) -> int:
    summary = write_experiment_summary(
        prediction_specs=args.prediction,
        preflight_specs=args.preflight,
        output_json=args.output_json,
        output_markdown=args.output_markdown,
    )
    print(json.dumps(summary, indent=2, sort_keys=True, ensure_ascii=True))
    return 0


def extract_markers_command(args: argparse.Namespace) -> int:
    extract_ranked_markers(
        adata_path=args.adata,
        groupby=args.groupby,
        output_csv=args.output,
        n_top=args.n_top,
        method=args.method,
    )
    print(f"Wrote ranked markers to {args.output}")
    return 0


def prepare_matrix_benchmark_command(args: argparse.Namespace) -> int:
    summary = prepare_matrix_marker_benchmark(
        adata_path=args.adata,
        output_csv=args.output_marker_db,
        tissue=args.tissue,
        groupby=args.groupby,
        label_key=args.label_key,
        ontology_key=args.ontology_key,
        n_top=args.n_top,
        method=args.method,
        run_clustering=args.run_clustering,
        resolution=args.resolution,
        normalize=not args.no_normalize,
        min_cells=args.min_cells,
        min_genes=args.min_genes,
        random_state=args.seed,
    )
    print(json.dumps(summary, indent=2, sort_keys=True, ensure_ascii=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="DeepSeekCell-FT research CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    build = subparsers.add_parser("build-dataset", help="Build instruction JSONL from marker CSV")
    build.add_argument("--input", required=True, type=Path)
    build.add_argument("--output", required=True, type=Path)
    build.add_argument("--format", choices=["chat", "instruction"], default="chat")
    build.add_argument("--examples-per-record", type=int, default=16)
    build.add_argument("--min-markers", type=int, default=3)
    build.add_argument("--max-markers", type=int, default=8)
    build.add_argument("--noise-rate", type=float, default=0.15)
    build.add_argument("--seed", type=int, default=13)
    build.set_defaults(func=build_dataset_command)

    normalize = subparsers.add_parser(
        "normalize-markers",
        help="Normalize an external marker table into the standard marker evidence CSV",
    )
    normalize.add_argument("--input", required=True, type=Path)
    normalize.add_argument("--output", required=True, type=Path)
    normalize.add_argument("--source", help="Source name to use when no source column is present")
    normalize.add_argument("--species", help="Optional species filter, for example Human")
    normalize.add_argument("--delimiter", default="auto", help="Delimiter, 'tab', or 'auto'")
    normalize.add_argument("--tissue-column")
    normalize.add_argument("--cell-type-column")
    normalize.add_argument("--marker-column")
    normalize.add_argument("--markers-column")
    normalize.add_argument("--cl-id-column")
    normalize.add_argument("--source-column")
    normalize.add_argument("--evidence-column")
    normalize.add_argument("--species-column")
    normalize.add_argument("--min-markers", type=int, default=1)
    normalize.set_defaults(func=normalize_markers_command)

    merge = subparsers.add_parser("merge-marker-dbs", help="Merge normalized marker CSV files")
    merge.add_argument("--inputs", required=True, nargs="+", type=Path)
    merge.add_argument("--output", required=True, type=Path)
    merge.add_argument("--min-markers", type=int, default=1)
    merge.set_defaults(func=merge_marker_dbs_command)

    validate = subparsers.add_parser("validate-marker-db", help="Summarize a marker evidence CSV")
    validate.add_argument("--input", required=True, type=Path)
    validate.set_defaults(func=validate_marker_db_command)

    download_panglaodb = subparsers.add_parser(
        "download-panglaodb-markers",
        help="Download the public PanglaoDB marker table",
    )
    download_panglaodb.add_argument(
        "--output",
        type=Path,
        default=Path("data/raw/panglaodb_markers.tsv"),
    )
    download_panglaodb.set_defaults(func=download_panglaodb_command)

    download_cl = subparsers.add_parser(
        "download-cell-ontology",
        help="Download the Cell Ontology OBO release",
    )
    download_cl.add_argument(
        "--output",
        type=Path,
        default=Path("data/raw/cl.obo"),
    )
    download_cl.set_defaults(func=download_cell_ontology_command)

    ontology_map = subparsers.add_parser(
        "build-ontology-map",
        help="Build a Cell Ontology label-to-CL-ID CSV from cl.obo",
    )
    ontology_map.add_argument("--input", required=True, type=Path)
    ontology_map.add_argument("--output", required=True, type=Path)
    ontology_map.add_argument("--ambiguous-output", type=Path)
    ontology_map.add_argument("--synonym-scopes", default="EXACT")
    ontology_map.add_argument("--include-obsolete", action="store_true")
    ontology_map.set_defaults(func=build_ontology_map_command)

    map_ontology = subparsers.add_parser(
        "map-marker-db-ontology",
        help="Fill missing CL IDs in a marker evidence CSV from an ontology label map",
    )
    map_ontology.add_argument("--marker-db", required=True, type=Path)
    map_ontology.add_argument("--ontology-map", required=True, type=Path)
    map_ontology.add_argument("--output", required=True, type=Path)
    map_ontology.add_argument("--unmapped-output", type=Path)
    map_ontology.add_argument("--overwrite", action="store_true")
    map_ontology.add_argument("--no-label-variants", action="store_true")
    map_ontology.set_defaults(func=map_marker_db_ontology_command)

    propose_curation = subparsers.add_parser(
        "propose-ontology-curation",
        help="Create a manual curation CSV for unmapped marker labels",
    )
    propose_curation.add_argument("--unmapped", required=True, type=Path)
    propose_curation.add_argument("--ontology-map", required=True, type=Path)
    propose_curation.add_argument("--output", required=True, type=Path)
    propose_curation.add_argument("--max-suggestions", type=int, default=5)
    propose_curation.set_defaults(func=propose_ontology_curation_command)

    auto_accept_curation = subparsers.add_parser(
        "auto-accept-ontology-curation",
        help="Auto-fill curation rows only for strict label variants",
    )
    auto_accept_curation.add_argument("--curation", required=True, type=Path)
    auto_accept_curation.add_argument("--output", required=True, type=Path)
    auto_accept_curation.add_argument("--min-score", type=float, default=0.8)
    auto_accept_curation.set_defaults(func=auto_accept_ontology_curation_command)

    accept_suggestion = subparsers.add_parser(
        "accept-ontology-suggestion",
        help="Accept one ontology curation suggestion from the command line",
    )
    accept_suggestion.add_argument("--curation", required=True, type=Path)
    accept_suggestion.add_argument("--output", required=True, type=Path)
    accept_suggestion.add_argument("--cell-type", required=True)
    accept_suggestion.add_argument("--rank", type=int)
    accept_suggestion.add_argument("--cl-id")
    accept_suggestion.add_argument("--accepted-label")
    accept_suggestion.add_argument("--notes")
    accept_suggestion.set_defaults(func=accept_ontology_suggestion_command)

    accept_decisions = subparsers.add_parser(
        "accept-ontology-decisions",
        help="Apply a compact CSV of reviewed ontology decisions",
    )
    accept_decisions.add_argument("--curation", required=True, type=Path)
    accept_decisions.add_argument("--decisions", required=True, type=Path)
    accept_decisions.add_argument("--output", required=True, type=Path)
    accept_decisions.add_argument(
        "--skip-missing",
        action="store_true",
        help="Skip decisions whose cell_type is absent from the current curation template",
    )
    accept_decisions.set_defaults(func=accept_ontology_decisions_command)

    prioritize_curation = subparsers.add_parser(
        "prioritize-ontology-curation",
        help="Rank unmapped curation labels by train/validation/test split presence",
    )
    prioritize_curation.add_argument("--curation", required=True, type=Path)
    prioritize_curation.add_argument("--split-dir", required=True, type=Path)
    prioritize_curation.add_argument("--output", required=True, type=Path)
    prioritize_curation.add_argument("--include-accepted", action="store_true")
    prioritize_curation.set_defaults(func=prioritize_ontology_curation_command)

    apply_curation = subparsers.add_parser(
        "apply-ontology-curation",
        help="Apply accepted CL IDs from a curation CSV to a marker DB",
    )
    apply_curation.add_argument("--marker-db", required=True, type=Path)
    apply_curation.add_argument("--curation", required=True, type=Path)
    apply_curation.add_argument("--output", required=True, type=Path)
    apply_curation.add_argument("--unmapped-output", type=Path)
    apply_curation.add_argument("--overwrite", action="store_true")
    apply_curation.set_defaults(func=apply_ontology_curation_command)

    split = subparsers.add_parser("split", help="Split JSONL into train/validation/test")
    split.add_argument("--input", required=True, type=Path)
    split.add_argument("--output-dir", required=True, type=Path)
    split.add_argument("--train-ratio", type=float, default=0.8)
    split.add_argument("--validation-ratio", type=float, default=0.1)
    split.add_argument("--seed", type=int, default=13)
    split.set_defaults(func=split_command)

    split_grouped = subparsers.add_parser(
        "split-grouped",
        help="Split JSONL while keeping metadata groups in only one split",
    )
    split_grouped.add_argument("--input", required=True, type=Path)
    split_grouped.add_argument("--output-dir", required=True, type=Path)
    split_grouped.add_argument(
        "--group-by",
        default="tissue,cell_type,source",
        help="Comma-separated metadata fields, for example tissue,cell_type,source",
    )
    split_grouped.add_argument("--train-ratio", type=float, default=0.8)
    split_grouped.add_argument("--validation-ratio", type=float, default=0.1)
    split_grouped.add_argument("--seed", type=int, default=13)
    split_grouped.set_defaults(func=split_grouped_command)

    split_stratified = subparsers.add_parser(
        "split-stratified",
        help="Split JSONL while preserving metadata label overlap across splits",
    )
    split_stratified.add_argument("--input", required=True, type=Path)
    split_stratified.add_argument("--output-dir", required=True, type=Path)
    split_stratified.add_argument(
        "--stratify-by",
        default="cell_type",
        help="Metadata field used as the stratum, for example cell_type",
    )
    split_stratified.add_argument("--train-ratio", type=float, default=0.8)
    split_stratified.add_argument("--validation-ratio", type=float, default=0.1)
    split_stratified.add_argument("--seed", type=int, default=13)
    split_stratified.set_defaults(func=split_stratified_command)

    perturb = subparsers.add_parser(
        "perturb-markers",
        help="Create a noisy marker split by dropping true markers and adding distractors",
    )
    perturb.add_argument("--input", required=True, type=Path)
    perturb.add_argument("--output", required=True, type=Path)
    perturb.add_argument("--marker-db", required=True, type=Path)
    perturb.add_argument("--drop-rate", type=float, default=0.5)
    perturb.add_argument("--add-noise-markers", type=int, default=3)
    perturb.add_argument("--min-markers", type=int, default=1)
    perturb.add_argument("--seed", type=int, default=13)
    perturb.set_defaults(func=perturb_markers_command)

    annotate = subparsers.add_parser("annotate", help="Annotate markers with marker-overlap baseline")
    annotate.add_argument("--marker-db", required=True, type=Path)
    annotate.add_argument("--tissue", required=True)
    annotate.add_argument("--markers", required=True)
    annotate.set_defaults(func=annotate_command)

    evaluate = subparsers.add_parser("evaluate", help="Evaluate prediction JSONL")
    evaluate.add_argument("--predictions", required=True, type=Path)
    evaluate.add_argument("--confidence-bins", type=int, default=10)
    evaluate.set_defaults(func=evaluate_command)

    analyze = subparsers.add_parser(
        "analyze-predictions",
        help="Summarize prediction errors and write example mismatches",
    )
    analyze.add_argument("--predictions", required=True, type=Path)
    analyze.add_argument("--examples-output", type=Path)
    analyze.add_argument("--max-examples", type=int, default=25)
    analyze.set_defaults(func=analyze_predictions_command)

    analyze_rerank = subparsers.add_parser(
        "analyze-rerank-predictions",
        help="Audit candidate-reranking behavior and top-k candidate quality",
    )
    analyze_rerank.add_argument("--predictions", required=True, type=Path)
    analyze_rerank.add_argument("--examples-output", type=Path)
    analyze_rerank.add_argument("--max-examples", type=int, default=25)
    analyze_rerank.set_defaults(func=analyze_rerank_predictions_command)

    map_prediction_ontology = subparsers.add_parser(
        "map-prediction-ontology",
        help="Fill prediction CL IDs from a curated marker label map",
    )
    map_prediction_ontology.add_argument("--predictions", required=True, type=Path)
    map_prediction_ontology.add_argument("--marker-db", required=True, type=Path)
    map_prediction_ontology.add_argument("--output", required=True, type=Path)
    map_prediction_ontology.add_argument(
        "--preserve-existing",
        action="store_true",
        help="Keep existing predicted CL IDs instead of replacing them from labels",
    )
    map_prediction_ontology.set_defaults(func=map_prediction_ontology_command)

    reparse_predictions = subparsers.add_parser(
        "reparse-predictions",
        help="Re-extract prediction fields from saved raw LLM responses",
    )
    reparse_predictions.add_argument("--predictions", required=True, type=Path)
    reparse_predictions.add_argument("--output", required=True, type=Path)
    reparse_predictions.set_defaults(func=reparse_predictions_command)

    sync_gold = subparsers.add_parser(
        "sync-prediction-gold-ontology",
        help="Refresh prediction gold CL IDs from an aligned instruction JSONL",
    )
    sync_gold.add_argument("--predictions", required=True, type=Path)
    sync_gold.add_argument("--input", required=True, type=Path)
    sync_gold.add_argument("--output", required=True, type=Path)
    sync_gold.add_argument(
        "--allow-mismatches",
        action="store_true",
        help="Write output even if row labels, tissues, or markers do not align",
    )
    sync_gold.set_defaults(func=sync_prediction_gold_ontology_command)

    benchmark = subparsers.add_parser(
        "benchmark-marker-overlap",
        help="Run marker-overlap baseline on an instruction split",
    )
    benchmark.add_argument("--marker-db", required=True, type=Path)
    benchmark.add_argument("--input", required=True, type=Path)
    benchmark.add_argument("--output", required=True, type=Path)
    benchmark.add_argument("--confidence-bins", type=int, default=10)
    benchmark.set_defaults(func=benchmark_marker_overlap_command)

    sctype_benchmark = subparsers.add_parser(
        "benchmark-sctype",
        help="Run scType-style positive/negative marker-set scoring on an instruction split",
    )
    sctype_benchmark.add_argument("--marker-db", required=True, type=Path)
    sctype_benchmark.add_argument("--input", required=True, type=Path)
    sctype_benchmark.add_argument("--output", required=True, type=Path)
    sctype_benchmark.add_argument(
        "--negative-weight",
        type=float,
        default=1.0,
        help="Penalty weight for query markers present in a candidate's negative marker set",
    )
    sctype_benchmark.add_argument("--confidence-bins", type=int, default=10)
    sctype_benchmark.set_defaults(func=benchmark_sctype_command)

    prompt_benchmark = subparsers.add_parser(
        "benchmark-prompt",
        help="Run a prompt-only causal LLM on an instruction split",
    )
    prompt_benchmark.add_argument("--base-model", required=True)
    prompt_benchmark.add_argument("--input", required=True, type=Path)
    prompt_benchmark.add_argument("--output", required=True, type=Path)
    prompt_benchmark.add_argument("--max-new-tokens", type=int, default=128)
    prompt_benchmark.add_argument("--temperature", type=float, default=0.0)
    prompt_benchmark.add_argument("--confidence-bins", type=int, default=10)
    prompt_benchmark.set_defaults(func=benchmark_prompt_command)

    lora_benchmark = subparsers.add_parser(
        "benchmark-lora",
        help="Run a trained LoRA adapter on an instruction split",
    )
    lora_benchmark.add_argument("--base-model", required=True)
    lora_benchmark.add_argument("--adapter", required=True)
    lora_benchmark.add_argument("--input", required=True, type=Path)
    lora_benchmark.add_argument("--output", required=True, type=Path)
    lora_benchmark.add_argument("--max-new-tokens", type=int, default=128)
    lora_benchmark.add_argument("--temperature", type=float, default=0.0)
    lora_benchmark.add_argument("--confidence-bins", type=int, default=10)
    lora_benchmark.set_defaults(func=benchmark_lora_command)

    lora_rerank_benchmark = subparsers.add_parser(
        "benchmark-lora-rerank",
        help="Run LoRA as a constrained reranker over marker-overlap candidates",
    )
    lora_rerank_benchmark.add_argument("--marker-db", required=True, type=Path)
    lora_rerank_benchmark.add_argument("--base-model", required=True)
    lora_rerank_benchmark.add_argument("--adapter", required=True)
    lora_rerank_benchmark.add_argument("--input", required=True, type=Path)
    lora_rerank_benchmark.add_argument("--output", required=True, type=Path)
    lora_rerank_benchmark.add_argument("--top-k", type=int, default=5)
    lora_rerank_benchmark.add_argument("--max-new-tokens", type=int, default=128)
    lora_rerank_benchmark.add_argument("--temperature", type=float, default=0.0)
    lora_rerank_benchmark.add_argument("--confidence-bins", type=int, default=10)
    lora_rerank_benchmark.set_defaults(func=benchmark_lora_rerank_command)

    preflight = subparsers.add_parser(
        "preflight-finetune",
        help="Inspect train/validation/test splits before LoRA fine-tuning",
    )
    preflight.add_argument("--split-dir", required=True, type=Path)
    preflight.add_argument("--output", type=Path)
    preflight.add_argument(
        "--base-model",
        default="deepseek-ai/deepseek-llm-7b-chat",
        help="Base model name to include in the suggested train command",
    )
    preflight.add_argument(
        "--model-output-dir",
        default="models/deepseekcell-ft-lora",
        help="LoRA output directory to include in the suggested train command",
    )
    preflight.add_argument("--max-seq-length", type=int, default=2048)
    preflight.add_argument(
        "--group-by",
        default="tissue,cell_type,source",
        help="Comma-separated metadata fields used to check split leakage",
    )
    preflight.add_argument(
        "--disable-group-check",
        action="store_true",
        help="Disable metadata-group leakage checks while still checking duplicate records",
    )
    preflight.set_defaults(func=preflight_finetune_command)

    summarize = subparsers.add_parser(
        "summarize-experiments",
        help="Create manuscript-ready JSON and Markdown summaries from benchmark outputs",
    )
    summarize.add_argument(
        "--prediction",
        action="append",
        required=True,
        help="Prediction spec as name=path or bare path; may be repeated",
    )
    summarize.add_argument(
        "--preflight",
        action="append",
        default=[],
        help="Preflight spec as name=path or bare path; may be repeated",
    )
    summarize.add_argument("--output-json", required=True, type=Path)
    summarize.add_argument("--output-markdown", type=Path)
    summarize.set_defaults(func=summarize_experiments_command)

    train = subparsers.add_parser("train-lora", help="Fine-tune a causal LLM with LoRA")
    train.add_argument("--base-model", required=True)
    train.add_argument("--train-jsonl", required=True)
    train.add_argument("--validation-jsonl")
    train.add_argument("--output-dir", required=True)
    train.add_argument("--max-seq-length", type=int, default=2048)
    train.add_argument("--per-device-train-batch-size", type=int, default=1)
    train.add_argument("--gradient-accumulation-steps", type=int, default=8)
    train.add_argument("--learning-rate", type=float, default=2e-4)
    train.add_argument("--num-train-epochs", type=float, default=3.0)
    train.add_argument("--lora-r", type=int, default=16)
    train.add_argument("--lora-alpha", type=int, default=32)
    train.add_argument("--lora-dropout", type=float, default=0.05)
    train.set_defaults(func=train_lora_command)

    extract = subparsers.add_parser("extract-markers", help="Extract cluster markers from AnnData")
    extract.add_argument("--adata", required=True, type=Path)
    extract.add_argument("--groupby", required=True)
    extract.add_argument("--output", required=True, type=Path)
    extract.add_argument("--n-top", type=int, default=25)
    extract.add_argument("--method", default="wilcoxon")
    extract.set_defaults(func=extract_markers_command)

    matrix = subparsers.add_parser(
        "prepare-matrix-benchmark",
        help="Cluster an AnnData matrix and write standard marker evidence CSV",
    )
    matrix.add_argument("--adata", required=True, type=Path)
    matrix.add_argument("--output-marker-db", required=True, type=Path)
    matrix.add_argument("--tissue", required=True)
    matrix.add_argument("--groupby", default="leiden")
    matrix.add_argument("--label-key")
    matrix.add_argument("--ontology-key")
    matrix.add_argument("--n-top", type=int, default=25)
    matrix.add_argument("--method", default="wilcoxon")
    matrix.add_argument("--run-clustering", action="store_true")
    matrix.add_argument("--resolution", type=float, default=1.0)
    matrix.add_argument("--no-normalize", action="store_true")
    matrix.add_argument("--min-cells", type=int, default=3)
    matrix.add_argument("--min-genes", type=int, default=200)
    matrix.add_argument("--seed", type=int, default=0)
    matrix.set_defaults(func=prepare_matrix_benchmark_command)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except FileNotFoundError as exc:
        missing = exc.filename or "unknown file"
        print(f"error: file not found: {missing}", file=sys.stderr)
        print(
            "hint: paths such as data/raw/cellmarker_raw.csv are placeholders; "
            "download the real source file or try data/raw/cellmarker_raw.example.csv.",
            file=sys.stderr,
        )
        return 1
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
