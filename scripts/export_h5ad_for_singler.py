#!/usr/bin/env python
"""Export an H5AD file into simple files that R/SingleR can read without reticulate."""

from __future__ import annotations

import argparse
from pathlib import Path

import anndata as ad
import pandas as pd
from scipy import io, sparse


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adata", required=True, type=Path, help="Input .h5ad file.")
    parser.add_argument("--output-dir", required=True, type=Path, help="Directory for exported files.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    adata = ad.read_h5ad(args.adata)
    matrix = adata.X
    if not sparse.issparse(matrix):
        matrix = sparse.csr_matrix(matrix)

    # SingleR expects genes x cells. AnnData stores cells x genes.
    io.mmwrite(args.output_dir / "matrix.mtx", matrix.T.tocoo())

    pd.Series(adata.var_names.astype(str)).to_csv(
        args.output_dir / "genes.tsv",
        sep="\t",
        index=False,
        header=False,
    )
    pd.Series(adata.obs_names.astype(str)).to_csv(
        args.output_dir / "cells.tsv",
        sep="\t",
        index=False,
        header=False,
    )
    adata.obs.copy().to_csv(
        args.output_dir / "metadata.tsv",
        sep="\t",
        index=True,
        index_label="cell_id",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
