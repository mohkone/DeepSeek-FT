"""Create a tutorial-labeled PBMC3k AnnData file for matrix benchmark smoke tests."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


PBMC3K_LOUVAIN_LABELS = {
    "0": ("CD4 T cells", "CL:0000624"),
    "1": ("CD14+ Monocytes", "CL:0001054"),
    "2": ("B cells", "CL:0000236"),
    "3": ("CD8 T cells", "CL:0000625"),
    "4": ("NK cells", "CL:0000623"),
    "5": ("FCGR3A+ Monocytes", "CL:0002396"),
    "6": ("Dendritic cells", "CL:0000451"),
    "7": ("Megakaryocytes", "CL:0000556"),
}

PBMC3K_LABEL_NAMES = {
    label.lower(): (label, cl_id)
    for label, cl_id in PBMC3K_LOUVAIN_LABELS.values()
}


def _resolve_pbmc3k_labels(clusters: list[str]) -> list[tuple[str, str]]:
    resolved = []
    missing = []
    for cluster in clusters:
        if cluster in PBMC3K_LOUVAIN_LABELS:
            resolved.append(PBMC3K_LOUVAIN_LABELS[cluster])
            continue
        label = PBMC3K_LABEL_NAMES.get(cluster.lower())
        if label is None:
            missing.append(cluster)
            continue
        resolved.append(label)
    if missing:
        missing_labels = sorted(set(missing))
        raise SystemExit(
            "PBMC3k cluster labels are not aligned with the tutorial mapping; "
            f"unmapped clusters: {missing_labels}"
        )
    return resolved


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download Scanpy PBMC3k processed data and add tutorial labels."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/matrix/pbmc3k_tutorial_labeled.h5ad"),
    )
    parser.add_argument("--cluster-key", default="louvain")
    parser.add_argument("--label-key", default="cell_type")
    parser.add_argument("--ontology-key", default="cell_ontology_id")
    parser.add_argument("--tissue-key", default="tissue")
    parser.add_argument("--tissue", default="PBMC")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        import scanpy as sc
    except ImportError as exc:
        raise SystemExit(
            "PBMC3k preparation requires Scanpy. Install with: "
            'python -m pip install -e ".[single-cell]"'
        ) from exc

    adata = sc.datasets.pbmc3k_processed()
    if args.cluster_key not in adata.obs:
        raise SystemExit(f"cluster key not found in PBMC3k AnnData: {args.cluster_key}")

    clusters = list(adata.obs[args.cluster_key].astype(str))
    resolved_labels = _resolve_pbmc3k_labels(clusters)

    adata.obs[args.label_key] = [label for label, _ in resolved_labels]
    adata.obs[args.ontology_key] = [cl_id for _, cl_id in resolved_labels]
    adata.obs[args.tissue_key] = args.tissue
    adata.uns["deepseekcell_ft_pbmc3k_label_map_json"] = json.dumps(
        PBMC3K_LOUVAIN_LABELS,
        sort_keys=True,
    )
    adata.uns["deepseekcell_ft_label_source"] = (
        "Scanpy PBMC3k processed tutorial louvain-to-cell-type mapping"
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    adata.write_h5ad(args.output)
    summary = {
        "output": str(args.output),
        "cells": int(adata.n_obs),
        "genes": int(adata.n_vars),
        "cluster_key": args.cluster_key,
        "label_key": args.label_key,
        "ontology_key": args.ontology_key,
        "labels": {
            label: int((adata.obs[args.label_key] == label).sum())
            for label, _ in PBMC3K_LOUVAIN_LABELS.values()
        },
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
