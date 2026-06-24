#!/usr/bin/env bash
set -euo pipefail

check_r_packages() {
  Rscript -e '
packages <- c("jsonlite", "Matrix", "celldex", "scrapper", "SingleR", "SummarizedExperiment")
missing <- packages[!vapply(packages, requireNamespace, logical(1), quietly = TRUE)]
if (length(missing)) {
  stop(sprintf("missing R packages: %s", paste(missing, collapse = ", ")), call. = FALSE)
}
cat("SingleR R stack is ready\n")
' >/tmp/deepseekcell_singler_check.log 2>&1
}

if command -v Rscript >/dev/null 2>&1 && check_r_packages; then
  cat /tmp/deepseekcell_singler_check.log
  exit 0
fi

if command -v mamba >/dev/null 2>&1; then
  solver=mamba
elif command -v conda >/dev/null 2>&1; then
  solver=conda
else
  echo "Neither Rscript nor conda/mamba was found. Install R and Bioconductor SingleR manually." >&2
  exit 1
fi

install_args=(install -y -c conda-forge -c bioconda)
if [[ "$solver" == "conda" ]]; then
  install_args+=(--solver classic)
fi

"$solver" "${install_args[@]}" \
  r-base \
  r-jsonlite \
  r-matrix \
  bioconductor-celldex \
  bioconductor-scrapper \
  bioconductor-singler \
  bioconductor-summarizedexperiment

check_r_packages
cat /tmp/deepseekcell_singler_check.log
