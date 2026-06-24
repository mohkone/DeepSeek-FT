"""Dataclasses used throughout the DeepSeekCell-FT pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .normalization import normalize_cl_id, normalize_gene_symbol, normalize_tissue


@dataclass(frozen=True)
class MarkerRecord:
    """Curated marker evidence for a tissue and cell type."""

    tissue: str
    cell_type: str
    markers: tuple[str, ...]
    cell_ontology_id: str | None = None
    source: str | None = None
    evidence: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "tissue", normalize_tissue(self.tissue))
        object.__setattr__(
            self,
            "markers",
            tuple(normalize_gene_symbol(marker) for marker in self.markers if marker),
        )
        object.__setattr__(self, "cell_ontology_id", normalize_cl_id(self.cell_ontology_id))


@dataclass(frozen=True)
class AnnotationExample:
    """One instruction-tuning example."""

    tissue: str
    markers: tuple[str, ...]
    cell_type: str
    reasoning: str
    cell_ontology_id: str | None = None
    source: str | None = None
    prompt: str | None = None
    response: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "tissue", normalize_tissue(self.tissue))
        object.__setattr__(
            self,
            "markers",
            tuple(normalize_gene_symbol(marker) for marker in self.markers if marker),
        )
        object.__setattr__(self, "cell_ontology_id", normalize_cl_id(self.cell_ontology_id))


@dataclass(frozen=True)
class AnnotationPrediction:
    """A model prediction for one cluster."""

    cell_type: str
    confidence: float | None = None
    cell_ontology_id: str | None = None
    reasoning: str | None = None
    raw_response: str | None = None
    runtime_seconds: float | None = None
    cost_usd: float | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "cell_ontology_id", normalize_cl_id(self.cell_ontology_id))

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "cell_type": self.cell_type,
            "confidence": self.confidence,
            "cell_ontology_id": self.cell_ontology_id,
            "reasoning": self.reasoning,
            "raw_response": self.raw_response,
            "runtime_seconds": self.runtime_seconds,
            "cost_usd": self.cost_usd,
        }
