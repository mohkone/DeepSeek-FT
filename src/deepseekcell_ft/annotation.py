"""Annotation models and response parsing."""

from __future__ import annotations

import re
import time
from collections import Counter
from collections.abc import Sequence
from math import sqrt

from .normalization import normalize_cell_label, normalize_cl_id, parse_marker_list
from .prompts import SYSTEM_PROMPT, build_user_prompt
from .schemas import AnnotationPrediction, MarkerRecord

CELL_TYPE_RE = re.compile(
    r"(?im)^\s*(?:[-*]\s*)?(?:\*\*)?cell\s*type(?:\*\*)?\s*:\s*(?:\*\*)?\s*(.+)$"
)
CL_ID_RE = re.compile(
    r"(?im)^\s*(?:[-*]\s*)?(?:\*\*)?(?:cell\s*ontology\s*id|cl\s*id)"
    r"(?:\*\*)?\s*:\s*(?:\*\*)?\s*(CL[:_]\d+)"
)
CONFIDENCE_RE = re.compile(
    r"(?im)^\s*(?:[-*]\s*)?(?:\*\*)?confidence(?:\s*score)?(?:\*\*)?\s*:\s*"
    r"(?:\*\*)?\s*([01](?:\.\d+)?|\d{1,3}(?:\.\d+)?%)"
)
REASONING_RE = re.compile(
    r"(?ims)^\s*(?:[-*]\s*)?(?:\*\*)?(?:biological\s*)?reasoning(?:\*\*)?\s*:\s*(?:\*\*)?\s*(.+)"
)
TEXT_ONTOLOGY_LABEL_RE = re.compile(
    r"(?im)^\s*(?:[-*]\s*)?(?:\*\*)?cell\s*ontology\s*id(?:\*\*)?\s*:\s*"
    r"(?:\*\*)?\s*(?!CL[:_]\d+)(?!GO[:_]\d+)(.+)$"
)
LIKELY_TO_BE_RE = re.compile(
    r"(?is)\blikely\s+to\s+be\s+(?:a|an|the)?\s*(?:\*\*)?([A-Za-z][^*.\n]+?)(?:\*\*)?(?:[.;\n]|$)"
)
CANDIDATE_RE = re.compile(r"candidate\s*:\s*(\d+)", re.IGNORECASE)


def _clean_response_value(value: str) -> str:
    value = value.strip()
    value = re.sub(r"^\s*(?:[-*]\s*)+", "", value)
    value = value.strip()
    value = re.sub(r"^[`*_]+", "", value)
    value = re.sub(r"[`*_]+$", "", value)
    value = value.strip()
    value = re.sub(r"^\s*(?:a|an|the)\s+", "", value, flags=re.IGNORECASE)
    value = value.strip(" \t\r\n.;")
    return re.sub(r"\s+", " ", value)


def _parse_confidence(value: str) -> float:
    value = value.strip()
    if value.endswith("%"):
        confidence = float(value[:-1]) / 100.0
    else:
        confidence = float(value)
    return min(1.0, max(0.0, confidence))


def _fallback_cell_type(text: str) -> str:
    ontology_label_match = TEXT_ONTOLOGY_LABEL_RE.search(text)
    if ontology_label_match:
        return _clean_response_value(ontology_label_match.group(1))

    likely_match = LIKELY_TO_BE_RE.search(text)
    if likely_match:
        return _clean_response_value(likely_match.group(1))

    first_line = text.strip().splitlines()[0] if text.strip() else ""
    if re.search(r"\b(given|provided|marker|predict|cell\s*type)\b", first_line, re.IGNORECASE):
        return "Unknown"
    return _clean_response_value(first_line) if first_line else "Unknown"


def parse_annotation_response(text: str) -> AnnotationPrediction:
    """Parse a structured annotation response from an LLM."""

    cell_match = CELL_TYPE_RE.search(text)
    cl_match = CL_ID_RE.search(text)
    confidence_match = CONFIDENCE_RE.search(text)
    reasoning_match = REASONING_RE.search(text)

    if cell_match:
        cell_type = _clean_response_value(cell_match.group(1))
    else:
        cell_type = _fallback_cell_type(text)

    confidence = None
    if confidence_match:
        confidence = _parse_confidence(confidence_match.group(1))

    return AnnotationPrediction(
        cell_type=cell_type,
        confidence=confidence,
        cell_ontology_id=normalize_cl_id(cl_match.group(1)) if cl_match else None,
        reasoning=_clean_response_value(reasoning_match.group(1)) if reasoning_match else None,
        raw_response=text,
    )


class MarkerOverlapAnnotator:
    """A transparent marker-overlap baseline."""

    def __init__(self, records: Sequence[MarkerRecord]):
        if not records:
            raise ValueError("records must not be empty")
        self.records = list(records)
        marker_counts = Counter(marker for record in records for marker in set(record.markers))
        self.marker_weights = {
            marker: 1.0 / count
            for marker, count in marker_counts.items()
            if count > 0
        }

    def rank_candidates(
        self,
        tissue: str,
        markers: str | Sequence[str],
        top_k: int = 5,
    ) -> list[dict[str, object]]:
        """Return top marker-overlap candidates as dictionaries."""

        query_markers = set(parse_marker_list(markers))
        if not query_markers:
            return []

        tissue_norm = tissue.strip().lower()
        candidates = [
            record for record in self.records if record.tissue.strip().lower() == tissue_norm
        ] or self.records

        scored: list[tuple[float, MarkerRecord, set[str]]] = []
        for record in candidates:
            record_markers = set(record.markers)
            overlap = query_markers & record_markers
            if not overlap:
                score = 0.0
            else:
                numerator = sum(self.marker_weights.get(marker, 1.0) for marker in overlap)
                denominator = sum(
                    self.marker_weights.get(marker, 1.0)
                    for marker in query_markers | record_markers
                )
                score = numerator / denominator if denominator else 0.0
            scored.append((score, record, overlap))

        scored.sort(
            key=lambda item: (
                item[0],
                len(item[2]),
                normalize_cell_label(item[1].cell_type),
            ),
            reverse=True,
        )
        ranked: list[dict[str, object]] = []
        seen: set[tuple[str, str | None]] = set()
        for score, record, overlap in scored:
            key = (normalize_cell_label(record.cell_type), record.cell_ontology_id)
            if key in seen:
                continue
            seen.add(key)
            ranked.append(
                {
                    "rank": len(ranked) + 1,
                    "cell_type": record.cell_type,
                    "cell_ontology_id": record.cell_ontology_id,
                    "marker_score": score,
                    "overlap": sorted(overlap),
                    "record_markers": list(record.markers),
                }
            )
            if len(ranked) >= top_k:
                break
        return ranked

    def predict(self, tissue: str, markers: str | Sequence[str]) -> AnnotationPrediction:
        start = time.perf_counter()
        ranked = self.rank_candidates(tissue, markers, top_k=2)
        if not ranked:
            return AnnotationPrediction(
                cell_type="Unknown",
                confidence=0.0,
                reasoning="No marker genes were provided.",
                runtime_seconds=time.perf_counter() - start,
            )

        best = ranked[0]
        best_score = float(best["marker_score"])
        second_score = float(ranked[1]["marker_score"]) if len(ranked) > 1 else 0.0
        confidence = min(1.0, max(0.0, best_score + max(0.0, best_score - second_score)))
        overlap = best["overlap"]
        overlap_text = ", ".join(overlap) if overlap else "no direct overlap"
        reasoning = (
            f"Best marker overlap with {best['cell_type']}: {overlap_text}. "
            f"Weighted Jaccard score {best_score:.3f}."
        )
        if best_score == 0.0:
            return AnnotationPrediction(
                cell_type="Unknown",
                confidence=0.0,
                reasoning=reasoning,
                runtime_seconds=time.perf_counter() - start,
            )
        return AnnotationPrediction(
            cell_type=str(best["cell_type"]),
            cell_ontology_id=best["cell_ontology_id"],
            confidence=confidence,
            reasoning=reasoning,
            runtime_seconds=time.perf_counter() - start,
        )


NEGATIVE_MARKER_COLUMNS = (
    "negative_markers",
    "negative_marker_genes",
    "negative_marker",
    "negative_genes",
    "neg_markers",
    "neg_marker_genes",
    "minus_markers",
    "exclude_markers",
)


def _negative_markers(record: MarkerRecord) -> tuple[str, ...]:
    """Read optional negative markers from marker-record metadata."""

    for column in NEGATIVE_MARKER_COLUMNS:
        value = record.metadata.get(column)
        if value:
            return parse_marker_list(str(value))
    return ()


class ScTypeStyleAnnotator:
    """A scType-style positive/negative marker-set scoring baseline."""

    def __init__(
        self,
        records: Sequence[MarkerRecord],
        negative_weight: float = 1.0,
    ):
        if not records:
            raise ValueError("records must not be empty")
        if negative_weight < 0:
            raise ValueError("negative_weight must be non-negative")
        self.records = list(records)
        self.negative_weight = negative_weight
        marker_counts = Counter()
        for record in self.records:
            marker_counts.update(set(record.markers))
            marker_counts.update(set(_negative_markers(record)))
        self.marker_weights = {
            marker: 1.0 / count
            for marker, count in marker_counts.items()
            if count > 0
        }

    def rank_candidates(
        self,
        tissue: str,
        markers: str | Sequence[str],
        top_k: int = 5,
    ) -> list[dict[str, object]]:
        """Return top scType-style marker-set candidates as dictionaries."""

        query_markers = set(parse_marker_list(markers))
        if not query_markers:
            return []

        tissue_norm = tissue.strip().lower()
        candidates = [
            record for record in self.records if record.tissue.strip().lower() == tissue_norm
        ] or self.records

        scored: list[tuple[float, int, int, MarkerRecord, set[str], set[str]]] = []
        for record in candidates:
            positive_markers = set(record.markers)
            negative_markers = set(_negative_markers(record))
            positive_overlap = query_markers & positive_markers
            negative_overlap = query_markers & negative_markers

            positive_score = sum(
                self.marker_weights.get(marker, 1.0) for marker in positive_overlap
            ) / sqrt(max(len(positive_markers), 1))
            negative_score = sum(
                self.marker_weights.get(marker, 1.0) for marker in negative_overlap
            ) / sqrt(max(len(negative_markers), 1))
            score = positive_score - (self.negative_weight * negative_score)
            scored.append(
                (
                    score,
                    len(positive_overlap),
                    len(negative_overlap),
                    record,
                    positive_overlap,
                    negative_overlap,
                )
            )

        scored.sort(
            key=lambda item: (
                item[0],
                item[1],
                -item[2],
                normalize_cell_label(item[3].cell_type),
            ),
            reverse=True,
        )
        ranked: list[dict[str, object]] = []
        seen: set[tuple[str, str | None]] = set()
        for (
            score,
            positive_count,
            negative_count,
            record,
            positive_overlap,
            negative_overlap,
        ) in scored:
            key = (normalize_cell_label(record.cell_type), record.cell_ontology_id)
            if key in seen:
                continue
            seen.add(key)
            ranked.append(
                {
                    "rank": len(ranked) + 1,
                    "cell_type": record.cell_type,
                    "cell_ontology_id": record.cell_ontology_id,
                    "sctype_score": score,
                    "positive_overlap_count": positive_count,
                    "negative_overlap_count": negative_count,
                    "positive_overlap": sorted(positive_overlap),
                    "negative_overlap": sorted(negative_overlap),
                    "record_markers": list(record.markers),
                    "negative_markers": list(_negative_markers(record)),
                }
            )
            if len(ranked) >= top_k:
                break
        return ranked

    def predict(self, tissue: str, markers: str | Sequence[str]) -> AnnotationPrediction:
        start = time.perf_counter()
        ranked = self.rank_candidates(tissue, markers, top_k=2)
        if not ranked:
            return AnnotationPrediction(
                cell_type="Unknown",
                confidence=0.0,
                reasoning="No marker genes were provided.",
                runtime_seconds=time.perf_counter() - start,
            )

        best = ranked[0]
        best_score = float(best["sctype_score"])
        second_score = float(ranked[1]["sctype_score"]) if len(ranked) > 1 else 0.0
        confidence = min(1.0, max(0.0, best_score + max(0.0, best_score - second_score)))
        positive_overlap = best["positive_overlap"]
        negative_overlap = best["negative_overlap"]
        positive_text = ", ".join(positive_overlap) if positive_overlap else "no positive overlap"
        negative_text = ", ".join(negative_overlap) if negative_overlap else "no negative overlap"
        reasoning = (
            f"Best scType-style score for {best['cell_type']}: "
            f"positive markers {positive_text}; negative markers {negative_text}. "
            f"Score {best_score:.3f}."
        )
        if best_score <= 0.0:
            return AnnotationPrediction(
                cell_type="Unknown",
                confidence=0.0,
                reasoning=reasoning,
                raw_response=f"scType-style score: {best_score:.6f}",
                runtime_seconds=time.perf_counter() - start,
            )
        return AnnotationPrediction(
            cell_type=str(best["cell_type"]),
            cell_ontology_id=best["cell_ontology_id"],
            confidence=confidence,
            reasoning=reasoning,
            raw_response=f"scType-style score: {best_score:.6f}",
            runtime_seconds=time.perf_counter() - start,
        )


class TransformersAnnotator:
    """Prompt-only local Hugging Face text-generation annotator."""

    def __init__(
        self,
        model_name_or_path: str,
        max_new_tokens: int = 256,
        temperature: float = 0.1,
        **pipeline_kwargs: object,
    ):
        try:
            from transformers import pipeline
        except ImportError as exc:
            raise ImportError(
                "TransformersAnnotator requires the 'train' optional dependencies. "
                "Install with: python -m pip install -e .[train]"
            ) from exc

        self.model_name_or_path = model_name_or_path
        self.max_new_tokens = max_new_tokens
        self.temperature = temperature
        self.generator = pipeline(
            "text-generation",
            model=model_name_or_path,
            **pipeline_kwargs,
        )

    def predict(self, tissue: str, markers: str | Sequence[str]) -> AnnotationPrediction:
        start = time.perf_counter()
        marker_tuple = parse_marker_list(markers)
        user_prompt = build_user_prompt(tissue, marker_tuple)
        prompt = (
            f"{SYSTEM_PROMPT}\n\n{user_prompt}\n\n"
            "Respond with exactly these fields: Cell type, Cell Ontology ID, "
            "Confidence, Reasoning."
        )
        output = self.generator(
            prompt,
            max_new_tokens=self.max_new_tokens,
            temperature=self.temperature,
            do_sample=self.temperature > 0,
            return_full_text=False,
        )
        text = output[0]["generated_text"] if output else ""
        prediction = parse_annotation_response(text)
        return AnnotationPrediction(
            cell_type=prediction.cell_type,
            confidence=prediction.confidence,
            cell_ontology_id=prediction.cell_ontology_id,
            reasoning=prediction.reasoning,
            raw_response=prediction.raw_response,
            runtime_seconds=time.perf_counter() - start,
        )


class PromptOnlyCausalLMAnnotator:
    """Prompt-only local Hugging Face causal-LM annotator."""

    def __init__(
        self,
        model_name_or_path: str,
        max_new_tokens: int = 128,
        temperature: float = 0.0,
    ):
        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer
        except ImportError as exc:
            raise ImportError(
                "PromptOnlyCausalLMAnnotator requires optional training dependencies. "
                "Install with: python -m pip install -e .[train]"
            ) from exc

        self.torch = torch
        self.model_name_or_path = model_name_or_path
        self.max_new_tokens = max_new_tokens
        self.temperature = temperature
        self.tokenizer = AutoTokenizer.from_pretrained(
            model_name_or_path,
            use_fast=True,
            trust_remote_code=True,
        )
        if self.tokenizer.pad_token is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token

        self.model = AutoModelForCausalLM.from_pretrained(
            model_name_or_path,
            device_map="auto",
            torch_dtype="auto",
            trust_remote_code=True,
            low_cpu_mem_usage=True,
        )
        self.model.eval()

    def generate_text(self, prompt: str) -> tuple[str, float]:
        """Generate text for a fully formatted prompt."""

        start = time.perf_counter()
        inputs = self.tokenizer(prompt, return_tensors="pt")
        device = getattr(self.model, "device", None)
        if device is None:
            device = next(self.model.parameters()).device
        inputs = {key: value.to(device) for key, value in inputs.items()}

        generation_kwargs: dict[str, object] = {
            "max_new_tokens": self.max_new_tokens,
            "do_sample": self.temperature > 0,
            "pad_token_id": self.tokenizer.pad_token_id,
        }
        if self.temperature > 0:
            generation_kwargs["temperature"] = self.temperature

        with self.torch.inference_mode():
            output_ids = self.model.generate(**inputs, **generation_kwargs)

        prompt_length = inputs["input_ids"].shape[-1]
        generated_ids = output_ids[0][prompt_length:]
        text = self.tokenizer.decode(generated_ids, skip_special_tokens=True).strip()
        return text, time.perf_counter() - start

    def _format_prompt(self, tissue: str, markers: str | Sequence[str]) -> str:
        marker_tuple = parse_marker_list(markers)
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_user_prompt(tissue, marker_tuple)},
        ]
        if hasattr(self.tokenizer, "apply_chat_template"):
            try:
                return self.tokenizer.apply_chat_template(
                    messages,
                    tokenize=False,
                    add_generation_prompt=True,
                )
            except Exception:
                pass
        return (
            f"{SYSTEM_PROMPT}\n\n{build_user_prompt(tissue, marker_tuple)}\n\n"
            "Assistant:"
        )

    def predict(self, tissue: str, markers: str | Sequence[str]) -> AnnotationPrediction:
        prompt = self._format_prompt(tissue, markers)
        text, runtime = self.generate_text(prompt)
        prediction = parse_annotation_response(text)
        return AnnotationPrediction(
            cell_type=prediction.cell_type,
            confidence=prediction.confidence,
            cell_ontology_id=prediction.cell_ontology_id,
            reasoning=prediction.reasoning,
            raw_response=prediction.raw_response,
            runtime_seconds=runtime,
        )


class LoraAdapterAnnotator:
    """Local Hugging Face annotator using a trained PEFT/LoRA adapter."""

    def __init__(
        self,
        base_model_name_or_path: str,
        adapter_name_or_path: str,
        max_new_tokens: int = 128,
        temperature: float = 0.0,
    ):
        try:
            import torch
            from peft import PeftModel
            from transformers import AutoModelForCausalLM, AutoTokenizer
        except ImportError as exc:
            raise ImportError(
                "LoraAdapterAnnotator requires optional training dependencies. "
                "Install with: python -m pip install -e .[train]"
            ) from exc

        self.torch = torch
        self.max_new_tokens = max_new_tokens
        self.temperature = temperature
        self.tokenizer = AutoTokenizer.from_pretrained(
            adapter_name_or_path,
            use_fast=True,
            trust_remote_code=True,
        )
        if self.tokenizer.pad_token is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token

        base_model = AutoModelForCausalLM.from_pretrained(
            base_model_name_or_path,
            device_map="auto",
            torch_dtype="auto",
            trust_remote_code=True,
            low_cpu_mem_usage=True,
        )
        self.model = PeftModel.from_pretrained(base_model, adapter_name_or_path)
        self.model.eval()

    def generate_text(self, prompt: str) -> tuple[str, float]:
        """Generate text for a fully formatted prompt."""

        start = time.perf_counter()
        inputs = self.tokenizer(prompt, return_tensors="pt")
        device = getattr(self.model, "device", None)
        if device is None:
            device = next(self.model.parameters()).device
        inputs = {key: value.to(device) for key, value in inputs.items()}

        generation_kwargs: dict[str, object] = {
            "max_new_tokens": self.max_new_tokens,
            "do_sample": self.temperature > 0,
            "pad_token_id": self.tokenizer.pad_token_id,
        }
        if self.temperature > 0:
            generation_kwargs["temperature"] = self.temperature

        with self.torch.inference_mode():
            output_ids = self.model.generate(**inputs, **generation_kwargs)

        prompt_length = inputs["input_ids"].shape[-1]
        generated_ids = output_ids[0][prompt_length:]
        text = self.tokenizer.decode(generated_ids, skip_special_tokens=True).strip()
        return text, time.perf_counter() - start

    def _format_prompt(self, tissue: str, markers: str | Sequence[str]) -> str:
        marker_tuple = parse_marker_list(markers)
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_user_prompt(tissue, marker_tuple)},
        ]
        if hasattr(self.tokenizer, "apply_chat_template"):
            return self.tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True,
            )
        return (
            f"{SYSTEM_PROMPT}\n\n{build_user_prompt(tissue, marker_tuple)}\n\n"
            "Assistant:"
        )

    def predict(self, tissue: str, markers: str | Sequence[str]) -> AnnotationPrediction:
        prompt = self._format_prompt(tissue, markers)
        text, runtime = self.generate_text(prompt)
        prediction = parse_annotation_response(text)
        return AnnotationPrediction(
            cell_type=prediction.cell_type,
            confidence=prediction.confidence,
            cell_ontology_id=prediction.cell_ontology_id,
            reasoning=prediction.reasoning,
            raw_response=prediction.raw_response,
            runtime_seconds=runtime,
        )


def build_candidate_rerank_prompt(
    tissue: str,
    markers: str | Sequence[str],
    candidates: Sequence[dict[str, object]],
) -> str:
    """Build a constrained candidate-choice prompt."""

    marker_text = ", ".join(parse_marker_list(markers))
    candidate_lines = []
    for candidate in candidates:
        cl_id = candidate.get("cell_ontology_id") or "NA"
        overlap = candidate.get("overlap") or []
        overlap_text = ", ".join(str(marker) for marker in overlap) or "none"
        candidate_lines.append(
            f"{candidate['rank']}. {candidate['cell_type']} | CL ID: {cl_id} | "
            f"marker score: {float(candidate['marker_score']):.4f} | overlap: {overlap_text}"
        )
    user_prompt = (
        f"Tissue: {tissue}\n\n"
        f"Cluster markers:\n{marker_text}\n\n"
        "Candidate cell types:\n"
        + "\n".join(candidate_lines)
        + "\n\nChoose exactly one candidate from the list. "
        "Do not invent a new cell type or Cell Ontology ID. "
        "Respond with exactly these fields: Candidate, Cell type, Cell Ontology ID, "
        "Confidence, Reasoning."
    )
    return f"{SYSTEM_PROMPT}\n\n{user_prompt}\n\nAssistant:"


def choose_candidate_from_response(
    response_text: str,
    candidates: Sequence[dict[str, object]],
) -> tuple[dict[str, object], str, AnnotationPrediction]:
    """Parse a reranker response and return the constrained candidate."""

    parsed = parse_annotation_response(response_text)
    rank_match = CANDIDATE_RE.search(response_text)
    if rank_match:
        rank = int(rank_match.group(1))
        for candidate in candidates:
            if int(candidate["rank"]) == rank:
                return candidate, "candidate_number", parsed

    parsed_label = normalize_cell_label(parsed.cell_type)
    for candidate in candidates:
        if normalize_cell_label(str(candidate["cell_type"])) == parsed_label:
            return candidate, "cell_type_label", parsed

    return candidates[0], "fallback_top_candidate", parsed


class CandidateRerankAnnotator:
    """Use marker-overlap candidates and a LoRA adapter for constrained reranking."""

    def __init__(
        self,
        marker_records: Sequence[MarkerRecord],
        base_model_name_or_path: str,
        adapter_name_or_path: str,
        top_k: int = 5,
        max_new_tokens: int = 128,
        temperature: float = 0.0,
    ):
        self.candidate_generator = MarkerOverlapAnnotator(marker_records)
        self.llm = LoraAdapterAnnotator(
            base_model_name_or_path=base_model_name_or_path,
            adapter_name_or_path=adapter_name_or_path,
            max_new_tokens=max_new_tokens,
            temperature=temperature,
        )
        self.top_k = top_k
        self.last_candidates: list[dict[str, object]] = []
        self.last_selection_source: str | None = None

    def predict(self, tissue: str, markers: str | Sequence[str]) -> AnnotationPrediction:
        candidates = self.candidate_generator.rank_candidates(tissue, markers, top_k=self.top_k)
        self.last_candidates = candidates
        if not candidates:
            self.last_selection_source = "no_candidates"
            return AnnotationPrediction(
                cell_type="Unknown",
                confidence=0.0,
                reasoning="No candidate cell types were available.",
            )

        prompt = build_candidate_rerank_prompt(tissue, markers, candidates)
        response_text, runtime = self.llm.generate_text(prompt)
        candidate, selection_source, parsed = choose_candidate_from_response(
            response_text,
            candidates,
        )
        self.last_selection_source = selection_source
        reasoning = parsed.reasoning or ""
        if selection_source == "fallback_top_candidate":
            reasoning = (
                f"Reranker response could not be matched to a candidate; "
                f"falling back to top marker-overlap candidate. {reasoning}"
            ).strip()
        confidence = parsed.confidence
        if confidence is None:
            confidence = min(1.0, max(0.0, float(candidate["marker_score"])))
        return AnnotationPrediction(
            cell_type=str(candidate["cell_type"]),
            cell_ontology_id=candidate.get("cell_ontology_id"),
            confidence=confidence,
            reasoning=reasoning,
            raw_response=response_text,
            runtime_seconds=runtime,
        )


def labels_match(left: str, right: str) -> bool:
    """Return true when two cell type labels match after conservative normalization."""

    return normalize_cell_label(left) == normalize_cell_label(right)
