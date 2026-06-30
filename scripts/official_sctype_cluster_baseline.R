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

read_single_column <- function(path) {
  read.delim(path, header = FALSE, stringsAsFactors = FALSE)[[1]]
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
    stop("failed to export H5AD for official scType", call. = FALSE)
  }
}

download_if_missing <- function(url, output, force = FALSE) {
  if (force || !file.exists(output)) {
    dir.create(dirname(output), recursive = TRUE, showWarnings = FALSE)
    download.file(url, output, mode = "wb", quiet = TRUE)
  }
  output
}

prepare_official_sctype_sources <- function(source_dir, force_download = FALSE) {
  source_dir <- normalizePath(source_dir, mustWork = FALSE)
  dir.create(source_dir, recursive = TRUE, showWarnings = FALSE)
  files <- list(
    gene_sets_prepare = file.path(source_dir, "gene_sets_prepare.R"),
    sctype_score = file.path(source_dir, "sctype_score_.R"),
    database = file.path(source_dir, "ScTypeDB_full.xlsx")
  )
  urls <- list(
    gene_sets_prepare = paste0(
      "https://raw.githubusercontent.com/IanevskiAleksandr/sc-type/",
      "master/R/gene_sets_prepare.R"
    ),
    sctype_score = paste0(
      "https://raw.githubusercontent.com/IanevskiAleksandr/sc-type/",
      "master/R/sctype_score_.R"
    ),
    database = paste0(
      "https://github.com/IanevskiAleksandr/sc-type/raw/",
      "master/ScTypeDB_full.xlsx"
    )
  )
  for (name in names(files)) {
    download_if_missing(urls[[name]], files[[name]], force = force_download)
  }
  files
}

cluster_average_matrix <- function(matrix, clusters) {
  cluster_ids <- unique(as.character(clusters))
  averaged <- sapply(
    cluster_ids,
    function(cluster) {
      in_cluster <- clusters == cluster
      Matrix::rowMeans(matrix[, in_cluster, drop = FALSE])
    }
  )
  averaged <- as.matrix(averaged)
  if (is.null(dim(averaged))) {
    averaged <- matrix(averaged, ncol = length(cluster_ids))
  }
  colnames(averaged) <- cluster_ids
  rownames(averaged) <- rownames(matrix)
  averaged
}

normalize_and_scale <- function(matrix) {
  lib_size <- colSums(matrix)
  lib_size[is.na(lib_size) | lib_size <= 0] <- 1
  normalized <- t(t(matrix) / lib_size) * 10000
  logged <- log1p(normalized)
  scaled <- t(scale(t(logged)))
  scaled[is.na(scaled)] <- 0
  scaled[is.infinite(scaled)] <- 0
  scaled
}

confidence_from_scores <- function(scores) {
  scores <- as.numeric(scores)
  scores <- scores[!is.na(scores)]
  if (!length(scores)) {
    return(NULL)
  }
  sorted <- sort(scores, decreasing = TRUE)
  best <- sorted[[1]]
  second <- if (length(sorted) > 1) sorted[[2]] else 0
  denominator <- abs(best) + abs(second) + 1e-9
  max(0, min(1, (best - second) / denominator))
}

args <- parse_args(commandArgs(trailingOnly = TRUE))
adata_path <- require_arg(args, "adata")
cluster_key <- require_arg(args, "cluster-key")
label_key <- require_arg(args, "label-key")
output_path <- require_arg(args, "output")
sctype_tissue <- require_arg(args, "sctype-tissue")
tissue <- if (!is.null(args[["tissue"]])) args[["tissue"]] else sctype_tissue
ontology_key <- if (!is.null(args[["ontology-key"]])) args[["ontology-key"]] else ""
source_dir <- if (!is.null(args[["source-dir"]])) args[["source-dir"]] else file.path("data", "external", "sctype")
export_dir <- if (!is.null(args[["export-dir"]])) args[["export-dir"]] else tempfile("sctype-h5ad-export-")
force_download <- isTRUE(args[["force-download"]])

for (pkg in c("Matrix", "jsonlite", "openxlsx", "HGNChelper", "scales")) {
  if (!requireNamespace(pkg, quietly = TRUE)) {
    stop(sprintf("missing required R package: %s", pkg), call. = FALSE)
  }
}

official_sources <- prepare_official_sctype_sources(source_dir, force_download = force_download)
source(official_sources$gene_sets_prepare, local = TRUE)
source(official_sources$sctype_score, local = TRUE)

dir.create(export_dir, recursive = TRUE, showWarnings = FALSE)
export_h5ad(adata_path, export_dir)

expression <- Matrix::readMM(file.path(export_dir, "matrix.mtx"))
genes <- read_single_column(file.path(export_dir, "genes.tsv"))
cells <- read_single_column(file.path(export_dir, "cells.tsv"))
keep_genes <- !duplicated(genes)
expression <- expression[keep_genes, , drop = FALSE]
rownames(expression) <- genes[keep_genes]
colnames(expression) <- cells

metadata <- read.delim(
  file.path(export_dir, "metadata.tsv"),
  header = TRUE,
  sep = "\t",
  check.names = FALSE,
  stringsAsFactors = FALSE
)
rownames(metadata) <- metadata$cell_id
metadata <- metadata[colnames(expression), , drop = FALSE]
if (!(cluster_key %in% colnames(metadata))) {
  stop(sprintf("cluster key not found in metadata: %s", cluster_key), call. = FALSE)
}
if (!(label_key %in% colnames(metadata))) {
  stop(sprintf("label key not found in metadata: %s", label_key), call. = FALSE)
}
if (nzchar(ontology_key) && !(ontology_key %in% colnames(metadata))) {
  stop(sprintf("ontology key not found in metadata: %s", ontology_key), call. = FALSE)
}

clusters <- as.character(metadata[[cluster_key]])
cluster_matrix <- cluster_average_matrix(expression, clusters)
scaled_matrix <- normalize_and_scale(cluster_matrix)

gene_sets <- gene_sets_prepare(official_sources$database, sctype_tissue)
scores <- sctype_score(
  scRNAseqData = scaled_matrix,
  scaled = TRUE,
  gs = gene_sets$gs_positive,
  gs2 = gene_sets$gs_negative
)
scores <- as.matrix(scores)
if (!nrow(scores) || !ncol(scores)) {
  stop(sprintf("official scType returned no scores for tissue: %s", sctype_tissue), call. = FALSE)
}

dir.create(dirname(output_path), recursive = TRUE, showWarnings = FALSE)
con <- file(output_path, open = "wt", encoding = "UTF-8")
on.exit(close(con), add = TRUE)

for (cluster in colnames(cluster_matrix)) {
  in_cluster <- clusters == cluster
  score_values <- as.numeric(scores[, cluster])
  names(score_values) <- rownames(scores)
  best_index <- which.max(score_values)
  best_label <- names(score_values)[[best_index]]
  best_score <- score_values[[best_index]]
  confidence <- confidence_from_scores(score_values)
  true_label <- majority_value(metadata[[label_key]][in_cluster])
  true_cl_id <- NULL
  if (nzchar(ontology_key)) {
    true_cl_id <- majority_value(metadata[[ontology_key]][in_cluster])
    if (is.na(true_cl_id) || !nzchar(true_cl_id)) {
      true_cl_id <- NULL
    }
  }
  record <- list(
    tissue = tissue,
    cluster = cluster,
    markers = list(),
    y_true = true_label,
    y_pred = best_label,
    true_cl_id = true_cl_id,
    pred_cl_id = NULL,
    confidence = confidence,
    runtime_seconds = NULL,
    cost_usd = NULL,
    reasoning = sprintf(
      "Official scType prediction for tissue '%s' using cluster-averaged expression.",
      sctype_tissue
    ),
    raw_response = sprintf(
      "official scType score: %.6f; source: IanevskiAleksandr/sc-type",
      best_score
    ),
    method = "scType"
  )
  writeLines(jsonlite::toJSON(record, auto_unbox = TRUE, null = "null"), con)
}

message(sprintf("Wrote %d official scType cluster predictions to %s", ncol(cluster_matrix), output_path))
