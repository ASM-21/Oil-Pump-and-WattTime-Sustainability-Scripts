# OpenNX Feature Library Draft

This folder contains a Siemens NXOpen prototype for estimating machining energy from CAD/manufacturing features. The workflow extracts features from an open NX part, looks up energy values in a material/feature library, and writes reports.

## Current status

**Prototype / promising future-work bridge.** This area connects CAD geometry to energy estimation and could become a polished demonstration of design-stage sustainability analysis after environment assumptions and validation notes are documented.

## Key files

| File | Role |
| --- | --- |
| `main.py` | NX entry point that orchestrates feature extraction, energy lookup, and report generation. |
| `feature_extractor.py` | NXOpen feature parsing and feature-type handling. |
| `energy_lookup.py` | Loads feature-energy library values and matches extracted features to energy estimates. |
| `report_generator.py` | Exports analysis reports. |
| `build_aluminum_library.py` | Builds or updates the aluminum feature-energy library. |
| `aluminum_expanded.xlsx` | Draft material/feature energy library used by the estimator. |

## Expected workflow

1. Open a part or assembly in Siemens NX.
2. Configure the material-library path and output directory in `main.py`.
3. Run `main.py` through NX Open execution.
4. Review generated JSON/Excel reports.
5. Compare estimated energy against measured CNC/program energy where available.

## Recommended docs to add next

- Siemens NX version and required Python/NXOpen environment details.
- Example output schema for extracted features.
- Explanation of how feature names, dimensions, and energy-library rows are matched.
- Validation notes for supported versus unsupported feature types.
- A small anonymized example report for portfolio/research demonstration.

## Known assumptions to review

- `main.py` currently contains local Windows-style paths that should become configurable before sharing.
- NXOpen scripts typically run inside the NX-managed Python environment rather than a normal terminal.
- The energy library should document units and measurement source for each feature-energy value.

## Validation against measured data (new)

`aluminum_expanded.xlsx` is 100% placeholder data (see
`build_aluminum_library.py`: every row has `source="placeholder"` and an
empty `uuid` column, waiting for real IN-MaC measurements to be dropped in).
That comparison had never been run. `validate_against_measured.py` does a
first, stdlib-only pass: it maps the real per-operation energy already
committed in `../ML Explore/operation_csvs/` onto this library's feature
categories (via the UUID name table in
`../Machine Specific Scripts/CNC/EnergyForFeatureLib.py`) and checks whether
the placeholder ranges are even in the right order of magnitude.

Headline result: `pocket_rectangular` (cavity milling) is measured 12x above
the placeholder table's largest entry — the table's dimensional range doesn't
reach this part's actual roughing volumes. `chamfer` and `face` also read
high, with caveats (per-edge basis, respectively a smaller gap) noted in the
findings. About a third of the part's real operations (wall/profile finishing
passes) have no matching category in the library at all. Run it yourself:

    python3 "validate_against_measured.py"

See `library_validation_findings.md` (full write-up, caveats, and the
category-by-category table) and `library_validation_results.csv` (per-operation
numbers behind it).

