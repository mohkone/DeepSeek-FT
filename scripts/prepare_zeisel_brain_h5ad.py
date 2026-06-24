"""Prepare a Zeisel 2015 mouse brain AnnData file from UCSC Cell Browser data."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from urllib.request import Request, urlopen

import anndata as ad
import pandas as pd


EXPR_URL = "https://cells.ucsc.edu/zeisel2015/exprMatrix.tsv.gz"
META_URL = "https://cells.ucsc.edu/zeisel2015/meta.tsv"
DATASET_URL = "https://cells.ucsc.edu/zeisel2015/dataset.json"


def _download(url: str, output: Path, force: bool = False) -> None:
    if output.exists() and not force:
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(request, timeout=120) as response, output.open("wb") as handle:
        shutil.copyfileobj(response, handle)


def _resolve_label(level1: str, level2: str) -> tuple[str, str] | None:
    if level1 == "interneurons":
        return "Interneurons", "CL:0000099"
    if level1 == "pyramidal SS":
        return "Pyramidal SS cells", "CL:0000598"
    if level1 == "pyramidal CA1":
        return "Pyramidal CA1 cells", "CL:0000598"
    if level1 == "oligodendrocytes":
        return "Oligodendrocytes", "CL:0000128"
    if level1 == "microglia":
        if level2.startswith("Pvm"):
            return "Perivascular macrophages", "CL:0000881"
        return "Microglia", "CL:0000129"
    if level1 == "endothelial-mural":
        if level2.startswith("Vend"):
            return "Endothelial cells", "CL:0000115"
        if level2 == "Vsmc":
            return "Vascular smooth muscle cells", "CL:0000359"
        if level2 == "Peric":
            return "Pericytes", "CL:0000669"
        return None
    if level1 == "astrocytes-ependymal":
        if level2.startswith("Astro"):
            return "Astrocytes", "CL:0000127"
        if level2 == "Epend":
            return "Ependymal cells", "CL:0000065"
        if level2 == "Choroid":
            return "Choroid plexus cells", "CL:0000706"
        return None
    return None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--expression",
        type=Path,
        default=Path("data/matrix/zeisel2015_exprMatrix.tsv.gz"),
        help="Cached UCSC Cell Browser expression matrix.",
    )
    parser.add_argument(
        "--metadata",
        type=Path,
        default=Path("data/matrix/zeisel2015_meta.tsv"),
        help="Cached UCSC Cell Browser metadata table.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/matrix/zeisel_brain_labeled.h5ad"),
    )
    parser.add_argument("--label-key", default="cell_type")
    parser.add_argument("--ontology-key", default="cell_ontology_id")
    parser.add_argument("--tissue-key", default="tissue_context")
    parser.add_argument("--tissue", default="Brain")
    parser.add_argument("--min-cells", type=int, default=10)
    parser.add_argument("--force-download", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    _download(EXPR_URL, args.expression, force=args.force_download)
    _download(META_URL, args.metadata, force=args.force_download)

    meta = pd.read_csv(args.metadata, sep="\t", index_col=0)
    resolved = meta.apply(
        lambda row: _resolve_label(str(row["level1class"]), str(row["level2class"])),
        axis=1,
    )
    keep_mask = resolved.notna()
    labels = [item[0] for item in resolved[keep_mask]]
    cl_ids = [item[1] for item in resolved[keep_mask]]

    labeled_meta = meta.loc[keep_mask].copy()
    labeled_meta[args.label_key] = labels
    labeled_meta[args.ontology_key] = cl_ids
    label_counts = labeled_meta[args.label_key].value_counts()
    retained_labels = set(label_counts[label_counts >= args.min_cells].index)
    labeled_meta = labeled_meta[labeled_meta[args.label_key].isin(retained_labels)].copy()
    labeled_meta[args.tissue_key] = args.tissue

    expr = pd.read_csv(args.expression, sep="\t", index_col=0, compression="gzip")
    cells = [cell for cell in labeled_meta.index if cell in expr.columns]
    if not cells:
        raise SystemExit("No overlapping cells between Zeisel expression and metadata tables")

    missing_cells = sorted(set(labeled_meta.index) - set(cells))
    labeled_meta = labeled_meta.loc[cells].copy()
    expr = expr.loc[:, cells]

    adata = ad.AnnData(
        X=expr.T.astype("float32").to_numpy(),
        obs=labeled_meta,
        var=pd.DataFrame(index=expr.index.astype(str)),
    )
    adata.var_names_make_unique()
    adata.uns["deepseekcell_ft_source"] = {
        "dataset": "Zeisel et al. 2015 mouse cortex and hippocampus",
        "ucsc_dataset": "zeisel2015",
        "expression_url": EXPR_URL,
        "metadata_url": META_URL,
        "dataset_url": DATASET_URL,
    }
    adata.uns["deepseekcell_ft_zeisel_label_map_json"] = json.dumps(
        {
            "interneurons": ["Interneurons", "CL:0000099"],
            "pyramidal SS": ["Pyramidal SS cells", "CL:0000598"],
            "pyramidal CA1": ["Pyramidal CA1 cells", "CL:0000598"],
            "oligodendrocytes": ["Oligodendrocytes", "CL:0000128"],
            "Mgl*": ["Microglia", "CL:0000129"],
            "Pvm*": ["Perivascular macrophages", "CL:0000881"],
            "Vend*": ["Endothelial cells", "CL:0000115"],
            "Vsmc": ["Vascular smooth muscle cells", "CL:0000359"],
            "Peric": ["Pericytes", "CL:0000669"],
            "Astro*": ["Astrocytes", "CL:0000127"],
            "Epend": ["Ependymal cells", "CL:0000065"],
            "Choroid": ["Choroid plexus cells", "CL:0000706"],
        },
        sort_keys=True,
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    adata.write_h5ad(args.output)

    summary = {
        "cells": int(adata.n_obs),
        "genes": int(adata.n_vars),
        "label_key": args.label_key,
        "labels": {
            label: int((adata.obs[args.label_key] == label).sum())
            for label in sorted(adata.obs[args.label_key].unique())
        },
        "metadata": str(args.metadata),
        "ontology_key": args.ontology_key,
        "output": str(args.output),
        "skipped_ambiguous_or_unmapped_cells": int((~keep_mask).sum()),
        "missing_expression_cells": len(missing_cells),
        "source": "UCSC Cell Browser zeisel2015",
        "tissue_key": args.tissue_key,
    }
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
