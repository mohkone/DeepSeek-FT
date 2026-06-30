#!/usr/bin/env bash
set -euo pipefail

check_r_packages() {
  Rscript -e '
packages <- c("jsonlite", "Matrix", "openxlsx", "HGNChelper", "scales")
missing <- packages[!vapply(packages, requireNamespace, logical(1), quietly = TRUE)]
if (length(missing)) {
  stop(sprintf("missing R packages: %s", paste(missing, collapse = ", ")), call. = FALSE)
}
cat("Official scType R stack is ready\n")
' >/tmp/deepseekcell_sctype_check.log 2>&1
}

if command -v Rscript >/dev/null 2>&1 && check_r_packages; then
  cat /tmp/deepseekcell_sctype_check.log
  exit 0
fi

if command -v mamba >/dev/null 2>&1; then
  solver=mamba
elif command -v conda >/dev/null 2>&1; then
  solver=conda
else
  echo "Neither Rscript nor conda/mamba was found. Install R and scType dependencies manually." >&2
  exit 1
fi

install_args=(install -y -c conda-forge -c bioconda)
if [[ "$solver" == "conda" ]]; then
  install_args+=(--solver classic)
fi

if ! "$solver" "${install_args[@]}" \
  r-base \
  r-jsonlite \
  r-matrix \
  r-openxlsx \
  r-hgnchelper \
  r-scales; then
  echo "Conda install failed; trying CRAN installation for scType R dependencies." >&2
  "$solver" "${install_args[@]}" \
    r-base \
    r-jsonlite \
    r-matrix \
    r-openxlsx \
    r-scales
  Rscript -e 'install.packages(c("jsonlite", "openxlsx", "HGNChelper", "scales"), repos = "https://cloud.r-project.org")'
fi

check_r_packages
cat /tmp/deepseekcell_sctype_check.log
