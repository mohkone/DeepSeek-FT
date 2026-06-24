"""Create a Baron-pancreas AnnData file from Scanpy's pancreas tutorial object."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


PANCREAS_URL = "https://www.dropbox.com/s/qj1jlm9w10wmt0u/pancreas.h5ad?dl=1"

BARON_CELLTYPE_LABELS = {
    "acinar": ("Acinar cells", "CL:0000622"),
    "activated_stellate": ("Activated pancreatic stellate cells", "CL:0002410"),
    "alpha": ("Alpha cells", "CL:0004117"),
    "beta": ("Beta cells", "CL:0000169"),
    "delta": ("Delta cells", "CL:0000173"),
    "ductal": ("Ductal cells", "CL:0002079"),
    "endothelial": ("Endothelial cells", "CL:0000115"),
    "epsilon": ("Epsilon cells", "CL:0005019"),
    "gamma": ("Gamma (PP) cells", "CL:0002275"),
    "macrophage": ("Macrophages", "CL:0000235"),
    "mast": ("Mast cells", "CL:0000097"),
    "quiescent_stellate": ("Quiescent pancreatic stellate cells", "CL:0002410"),
    "schwann": ("Schwann cells", "CL:0002573"),
    "t_cell": ("T cells", "CL:0000084"),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Download Scanpy's pancreas tutorial object, filter to the Baron "
            "sample, and add standard cell-type and Cell Ontology columns."
        )
    )
    parser.add_argument(
        "--source-cache",
        type=Path,
        default=Path("data/matrix/pancreas_scanpy_integration.h5ad"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/matrix/baron_pancreas_labeled.h5ad"),
    )
    parser.add_argument("--sample-key", default="sample")
    parser.add_argument("--sample", default="Baron")
    parser.add_argument("--source-label-key", default="celltype")
    parser.add_argument("--label-key", default="cell_type")
    parser.add_argument("--ontology-key", default="cell_ontology_id")
    parser.add_argument("--tissue-key", default="tissue")
    parser.add_argument("--tissue", default="Pancreas")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        import scanpy as sc
    except ImportError as exc:
        raise SystemExit(
            "Baron pancreas preparation requires Scanpy. Install with: "
            'python -m pip install -e ".[single-cell]"'
        ) from exc

    args.source_cache.parent.mkdir(parents=True, exist_ok=True)
    adata = sc.read(args.source_cache, backup_url=PANCREAS_URL)
    if args.sample_key not in adata.obs:
        raise SystemExit(f"sample key not found in AnnData: {args.sample_key}")
    if args.source_label_key not in adata.obs:
        raise SystemExit(f"source label key not found in AnnData: {args.source_label_key}")

    sample_mask = adata.obs[args.sample_key].astype(str) == args.sample
    if not sample_mask.any():
        samples = sorted(set(adata.obs[args.sample_key].astype(str)))
        raise SystemExit(f"sample not found: {args.sample}; available samples: {samples}")

    baron = adata[sample_mask].copy()
    original_labels = list(baron.obs[args.source_label_key].astype(str))
    missing = sorted({label for label in original_labels if label not in BARON_CELLTYPE_LABELS})
    if missing:
        raise SystemExit(
            "Baron pancreas labels are not mapped to Cell Ontology IDs; "
            f"unmapped labels: {missing}"
        )

    resolved = [BARON_CELLTYPE_LABELS[label] for label in original_labels]
    baron.obs["baron_cell_type_original"] = original_labels
    baron.obs[args.label_key] = [label for label, _ in resolved]
    baron.obs[args.ontology_key] = [cl_id for _, cl_id in resolved]
    baron.obs[args.tissue_key] = args.tissue
    baron.uns["deepseekcell_ft_baron_label_map_json"] = json.dumps(
        BARON_CELLTYPE_LABELS,
        sort_keys=True,
    )
    baron.uns["deepseekcell_ft_label_source"] = (
        "Scanpy pancreas tutorial object filtered to sample=Baron"
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    baron.write_h5ad(args.output)
    summary = {
        "output": str(args.output),
        "source_cache": str(args.source_cache),
        "cells": int(baron.n_obs),
        "genes": int(baron.n_vars),
        "sample": args.sample,
        "source_label_key": args.source_label_key,
        "label_key": args.label_key,
        "ontology_key": args.ontology_key,
        "labels": {
            label: int((baron.obs[args.label_key] == label).sum())
            for label, _ in sorted(set(BARON_CELLTYPE_LABELS.values()))
        },
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
