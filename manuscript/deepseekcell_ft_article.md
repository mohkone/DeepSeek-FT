# DeepSeekCell-FT: Evaluating Fine-Tuned and Candidate-Constrained Large Language Models for Ontology-Grounded Cell Type Annotation

## Abstract

Automated cell type annotation remains a central bottleneck in single-cell
RNA-seq analysis. Reference-based tools and marker-rule systems are effective,
but they can struggle when marker evidence is partial, noisy, tissue-specific,
or expressed in natural-language biological context. We present DeepSeekCell-FT,
a reproducible benchmark and fine-tuning pipeline for ontology-grounded
cluster-level cell type annotation from marker genes. Rather than assuming that
fine-tuning alone improves annotation, we evaluate two LLM usage modes:
open-ended generation of labels and Cell Ontology IDs, and constrained
reranking of evidence-backed Marker-overlap candidates. On a PanglaoDB-derived
label-overlap benchmark, prompt-only DeepSeek and Qwen performed poorly
(0.0000 and 0.0449 accuracy, respectively). Open-ended DeepSeek-7B LoRA
improved over prompt-only inference but remained substantially weaker than a
transparent Marker-overlap baseline (0.3652 versus 0.9944 accuracy), and
generated unreliable Cell Ontology IDs. Candidate-constrained reranking was much
stronger (0.8876 accuracy, 0.8941 mapped Cell Ontology accuracy), but still did not
surpass Marker-overlap selection. Synthetic marker-dropout and distractor-noise
stress tests narrowed the gap but did not reverse it. PBMC3k, Baron pancreas,
and Zeisel brain matrix-derived validation datasets confirmed that the
matrix-to-marker workflow runs end to end, with Marker-overlap and LoRA
reranking both achieving perfect accuracy over broad curated cluster labels.
These results show that fine-tuning alone is insufficient for reliable
open-ended cell type annotation on the current benchmark, while constrained
candidate selection is a more promising and auditable role for biological LLMs.

## 1. Introduction

Single-cell RNA-seq studies commonly summarize cell clusters by differentially
expressed marker genes. Expert annotators translate these markers into cell
type labels by combining gene-level evidence, tissue context, known lineage
relationships, and prior literature. This reasoning process is well suited to
large language models, but prompt-only models can be inconsistent and may
produce labels that are difficult to align with controlled vocabularies.

DeepSeekCell-FT addresses this gap by evaluating instruction-following models
on marker-to-cell-type examples derived from curated marker databases, reference
atlases, and ontology mappings. The central question is not simply whether
fine-tuning improves an LLM, but whether an LLM should generate cell types
open-endedly or operate inside a constrained, evidence-backed annotation
workflow.

## 2. Research Question

When using marker genes for ontology-grounded cell type annotation, is
fine-tuned open-ended generation reliable enough for direct annotation, or are
LLMs more useful as constrained rerankers over evidence-backed candidate cell
types?

## 3. Contributions

1. A reproducible instruction-tuning pipeline that converts curated marker
   evidence into chat-style fine-tuning examples.
2. An ontology-aware evaluation of prompt-only DeepSeek and Qwen, open-ended
   DeepSeek-7B LoRA generation, Marker-overlap, and candidate-constrained
   DeepSeek-7B LoRA reranking.
3. A negative result showing that fine-tuning alone is insufficient for
   reliable open-ended label and Cell Ontology ID generation on the current
   marker-record benchmark.
4. A robustness analysis showing that candidate reranking is substantially
   stronger than open-ended generation, but remains weaker than Marker-overlap
   selection under clean and synthetically corrupted marker lists.
5. A matrix-to-ontology workflow:
   gene expression matrix -> marker extraction -> fine-tuned LLM -> cell type
   -> Cell Ontology ID.

## 4. Data Sources

Training examples are generated from curated and atlas-derived resources:

- PBMC and other public single-cell benchmark datasets with expert labels.
- CellMarker marker evidence.
- PanglaoDB marker evidence.
- Cell Ontology label and identifier mappings.
- Human Cell Atlas-derived annotated references.

Each marker evidence record uses the schema:

```csv
tissue,cell_type,cell_ontology_id,markers,source,evidence
PBMC,CD4+ T cell,CL:0000624,"IL7R,LTB,IL32,CCR7",CellMarker,"Canonical helper T cell evidence"
```

Instruction examples are augmented by sampling marker subsets, varying
marker order, adding limited distractor markers, and preserving tissue context.
Augmentations are split by dataset and tissue when possible to reduce
evidence leakage.

## 5. Methods

### 5.1 Input and Output Format

Input:

```text
Tissue: PBMC

Cluster markers:
IL7R, LTB, MALAT1, IL32
```

Output:

```text
Cell type: CD4+ T cell
Cell Ontology ID: CL:0000624
Confidence: 0.90

Reasoning: IL7R and LTB support CD4+ T cell identity in PBMC.
```

### 5.2 Instruction Dataset Construction

For each curated marker record, the pipeline generates multiple instruction
pairs by sampling positive markers and adding controlled marker noise. This
simulates realistic cluster marker lists where housekeeping genes, ribosomal
genes, or lineage-adjacent markers may appear alongside canonical markers.

### 5.3 Model Fine-Tuning

The current GPU experiment fine-tunes DeepSeek-7B with a parameter-efficient
LoRA adapter on chat-formatted instruction data. The codebase is structured so
that Llama 3 8B and Qwen 7B checkpoints can be evaluated with the same workflow
in future runs. Hyperparameters are held constant across comparable LoRA runs
when feasible:

- LoRA rank: 16
- LoRA alpha: 32
- LoRA dropout: 0.05
- Maximum sequence length: 2048
- Learning rate: 2e-4
- Epochs: selected by validation performance

### 5.4 Baselines

The benchmark currently includes:

- Prompt-only DeepSeek and Qwen with the same output schema.
- Marker-overlap baseline using weighted marker Jaccard similarity.
- SingleR as an off-the-shelf reference-based traditional method on
  matrix-derived validation datasets.

scType is an important marker-rule comparator, but no harmonized scType result
is reported in the present version. It is therefore treated as remaining work
rather than as a completed baseline.

### 5.5 Evaluation

Primary metrics:

- Accuracy: exact match after conservative label normalization.
- Macro F1: robustness across common and rare labels.
- Cell Ontology accuracy: exact CL ID match when a gold ID exists.
- Confidence calibration: expected calibration error.
- Runtime: wall-clock inference time per cluster.
- Cost: API or compute-estimated cost per annotated dataset.

Secondary analyses:

- Held-out tissue generalization.
- Label granularity errors, such as T cell versus CD4+ T cell.
- Marker noise sensitivity.
- Ontology consistency between predicted label and CL ID.
- Failure mode audit of rationales.

## 6. Experimental Design

The current PanglaoDB/Cell Ontology benchmark uses two complementary split
regimes:

1. Label-overlap split: examples are stratified by cell type so train,
   validation, and test contain overlapping labels. This is the standard
   in-distribution fine-tuning comparison. The current split contains 912
   instruction examples across 177 labels, with 555 training, 179 validation,
   and 178 test examples. All test labels are represented in the training set.
2. Label-held-out grouped split: examples are grouped by tissue, cell type,
   and source so augmented marker lists from the same curated record cannot
   appear in multiple splits. This creates a harder generalization benchmark.
   The current split contains 728 training, 92 validation, and 92 test
   examples; all 23 test labels are unseen during training.

Gold labels are mapped to Cell Ontology IDs for ontology-level evaluation when
CL IDs are available. After PanglaoDB normalization, automated ontology
matching, and reviewed curation, 880 of 912 instruction examples have CL IDs
(96.49% coverage). The remaining 32 instruction examples are retained for
label accuracy and macro F1, but excluded from CL accuracy denominators.
Supplementary Table S1 (`outputs/label_support_ontology_coverage.csv`) reports
per-label support across train, validation, and test splits for all 177 labels,
including per-label Cell Ontology coverage and assigned CL IDs.

## 7. Statistical Analysis

Model comparisons used paired tests at the cluster level where each method
annotated the same examples. Accuracy differences were tested with exact
McNemar tests on discordant paired predictions. Accuracy and macro-F1
differences were summarized with paired bootstrap 95% confidence intervals
using 500 bootstrap resamples over examples and a fixed random seed.
Calibration was summarized with expected calibration error.

## 8. Current Results

The Marker-overlap baseline provides a transparent non-LLM reference point
before GPU-based LoRA training. On the label-overlap split, Marker-overlap
achieved 0.9944 accuracy, 0.9924 macro F1, and 0.9941 Cell Ontology accuracy
over 178 test examples. On the harder label-held-out split, it achieved 0.9891
accuracy, 0.9938 macro F1, and 0.9881 Cell Ontology accuracy over 92 test
examples. Runtime was approximately 0.0002 seconds per cluster in both settings.

Prompt-only LLM baselines performed poorly under the same label-overlap
evaluation. Prompt-only DeepSeek reached 0.0000 accuracy, 0.0000 macro F1, and
0.0000 mapped Cell Ontology accuracy over 178 test examples. Prompt-only
Qwen2.5-7B-Instruct reached 0.0449 accuracy, 0.0352 macro F1, and 0.0471 mapped
Cell Ontology accuracy. Error analysis showed that prompt-only models often
produced broad or non-canonical labels, unsupported ontology identifiers, and
overconfident incorrect outputs. These results provide an important baseline:
fine-tuning did improve over prompt-only DeepSeek, but did not close the gap to
transparent Marker-overlap selection.

DeepSeek-7B LoRA fine-tuning was then run on an AutoDL GPU instance using an
NVIDIA RTX PRO 6000 Blackwell Server Edition GPU. The label-overlap run trained
for three epochs on 555 examples and reached a final validation loss of 0.3979
with validation token accuracy of 0.9006. However, test-set annotation accuracy
remained substantially below the Marker-overlap baseline: 0.3652 accuracy and
0.2844 macro F1 over 178 test examples. The raw generated Cell Ontology IDs
matched only 3 of 170 test examples with gold CL IDs, yielding 0.0176 Cell
Ontology accuracy. Post-hoc mapping from predicted labels to unambiguous
curated Cell Ontology IDs improved mapped Cell Ontology accuracy to 0.3824, confirming
that generated ontology IDs were unreliable even when the predicted label was
sometimes correct.

A constrained reranking variant substantially improved over open-ended LoRA
generation. In this setting, Marker-overlap supplied the top five candidate
cell types and Cell Ontology IDs, and the LoRA adapter was required to choose
one candidate. Candidate reranking reached 0.8876 accuracy, 0.8571 macro F1,
and 0.8941 mapped Cell Ontology accuracy over the same 178 label-overlap test
examples. This result shows that the fine-tuned model is more useful when it is
anchored to evidence-backed candidates, but it still degraded performance
relative to the Marker-overlap top-1 baseline.

A noisy-marker stress test was then created by dropping 50% of the original
test markers and adding three distractor genes per example. This perturbation
reduced the Marker-overlap baseline from 0.9944 to 0.9438 accuracy, but
Marker-overlap remained stronger than candidate reranking. DeepSeek-7B LoRA
reranking achieved 0.8652 accuracy, 0.8248 macro F1, and 0.8706 mapped Cell Ontology
accuracy on the perturbed split. Thus, moderate marker noise was not sufficient
to reveal an advantage for the LLM reranker over weighted marker matching.
Reranking diagnostics showed that the correct label was still present in the
top five Marker-overlap candidates for 0.9944 of perturbed test examples, while
the Marker-overlap top candidate alone was correct for 0.9494. The LoRA
reranker fixed 3 examples where the top candidate was wrong, but harmed 18
examples where the top candidate was already correct, indicating that the main
failure mode was candidate selection rather than candidate retrieval.

The robustness grid was extended to more severe synthetic perturbations. With
75% marker dropout and five distractor genes, Marker-overlap achieved 0.7697
accuracy, while the reranking candidate audit found the top candidate correct
for 0.7753 of examples and the true label present in the top five candidates
for 0.9888 of examples. The LoRA reranker reached 0.6910 accuracy, fixing 4
top-candidate errors but harming 19 correct top-candidate predictions. With
90% marker dropout and eight distractor genes, Marker-overlap accuracy was
0.6798 and LoRA reranking accuracy was 0.6461; the true label was still in the
top five candidates for 0.9663 of examples. These stress tests reinforce that
the present LoRA adapter does not outperform Marker-overlap selection, even
when marker lists are heavily degraded.

As an initial matrix-derived validation dataset, the workflow was applied to the
Scanpy PBMC3k processed tutorial dataset. Cluster labels were aligned to the
standard tutorial annotation categories and Cell Ontology IDs, top marker genes
were extracted from the AnnData matrix, and eight cluster-level marker-list
instructions were evaluated. Marker-overlap and DeepSeek-7B LoRA reranking both
achieved 1.0000 accuracy, 1.0000 macro F1, and 1.0000 Cell Ontology accuracy.
This confirms that the matrix-to-marker-to-annotation pipeline runs end to end
on a recognizable scRNA-seq benchmark. Because this PBMC3k benchmark contains
only eight broad tutorial-labeled clusters, it should be interpreted as a
sanity and validation dataset rather than evidence that the approach is
robust across tissues or fine-grained cell states.

The matrix-derived validation was then extended to the Baron pancreas subset of
the Scanpy pancreas integration tutorial object. The workflow filtered to
`sample=Baron`, mapped 14 Baron cell-type labels to Cell Ontology IDs, extracted
top ranked marker genes per label group, and evaluated 14 cluster-level
marker-list instructions. Marker-overlap and DeepSeek-7B LoRA reranking again
achieved 1.0000 accuracy, 1.0000 macro F1, and 1.0000 Cell Ontology accuracy.
This adds a second tissue and endocrine-cell benchmark, but it remains a
label-group validation rather than a fully independent expert reannotation or
traditional-reference comparison.

As a preliminary brain matrix-derived validation dataset, the workflow was also applied
to the UCSC Cell Browser Zeisel 2015 mouse cortex and hippocampus dataset.
Metadata labels were harmonized into 12 ontology-mapped brain and vascular
cell-type groups, retaining 2925 cells and skipping 80 unresolved ambiguous
cells from combined broad metadata classes. Marker-overlap achieved 1.0000
accuracy, 1.0000 macro F1, and 1.0000 Cell Ontology accuracy on the resulting
12 cluster-level marker-list instructions. DeepSeek-7B LoRA reranking also
achieved 1.0000 accuracy, 1.0000 macro F1, and 1.0000 Cell Ontology accuracy.
This provides a third matrix-derived validation and directly covers brain cell
classes relevant to the neuron/glia confusions observed in the PanglaoDB error
analysis, but it remains a label-group validation without a traditional
reference-method comparison.

![Figure 1. Noise robustness accuracy curves for Marker-overlap and DeepSeek-7B LoRA reranking.](../outputs/noise_robustness_accuracy.svg)

Figure 1. Accuracy on the label-overlap test set after progressively stronger
synthetic marker perturbation. Marker-overlap remains more accurate than
DeepSeek-7B LoRA reranking across all tested settings, although the gap narrows
as dropout and distractor noise increase.

Table 1. Main benchmark, robustness, and matrix-derived validation results.

| Split | Method | n | Accuracy | Macro F1 | Raw CL Accuracy | Mapped CL Accuracy | ECE | Mean Runtime (s) |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Label-overlap | Marker-overlap | 178 | 0.9944 | 0.9924 | 0.9941 | 0.9941 | 0.4530 | 0.0002 |
| Label-overlap | Prompt-only DeepSeek | 178 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.8740 | 1.7248 |
| Label-overlap | Prompt-only Qwen2.5-7B | 178 | 0.0449 | 0.0352 | 0.0000 | 0.0471 | 0.8282 | 1.8137 |
| Label-overlap | DeepSeek-7B LoRA | 178 | 0.3652 | 0.2844 | 0.0176 | 0.3824 | 0.5348 | 1.3212 |
| Label-overlap | DeepSeek-7B LoRA rerank | 178 | 0.8876 | 0.8571 | 0.7882 | 0.8941 | 0.5418 | 1.6256 |
| Label-overlap perturbed | Marker-overlap | 178 | 0.9438 | 0.9276 | 0.9412 | 0.9412 | 0.7157 | 0.0002 |
| Label-overlap perturbed | DeepSeek-7B LoRA rerank | 178 | 0.8652 | 0.8248 | 0.7647 | 0.8706 | 0.7492 | 1.5667 |
| Label-overlap perturbed drop75/noise5 | Marker-overlap | 178 | 0.7697 | 0.7238 | 0.7647 | 0.7647 | 0.6505 | 0.0001 |
| Label-overlap perturbed drop75/noise5 | DeepSeek-7B LoRA rerank | 178 | 0.6910 | 0.6314 | 0.5941 | 0.6765 | 0.6290 | 1.5486 |
| Label-overlap perturbed drop90/noise8 | Marker-overlap | 178 | 0.6798 | 0.6324 | 0.6765 | 0.6765 | 0.6049 | 0.0003 |
| Label-overlap perturbed drop90/noise8 | DeepSeek-7B LoRA rerank | 178 | 0.6461 | 0.5943 | 0.5471 | 0.6529 | 0.6052 | 1.5439 |
| Label-held-out | Marker-overlap | 92 | 0.9891 | 0.9938 | 0.9881 | 0.9881 | 0.4785 | 0.0002 |
| PBMC3k matrix-derived | Marker-overlap | 8 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 0.0000 | 0.0001 |
| PBMC3k matrix-derived | DeepSeek-7B LoRA rerank | 8 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 0.0000 | 1.8642 |
| PBMC3k matrix-derived | SingleR (HPCA) | 8 | 0.0000 | 0.0000 | NA | NA | 0.2809 | NA |
| Baron pancreas matrix-derived | Marker-overlap | 14 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 0.0000 | 0.0001 |
| Baron pancreas matrix-derived | DeepSeek-7B LoRA rerank | 14 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 0.0000 | 1.9408 |
| Baron pancreas matrix-derived | SingleR (HPCA) | 14 | 0.0714 | 0.0714 | NA | NA | 0.0923 | NA |
| Zeisel brain matrix-derived | Marker-overlap | 12 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 0.0000 | 0.0003 |
| Zeisel brain matrix-derived | DeepSeek-7B LoRA rerank | 12 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 0.0000 | 2.0672 |
| Zeisel brain matrix-derived | SingleR (MouseRNAseq) | 12 | 0.3333 | 0.2639 | NA | NA | 0.3626 | NA |

Paired statistical tests supported the point-estimate comparisons. On the
clean label-overlap split, Marker-overlap exceeded LoRA reranking by 0.1067
accuracy points (95% paired bootstrap CI 0.0618 to 0.1517; exact McNemar
p < 0.0001). LoRA reranking exceeded open-ended LoRA by 0.5225 accuracy points
(95% CI 0.4382 to 0.5955; p < 0.0001). Marker-overlap also significantly
outperformed LoRA reranking under drop50/noise3 and drop75/noise5
perturbations, but the drop90/noise8 comparison was no longer significant by
McNemar test.

Table 2. Paired statistical comparisons between Marker-overlap, open-ended
LoRA, and candidate-constrained LoRA reranking.

| Comparison | Method A | Method B | n | Accuracy A | Accuracy B | Delta A-B (95% CI) | Macro-F1 Delta (95% CI) | McNemar p |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Label-overlap | Marker-overlap | DeepSeek-7B LoRA rerank | 178 | 0.9944 | 0.8876 | 0.1067 (0.0618, 0.1517) | 0.1352 (0.0840, 0.1683) | <0.0001 |
| Label-overlap | DeepSeek-7B LoRA rerank | DeepSeek-7B LoRA open-ended | 178 | 0.8876 | 0.3652 | 0.5225 (0.4382, 0.5955) | 0.5728 (0.4918, 0.6263) | <0.0001 |
| drop50/noise3 | Marker-overlap | DeepSeek-7B LoRA rerank | 178 | 0.9438 | 0.8652 | 0.0787 (0.0281, 0.1292) | 0.1029 (0.0546, 0.1435) | 0.0043 |
| drop75/noise5 | Marker-overlap | DeepSeek-7B LoRA rerank | 178 | 0.7697 | 0.6910 | 0.0787 (0.0225, 0.1236) | 0.0924 (0.0423, 0.1301) | 0.0066 |
| drop90/noise8 | Marker-overlap | DeepSeek-7B LoRA rerank | 178 | 0.6798 | 0.6461 | 0.0337 (-0.0112, 0.0730) | 0.0381 (-0.0012, 0.0787) | 0.2101 |

Table 3. Candidate-retrieval diagnostics under synthetic marker perturbation.

| Noise Setting | Top-1 Candidate Accuracy | Oracle Top-5 Accuracy | LoRA Rerank Accuracy | Reranker Fixed Top-1 | Reranker Harmed Top-1 |
| --- | ---: | ---: | ---: | ---: | ---: |
| drop50/noise3 | 0.9494 | 0.9944 | 0.8652 | 3 | 18 |
| drop75/noise5 | 0.7753 | 0.9888 | 0.6910 | 4 | 19 |
| drop90/noise8 | 0.6798 | 0.9663 | 0.6461 | 5 | 11 |

The high Marker-overlap baseline indicates that PanglaoDB marker records are
internally consistent and that future LLM comparisons must demonstrate value
beyond simple marker-set matching, such as robustness to noisy extracted
markers, better rationale quality, ontology normalization, and transfer to
matrix-derived cluster markers.

Error analysis showed 65 correct and 113 incorrect LoRA predictions, with no
blank predictions and no missing confidence scores. The model generated CL IDs
for 162 of 178 predictions, but most generated ontology IDs were incorrect.
The label-to-ontology post-processing step mapped 172 predictions, left 6
labels unmapped, and increased CL accuracy from 0.0176 to 0.3824.
Common confusions included biologically adjacent labels such as beta cells
versus gamma (PP) cells, glycinergic neurons versus glutaminergic neurons, and
T cytotoxic cells versus T cells. This suggests that open-ended label and CL ID
generation is not sufficient for this benchmark. Subsequent experiments should
test constrained prediction over a candidate cell-type vocabulary, retrieval
from marker evidence, and post-hoc mapping of predicted labels to curated Cell
Ontology IDs.

![Figure 2. Highest-count off-diagonal DeepSeek-7B LoRA rerank confusions.](../outputs/deepseek_lora_rerank_top_confusions.svg)

Figure 2. Off-diagonal true-versus-predicted label pairs for DeepSeek-7B LoRA
reranking on the PanglaoDB label-overlap test set. Because reranking made 20
errors over 178 examples and each confusion pair occurred once, the figure is a
compact error inventory rather than a dense high-frequency heatmap. The full
confusion matrix is provided in `outputs/deepseek_lora_rerank_confusion_matrix.csv`.

Off-the-shelf SingleR baselines were added for the matrix-derived validation datasets
using celldex HPCA for the human PBMC3k and Baron pancreas datasets and celldex
MouseRNAseq for the Zeisel mouse brain dataset. These references returned labels
that were often broader or differently named than the validation labels, and the
current wrapper does not yet map SingleR predictions to Cell Ontology IDs or to
broader harmonized label groups.
Consequently, SingleR is reported as a reference-label comparator with CL
accuracy marked as not assessed rather than as an ontology-harmonized baseline.
These exact-label SingleR scores should therefore be interpreted as evidence
that label harmonization is still needed, not as evidence that SingleR performs
poorly under an optimized reference-mapping setup. scType and optionally an
additional Llama-family prompt baseline remain pending before making broad
claims about LLM fine-tuning versus existing annotation workflows.

## 9. Discussion

The prompt-only experiments showed that generic instruction-following LLMs are
unreliable standalone annotators for this benchmark. Prompt-only DeepSeek failed
to recover any exact gold labels, and prompt-only Qwen recovered only 8 of 178.
DeepSeek-7B LoRA fine-tuning improved substantially over these prompt-only
baselines, showing that supervised adaptation changed model behavior in the
intended direction. However, LoRA still did not improve label or ontology
accuracy over the transparent Marker-overlap baseline. This negative result is
scientifically useful: it shows that supervised open-ended generation can learn
the output format and reduce language-model loss without learning a sufficiently
reliable decision rule for exact cell-type annotation across many fine-grained
labels. The constrained reranking experiment partially supports this direction:
the LLM became much stronger when forced to select from evidence-backed
candidates, but it still harmed a near-perfect Marker-overlap baseline on
curated PanglaoDB examples. The moderate synthetic noise stress test led to the
same conclusion: Marker-overlap degraded, but remained stronger than the LLM
reranker. The candidate audit clarifies this result: Marker-overlap continued
to retrieve the gold label among the top candidates in nearly all noisy
examples, whereas the LLM sometimes overrode a correct top candidate. Even under
severe synthetic noise, the gap narrowed but did not reverse. The most promising
next use of the LLM is therefore not replacing Marker-overlap on curated marker
tables, but explaining candidate labels, calibrating uncertainty, and handling
genuinely matrix-derived marker lists where noise, dropout, and batch effects
may be more realistic than synthetic marker perturbation.

The near-perfect Marker-overlap result is itself an important constraint on the
claim. On curated marker-record benchmarks, a transparent overlap method is
sufficient for raw top-1 classification, so the scientific motivation for an
LLM cannot be higher accuracy on this benchmark alone. Instead, the plausible
roles for LLMs are complementary: generating concise rationales that make
candidate annotations auditable, estimating uncertainty when marker evidence is
ambiguous or conflicting, normalizing free-text labels to ontology terms,
interpreting noisy marker lists extracted from real matrices, and incorporating
literature-aware biological context that is not captured by exact marker-set
overlap. The constrained reranking results support this narrower role: LLMs are
more useful when anchored to evidence-backed candidates than when asked to
generate labels and ontology IDs open-endedly.

The method should not replace expert curation. Instead, it should serve as an
auditable annotation assistant that accelerates first-pass labeling and flags
uncertain clusters for review.

## 10. Limitations

Potential limitations include training-data leakage from public marker
databases, inconsistent label granularity across sources, hallucinated ontology
IDs, and model sensitivity to marker extraction quality. The benchmark must
therefore separate sources carefully, audit predictions manually, and report
ontology consistency rather than label accuracy alone.

The current result is still limited by its heavy reliance on curated PanglaoDB
marker records. These records are internally consistent and favorable to
Marker-overlap methods. The PBMC3k matrix-derived validation demonstrates that
the workflow runs on extracted cluster markers, but it covers only eight broad
tutorial-labeled PBMC clusters. The Baron pancreas validation adds a second
tissue with 14 endocrine and pancreatic support-cell labels, and Zeisel adds a
third brain validation dataset with 12 label groups, but all three are
relatively easy label-group validations. They demonstrate pipeline
functionality and ontology propagation rather than independent benchmark
superiority. Additional real scRNA-seq datasets may contain more dropout, batch
effects, cluster impurity, rare populations, and marker-ranking noise than the
synthetic perturbations or matrix validation datasets evaluated here. Current
Cell Ontology coverage is 96.49%, meeting
the >=95% target for the current PanglaoDB-derived instruction benchmark. The
remaining unmapped labels are broad or ambiguous PanglaoDB categories that
require dataset-specific interpretation.

## 11. Remaining Work Before Submission

The current results support a careful manuscript, but the following additions
would make the study substantially stronger:

1. Add ontology harmonization for SingleR outputs, and add scType comparisons if
   suitable marker resources are available.
2. Add a more challenging matrix-derived benchmark with cluster impurity,
   fine-grained labels, or independent expert annotation.
3. Optionally add a Llama-family prompt-only or candidate-reranking baseline
   for a broader open-weight LLM comparison.

## 12. Reproducibility

The accompanying codebase provides:

- Marker evidence ingestion from CSV.
- Instruction JSONL generation.
- Train, validation, and test splitting, including label-overlap and
  label-held-out grouped splits.
- LoRA fine-tuning adapter.
- Prompt-only and Marker-overlap annotation.
- AnnData marker extraction and matrix-derived marker benchmark preparation.
- A SingleR cluster-baseline wrapper for `.h5ad` matrices.
- Ontology-aware evaluation.
- Preflight checks for split leakage, CL coverage, dependency versions, token
  lengths, and GPU availability.
- Experiment summary generation for manuscript-ready JSON and Markdown tables.
- Supplementary label-support tables and LoRA rerank confusion artifacts.

All random dataset augmentations use explicit seeds. Heavy dependencies are
optional so the core benchmark remains inspectable and testable.

## 13. Conclusion

DeepSeekCell-FT evaluates fine-tuned and candidate-constrained LLM workflows
for ontology-grounded cell type annotation from marker genes. The current
results do not support the claim that fine-tuned DeepSeek improves annotation
over a transparent Marker-overlap baseline. Instead, they show a more specific
and useful pattern: prompt-only LLMs are very weak standalone annotators,
open-ended LoRA generation improves over prompt-only DeepSeek but remains
unreliable for exact labels and Cell Ontology IDs, and candidate-constrained
reranking substantially improves LLM usefulness but still trails Marker-overlap
selection on this curated benchmark. The strongest current conclusion is
therefore that LLMs are better positioned as auditable assistants for candidate
evaluation, rationale generation, uncertainty review, and matrix-derived marker
interpretation than as standalone open-ended cell type annotators.

## Availability of Data and Materials

The code, configuration files, benchmark scripts, generated prediction files,
summary tables, supplementary label-support table, and figure-generation
scripts are available in the accompanying DeepSeekCell-FT repository and
archived on Zenodo at doi:10.5281/zenodo.20837447. Public input resources are
available from PanglaoDB, Cell Ontology, 10x Genomics PBMC3k, Scanpy tutorial
data, and UCSC Cell Browser as cited in the References.

## Competing Interests

The author declares no competing interests. This statement should be confirmed
for all final manuscript authors before submission.

## Funding

No external funding is declared for the current manuscript draft. This section
should be updated if compute credits, institutional support, or grant funding
are reported in the final submission.

## Authors' Contributions

MK designed the study, implemented the benchmark workflow, ran the experiments,
analyzed the results, and drafted the manuscript. This section should be
updated to reflect the final author list and journal contribution taxonomy.

## Acknowledgements

The author thanks the developers and maintainers of the public single-cell,
ontology, and open-source model resources used in this study. This section
should be expanded if additional collaborators or compute providers are
acknowledged in the final submission.

## References

1. Aran D, Looney AP, Liu L, Wu E, Fong V, Hsu A, Chak S, Naikawadi RP,
   Wolters PJ, Abate AR, Butte AJ, Bhattacharya M. Reference-based analysis of
   lung single-cell sequencing reveals a transitional profibrotic macrophage.
   Nat Immunol. 2019;20(2):163-172. doi:10.1038/s41590-018-0276-y.
2. Ianevski A, Giri AK, Aittokallio T. Fully-automated and ultra-fast
   cell-type identification using specific marker combinations from single-cell
   transcriptomic data. Nat Commun. 2022;13:1246.
   doi:10.1038/s41467-022-28803-w.
3. Zhang X, Lan Y, Xu J, Quan F, Zhao E, Deng C, Luo T, Xu L, Liao G, Yan M,
   Ping Y, Li F, Shi A, Bai J, Zhao T, Li X, Xiao Y. CellMarker: a manually
   curated resource of cell markers in human and mouse. Nucleic Acids Res.
   2019;47(D1):D721-D728. doi:10.1093/nar/gky900.
4. Franzen O, Gan LM, Bjorkegren JLM. PanglaoDB: a web server for exploration
   of mouse and human single-cell RNA sequencing data. Database (Oxford).
   2019;2019:baz046. doi:10.1093/database/baz046.
5. Diehl AD, Meehan TF, Bradford YM, Brush MH, Dahdul WM, Dougall DS, He Y,
   Osumi-Sutherland D, Ruttenberg A, Sarntivijai S, Van Slyke CE, Vasilevsky
   NA, Haendel MA, Blake JA, Mungall CJ. The Cell Ontology 2016: enhanced
   content, modularization, and ontology interoperability. J Biomed Semantics.
   2016;7:44. doi:10.1186/s13326-016-0088-7.
6. Regev A, Teichmann SA, Lander ES, Amit I, Benoist C, Birney E, Bodenmiller
   B, Campbell P, Carninci P, Clatworthy M, Clevers H, Deplancke B, Dunham I,
   Eberwine J, Eils R, Enard W, Farmer A, Fugger L, Gottgens B, Hacohen N,
   Haniffa M, Hemberg M, Kim S, Klenerman P, Kriegstein A, Lein E, Linnarsson
   S, Lundberg E, Lundeberg J, Majumder P, Marioni JC, Merad M, Mhlanga MM,
   Nawijn MC, Netea MG, Nolan GP, Pe'er D, Phillipakis A, Ponting CP, Quake SR,
   Reik W, Rozenblatt-Rosen O, Sanes JR, Satija R, Schumacher TN, Shalek AK,
   Shapiro E, Sharma P, Shin JW, Stegle O, Stratton MR, Stubbington MJT, Theis
   FJ, Uhlen M, van Oudenaarden A, Wagner A, Watt FM, Weissman JS, Wold B,
   Xavier RJ, Yosef N; Human Cell Atlas Meeting Participants. The Human Cell
   Atlas. eLife. 2017;6:e27041. doi:10.7554/eLife.27041.
7. Wolf FA, Angerer P, Theis FJ. SCANPY: large-scale single-cell gene
   expression data analysis. Genome Biol. 2018;19:15.
   doi:10.1186/s13059-017-1382-0.
8. 10x Genomics. 3k PBMCs from a Healthy Donor. 10x Genomics single-cell gene
   expression dataset. 2016. Available from:
   https://www.10xgenomics.com/datasets/3-k-pbm-cs-from-a-healthy-donor-1-standard-1-1-0.
9. Baron M, Veres A, Wolock SL, Faust AL, Gaujoux R, Vetere A, Ryu JH, Wagner
   BK, Shen-Orr SS, Klein AM, Melton DA, Yanai I. A single-cell transcriptomic
   map of the human and mouse pancreas reveals inter- and intra-cell population
   structure. Cell Syst. 2016;3(4):346-360.e4.
   doi:10.1016/j.cels.2016.08.011.
10. Zeisel A, Munoz-Manchado AB, Codeluppi S, Lonnerberg P, La Manno G, Jureus
    A, Marques S, Munguba H, He L, Betsholtz C, Rolny C, Castelo-Branco G,
    Hjerling-Leffler J, Linnarsson S. Cell types in the mouse cortex and
    hippocampus revealed by single-cell RNA-seq. Science.
    2015;347(6226):1138-1142. doi:10.1126/science.aaa1934.
11. DeepSeek-AI. DeepSeek LLM: scaling open-source language models with
    longtermism. arXiv:2401.02954. 2024. doi:10.48550/arXiv.2401.02954.
12. Grattafiori A, Dubey A, Jauhri A, Pandey A, Kadian A, Al-Dahle A, et al.
    The Llama 3 Herd of Models. arXiv:2407.21783. 2024.
    doi:10.48550/arXiv.2407.21783.
13. Qwen Team. Qwen2.5 Technical Report. arXiv:2412.15115. 2025.
    doi:10.48550/arXiv.2412.15115.
