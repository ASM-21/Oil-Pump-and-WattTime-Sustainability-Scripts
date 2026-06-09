# Machine Specific Scripts

This folder contains exploratory scripts for machine-level manufacturing energy analysis. The scripts are split between additive-manufacturing traces and CNC machining energy/feature-library work.

## Current status

**Exploratory / data-analysis support.** These scripts appear to be closer to analysis notebooks converted into Python files than polished command-line tools. They are useful for preserving how machine energy values were calculated and plotted, but they need input/output documentation before another researcher can rerun them easily.

## Subfolders

| Folder | Purpose |
| --- | --- |
| `Additive/` | 3D-printer energy analysis and boxplot generation. |
| `CNC/` | CNC program energy analysis, feature-library calculations, UUID/CSV mapping, and figure generation. |

## How this connects to the larger research

Machine-specific energy values can provide the manufacturing-energy side of the sustainability workflow. They can feed:

- feature-level energy libraries for CAD-phase estimation,
- oil-pump process energy values in OpenLCA,
- comparisons between machine operation and grid-emissions timing,
- future case studies where part geometry, machine energy, and electricity emissions are analyzed together.

## Recommended docs to add next

1. A sample input-data dictionary for each machine/export format.
2. A table mapping each script to the figure, table, or calculated value it produced.
3. Notes on units, sampling rate, time zone, and machine/program identifiers.
4. A short explanation of which scripts are reusable and which are historical one-offs.
5. An output convention for plots and cleaned CSV/Excel files.

## Safety and cleanup notes

- Check for local absolute paths before sharing.
- Avoid committing raw proprietary machine logs unless they are approved for release.
- Prefer small anonymized sample inputs for documentation and testing.

