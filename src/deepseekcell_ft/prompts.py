"""Prompt templates for marker-gene cell type annotation."""

from __future__ import annotations

SYSTEM_PROMPT = (
    "You are DeepSeekCell-FT, a careful single-cell RNA-seq annotation assistant. "
    "Given tissue context and marker genes, predict the most specific cell type, "
    "a Cell Ontology ID when available, a confidence score from 0 to 1, and concise "
    "biological reasoning. Prefer established marker evidence over speculation."
)


def build_user_prompt(tissue: str, markers: tuple[str, ...] | list[str]) -> str:
    marker_text = ", ".join(markers)
    return f"Tissue: {tissue}\n\nCluster markers:\n{marker_text}"


def build_assistant_response(
    cell_type: str,
    reasoning: str,
    cell_ontology_id: str | None = None,
    confidence: float | None = None,
) -> str:
    lines = [f"Cell type: {cell_type}"]
    if cell_ontology_id:
        lines.append(f"Cell Ontology ID: {cell_ontology_id}")
    if confidence is not None:
        lines.append(f"Confidence: {confidence:.2f}")
    lines.append("")
    lines.append(f"Reasoning: {reasoning}")
    return "\n".join(lines)


def build_reasoning(cell_type: str, markers: tuple[str, ...], evidence: str | None = None) -> str:
    shown = ", ".join(markers[:3])
    if evidence:
        return f"{shown} support {cell_type}. {evidence.strip()}"
    return f"{shown} are established marker genes supporting {cell_type}."
