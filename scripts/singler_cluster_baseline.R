#!/usr/bin/env Rscript

parse_args <- function(args) {
  parsed <- list()
  i <- 1
  while (i <= length(args)) {
    key <- args[[i]]
    if (!startsWith(key, "--")) {
      stop(sprintf("unexpected argument: %s", key), call. = FALSE)
    }
    name <- substring(key, 3)
    if (i == length(args) || startsWith(args[[i + 1]], "--")) {
      parsed[[name]] <- TRUE
      i <- i + 1
    } else {
      parsed[[name]] <- args[[i + 1]]
      i <- i + 2
    }
  }
  parsed
}

require_arg <- function(args, name) {
  value <- args[[name]]
  if (is.null(value) || identical(value, TRUE) || !nzchar(value)) {
    stop(sprintf("missing required --%s", name), call. = FALSE)
  }
  value
}

majority_value <- function(values) {
  values <- as.character(values)
  values <- values[!is.na(values) & nzchar(values)]
  if (!length(values)) {
    return(NA_character_)
  }
  names(sort(table(values), decreasing = TRUE))[1]
}

load_reference <- function(reference_name) {
  if (!requireNamespace("celldex", quietly = TRUE)) {
    stop("SingleR reference loading requires the Bioconductor package celldex", call. = FALSE)
  }
  switch(
    reference_name,
    hpca = celldex::HumanPrimaryCellAtlasData(),
    blueprint_encode = celldex::BlueprintEncodeData(),
    mouse_rna_seq = celldex::MouseRNAseqData(),
    stop(sprintf("unsupported --reference %s", reference_name), call. = FALSE)
  )
}

export_h5ad <- function(adata_path, export_dir) {
  exporter <- file.path("scripts", "export_h5ad_for_singler.py")
  if (!file.exists(exporter)) {
    stop(sprintf("missing H5AD exporter: %s", exporter), call. = FALSE)
  }
  python <- Sys.getenv("DEEPSEEKCELL_PYTHON", unset = "python")
  status <- system2(
    python,
    c(exporter, "--adata", adata_path, "--output-dir", export_dir),
    stdout = TRUE,
    stderr = TRUE
  )
  exit_status <- attr(status, "status")
  if (!is.null(exit_status) && exit_status != 0) {
    cat(status, sep = "\n")
    stop("failed to export H5AD for SingleR", call. = FALSE)
  }
}

read_single_column <- function(path) {
  read.delim(path, header = FALSE, stringsAsFactors = FALSE)[[1]]
}

args <- parse_args(commandArgs(trailingOnly = TRUE))
adata_path <- require_arg(args, "adata")
cluster_key <- require_arg(args, "cluster-key")
label_key <- require_arg(args, "label-key")
output_path <- require_arg(args, "output")
tissue <- if (!is.null(args[["tissue"]])) args[["tissue"]] else ""
ontology_key <- if (!is.null(args[["ontology-key"]])) args[["ontology-key"]] else ""
reference_name <- if (!is.null(args[["reference"]])) args[["reference"]] else "hpca"
export_dir <- if (!is.null(args[["export-dir"]])) args[["export-dir"]] else tempfile("singler-h5ad-export-")

for (pkg in c("Matrix", "SingleR", "SummarizedExperiment", "jsonlite")) {
  if (!requireNamespace(pkg, quietly = TRUE)) {
    stop(sprintf("missing required R package: %s", pkg), call. = FALSE)
  }
}

dir.create(export_dir, recursive = TRUE, showWarnings = FALSE)
export_h5ad(adata_path, export_dir)

test_matrix <- Matrix::readMM(file.path(export_dir, "matrix.mtx"))
rownames(test_matrix) <- read_single_column(file.path(export_dir, "genes.tsv"))
colnames(test_matrix) <- read_single_column(file.path(export_dir, "cells.tsv"))

metadata <- read.delim(
  file.path(export_dir, "metadata.tsv"),
  header = TRUE,
  sep = "\t",
  check.names = FALSE,
  stringsAsFactors = FALSE
)
rownames(metadata) <- metadata$cell_id
metadata <- metadata[colnames(test_matrix), , drop = FALSE]
if (!(cluster_key %in% colnames(metadata))) {
  stop(sprintf("cluster key not found in colData: %s", cluster_key), call. = FALSE)
}
if (!(label_key %in% colnames(metadata))) {
  stop(sprintf("label key not found in colData: %s", label_key), call. = FALSE)
}
if (nzchar(ontology_key) && !(ontology_key %in% colnames(metadata))) {
  stop(sprintf("ontology key not found in colData: %s", ontology_key), call. = FALSE)
}

ref <- load_reference(reference_name)
clusters <- as.character(metadata[[cluster_key]])
pred <- SingleR::SingleR(
  test = test_matrix,
  ref = ref,
  labels = ref$label.main,
  clusters = clusters
)

dir.create(dirname(output_path), recursive = TRUE, showWarnings = FALSE)
con <- file(output_path, open = "wt", encoding = "UTF-8")
on.exit(close(con), add = TRUE)

for (i in seq_len(nrow(pred))) {
  cluster <- rownames(pred)[[i]]
  in_cluster <- clusters == cluster
  true_label <- majority_value(metadata[[label_key]][in_cluster])
  true_cl_id <- NULL
  if (nzchar(ontology_key)) {
    true_cl_id <- majority_value(metadata[[ontology_key]][in_cluster])
    if (is.na(true_cl_id) || !nzchar(true_cl_id)) {
      true_cl_id <- NULL
    }
  }
  scores <- as.numeric(pred$scores[i, ])
  confidence <- if (length(scores)) max(scores, na.rm = TRUE) else NULL
  record <- list(
    tissue = tissue,
    cluster = cluster,
    markers = list(),
    y_true = true_label,
    y_pred = as.character(pred$labels[[i]]),
    true_cl_id = true_cl_id,
    pred_cl_id = NULL,
    confidence = confidence,
    runtime_seconds = NULL,
    cost_usd = NULL,
    reasoning = sprintf("SingleR cluster-level prediction using %s reference.", reference_name),
    raw_response = NULL,
    method = "SingleR"
  )
  writeLines(jsonlite::toJSON(record, auto_unbox = TRUE, null = "null"), con)
}

message(sprintf("Wrote %d SingleR cluster predictions to %s", nrow(pred), output_path))
