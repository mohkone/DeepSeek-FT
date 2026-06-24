"""Extract cluster marker genes from AnnData files."""

from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path
from typing import Any

from .normalization import normalize_cl_id


def majority_value(values: list[Any]) -> tuple[str | None, float | None]:
    """Return the most common non-empty value and its fraction."""

    usable = [
        str(value)
        for value in values
        if value is not None and str(value).strip() and str(value).lower() != "nan"
    ]
    if not usable:
        return None, None
    label, count = Counter(usable).most_common(1)[0]
    return label, count / len(usable)


def _ranked_names(result: Any, group: str, n_top: int) -> list[str]:
    names = result["names"][group][:n_top]
    return [str(name) for name in names if str(name).strip()]


def extract_ranked_markers(
    adata_path: str | Path,
    groupby: str,
    output_csv: str | Path,
    n_top: int = 25,
    method: str = "wilcoxon",
) -> None:
    """Rank marker genes per cluster from an AnnData file with scanpy."""

    try:
        import scanpy as sc
    except ImportError as exc:
        raise ImportError(
            "Marker extraction requires optional single-cell dependencies. "
            "Install with: python -m pip install -e .[single-cell]"
        ) from exc

    adata = sc.read_h5ad(adata_path)
    if groupby not in adata.obs:
        raise ValueError(f"groupby column not found in adata.obs: {groupby}")

    sc.tl.rank_genes_groups(adata, groupby=groupby, method=method)
    result = adata.uns["rank_genes_groups"]
    groups = list(result["names"].dtype.names or [])

    output_csv = Path(output_csv)
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with output_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["cluster", "rank", "gene", "score", "pval_adj"])
        writer.writeheader()
        for group in groups:
            names = result["names"][group][:n_top]
            scores = result["scores"][group][:n_top]
            if "pvals_adj" in result and group in (result["pvals_adj"].dtype.names or []):
                pvals_adj = result["pvals_adj"][group][:n_top]
            else:
                pvals_adj = [None] * len(names)
            for rank, gene in enumerate(names, start=1):
                writer.writerow(
                    {
                        "cluster": group,
                        "rank": rank,
                        "gene": str(gene),
                        "score": float(scores[rank - 1]),
                        "pval_adj": (
                            float(pvals_adj[rank - 1])
                            if pvals_adj is not None and pvals_adj[rank - 1] is not None
                            else None
                        ),
                    }
                )


def prepare_matrix_marker_benchmark(
    adata_path: str | Path,
    output_csv: str | Path,
    tissue: str,
    groupby: str = "leiden",
    label_key: str | None = None,
    ontology_key: str | None = None,
    n_top: int = 25,
    method: str = "wilcoxon",
    run_clustering: bool = False,
    resolution: float = 1.0,
    normalize: bool = True,
    min_cells: int = 3,
    min_genes: int = 200,
    random_state: int = 0,
) -> dict[str, Any]:
    """Create a standard marker evidence CSV from a clustered AnnData matrix."""

    try:
        import scanpy as sc
    except ImportError as exc:
        raise ImportError(
            "Matrix benchmark preparation requires optional single-cell dependencies. "
            "Install with: python -m pip install -e .[single-cell]"
        ) from exc

    adata_path = Path(adata_path)
    adata = sc.read_h5ad(adata_path)
    adata.var_names_make_unique()

    if normalize:
        if min_genes:
            sc.pp.filter_cells(adata, min_genes=min_genes)
        if min_cells:
            sc.pp.filter_genes(adata, min_cells=min_cells)
        sc.pp.normalize_total(adata, target_sum=1e4)
        sc.pp.log1p(adata)

    if run_clustering or groupby not in adata.obs:
        sc.pp.highly_variable_genes(adata, n_top_genes=min(2000, adata.n_vars))
        sc.pp.pca(adata, n_comps=min(50, max(2, adata.n_vars - 1)))
        sc.pp.neighbors(adata, random_state=random_state)
        sc.tl.leiden(adata, key_added=groupby, resolution=resolution, random_state=random_state)

    if groupby not in adata.obs:
        raise ValueError(f"groupby column not found in adata.obs: {groupby}")
    if label_key and label_key not in adata.obs:
        raise ValueError(f"label_key column not found in adata.obs: {label_key}")
    if ontology_key and ontology_key not in adata.obs:
        raise ValueError(f"ontology_key column not found in adata.obs: {ontology_key}")

    sc.tl.rank_genes_groups(adata, groupby=groupby, method=method)
    result = adata.uns["rank_genes_groups"]
    groups = list(result["names"].dtype.names or [])
    group_series = adata.obs[groupby].astype(str)

    output_rows: list[dict[str, Any]] = []
    for group in groups:
        mask = group_series == str(group)
        n_cells = int(mask.sum())
        markers = _ranked_names(result, group, n_top)
        if label_key:
            cell_type, label_fraction = majority_value(list(adata.obs.loc[mask, label_key]))
        else:
            cell_type, label_fraction = f"cluster {group}", None
        if ontology_key:
            cell_ontology_id, _ = majority_value(list(adata.obs.loc[mask, ontology_key]))
        else:
            cell_ontology_id = None
        output_rows.append(
            {
                "tissue": tissue,
                "cell_type": cell_type or f"cluster {group}",
                "cell_ontology_id": normalize_cl_id(cell_ontology_id),
                "markers": ", ".join(markers),
                "source": f"matrix:{adata_path.name}",
                "evidence": f"Scanpy rank_genes_groups {method}; cluster={group}; n_cells={n_cells}",
                "cluster": group,
                "n_cells": n_cells,
                "majority_label_fraction": (
                    round(label_fraction, 6) if label_fraction is not None else None
                ),
                "groupby": groupby,
                "label_key": label_key,
                "ontology_key": ontology_key,
                "adata": str(adata_path),
            }
        )

    output_csv = Path(output_csv)
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "tissue",
        "cell_type",
        "cell_ontology_id",
        "markers",
        "source",
        "evidence",
        "cluster",
        "n_cells",
        "majority_label_fraction",
        "groupby",
        "label_key",
        "ontology_key",
        "adata",
    ]
    with output_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(output_rows)

    return {
        "input": str(adata_path),
        "output": str(output_csv),
        "records": len(output_rows),
        "cells": int(adata.n_obs),
        "genes": int(adata.n_vars),
        "groupby": groupby,
        "label_key": label_key,
        "ontology_key": ontology_key,
        "records_with_cl_id": sum(bool(row["cell_ontology_id"]) for row in output_rows),
        "mean_markers_per_record": (
            sum(len(row["markers"].split(", ")) if row["markers"] else 0 for row in output_rows)
            / len(output_rows)
            if output_rows
            else 0.0
        ),
        "run_clustering": run_clustering,
        "normalized": normalize,
    }
