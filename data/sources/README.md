# Marker Data Sources

This folder is for notes about external marker databases used to build the
training corpus. Keep downloaded source files under `data/raw/` or another
local path outside version control when they are large.

Useful starting points:

- CellMarker 2.0: https://www.bio-bigdata.center/
- CellMarker 2.0 paper: https://academic.oup.com/nar/article/51/D1/D870/6775381
- PanglaoDB: https://panglaodb.se/
- PanglaoDB GitHub metadata: https://github.com/oscar-franzen/PanglaoDB
- Cell Ontology: https://obofoundry.org/ontology/cl.html

## Downloading Cell Ontology

```powershell
python -m deepseekcell_ft.cli download-cell-ontology `
  --output data/raw/cl.obo
python -m deepseekcell_ft.cli build-ontology-map `
  --input data/raw/cl.obo `
  --output data/raw/cell_ontology_labels.csv `
  --ambiguous-output data/raw/cell_ontology_labels.ambiguous.csv
```

After automated mapping, create a manual review template for unresolved labels:

```powershell
python -m deepseekcell_ft.cli propose-ontology-curation `
  --unmapped outputs/panglaodb_unmapped_cl.csv `
  --ontology-map data/raw/cell_ontology_labels.csv `
  --output outputs/panglaodb_cl_curation_template.csv
python -m deepseekcell_ft.cli auto-accept-ontology-curation `
  --curation outputs/panglaodb_cl_curation_template.csv `
  --output outputs/panglaodb_cl_curation_autoaccepted.csv
python -m deepseekcell_ft.cli accept-ontology-suggestion `
  --curation outputs/panglaodb_cl_curation_template.csv `
  --output outputs/panglaodb_cl_curation_reviewed.csv `
  --cell-type "Bergmann glia" `
  --rank 1
python -m deepseekcell_ft.cli accept-ontology-decisions `
  --curation outputs/panglaodb_cl_curation_template.csv `
  --decisions data/curation/panglaodb_cl_decisions.example.csv `
  --output outputs/panglaodb_cl_curation_reviewed.csv
python -m deepseekcell_ft.cli prioritize-ontology-curation `
  --curation outputs/panglaodb_cl_curation_reviewed.csv `
  --split-dir data/processed/panglaodb_cl_curated_grouped_splits `
  --output outputs/panglaodb_cl_curation_priority.csv
```

## Downloading PanglaoDB

```powershell
python -m deepseekcell_ft.cli download-panglaodb-markers `
  --output data/raw/panglaodb_markers.tsv
python -m deepseekcell_ft.cli normalize-markers `
  --input data/raw/panglaodb_markers.tsv `
  --output data/raw/panglaodb.normalized.csv `
  --source PanglaoDB `
  --species Human `
  --min-markers 2
```

The repeatable full workflow is available as:

```powershell
.\scripts\run_panglaodb_cl_pipeline.ps1
```

## Normalizing One-Gene-Per-Row Tables

Many marker databases use one marker gene per row. Convert them into the
project schema like this:

```powershell
$env:PYTHONPATH="src"
python -m deepseekcell_ft.cli normalize-markers `
  --input data/raw/cellmarker_raw.example.csv `
  --output data/raw/cellmarker.normalized.example.csv `
  --source CellMarker `
  --species Human `
  --tissue-column tissueType `
  --cell-type-column cellName `
  --marker-column geneSymbol `
  --cl-id-column CellOntologyID `
  --species-column speciesType `
  --evidence-column PMID
```

The example file is only a local smoke test. For real experiments, download a
source table and replace the input path, for example `data/raw/cellmarker_raw.csv`.

Then validate:

```powershell
python -m deepseekcell_ft.cli validate-marker-db `
  --input data/raw/cellmarker.normalized.csv
```

## Merging Sources

```powershell
python -m deepseekcell_ft.cli merge-marker-dbs `
  --inputs data/raw/cellmarker.normalized.csv data/raw/panglaodb.normalized.csv `
  --output data/raw/marker_evidence.combined.csv `
  --min-markers 2
```
