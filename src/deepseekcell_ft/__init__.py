"""DeepSeekCell-FT research scaffold."""

from .annotation import MarkerOverlapAnnotator, parse_annotation_response
from .dataset_builder import generate_examples, load_marker_records, write_jsonl
from .evaluation import evaluate_predictions
from .schemas import AnnotationExample, AnnotationPrediction, MarkerRecord
from .source_ingestion import (
    MarkerTableConfig,
    merge_marker_record_sets,
    normalize_marker_table,
    summarize_marker_records,
)

__all__ = [
    "AnnotationExample",
    "AnnotationPrediction",
    "MarkerOverlapAnnotator",
    "MarkerTableConfig",
    "MarkerRecord",
    "evaluate_predictions",
    "generate_examples",
    "load_marker_records",
    "merge_marker_record_sets",
    "normalize_marker_table",
    "parse_annotation_response",
    "summarize_marker_records",
    "write_jsonl",
]

__version__ = "0.1.0"
