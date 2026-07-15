# Operation-level energy analysis: architecture

A source-agnostic spine for operation-level energy work. Any operation, from
this Brillinger dataset, your IN-MaC UUID results, or FDM runs, becomes one
normalized record keyed by UUID. Analyses run over a store of records
regardless of origin, so you can pose new questions and compare across datasets
and process types on a common footing, with confounds surfaced automatically.

## Layers

```
ingestion adapters            operations.ops_from_brillinger
(dataset-specific)            operations.ops_from_uuid_results   <- your data
        |                     (write more as needed)
        v   OperationRecord
OperationStore                operations.OperationStore
(any mix of sources)
        |
        v
exploratory engine            summarize / energy_share / rank / pareto /
(source-agnostic)             compare / data_quality  (+ register your own)
                              every compare() auto-reports confounds
```

The spine (`operations.py`) has **no dependency** on the Brillinger code. It
takes plain DataFrames/dicts through adapters, so it drops into your repo and
runs on your data with or without this dataset. The Brillinger modules are just
one ingestion adapter.

## Modules

| file | role | depends on |
|---|---|---|
| `config.py` | externalized `DatasetConfig` + per-dataset instances (Brillinger, IN-MaC) | none |
| `brillinger_pipeline.py` | parse Sinumerik NC + per-axis power, energy by operation, sampling-rate sensitivity | numpy, pandas, (ijson) |
| `material_removal.py` | Z-map material removal sim, per-operation volume, SEC | numpy, pandas, brillinger_pipeline, (trimesh) |
| `operations.py` | **the spine**: Operation model, store, exploratory engine, adapters | numpy, pandas |
| `comparison.py` | two-dataset marginal-SEC comparison with confounds (original; superseded by operations.compare) | numpy, pandas |
| `dataset_explorer.py` | manifest, signal diagnostics, cached resilient corpus runner + provenance, corpus characterization | numpy, pandas, the above |
| `signals.py` | per-axis energy decomposition, corpus sampling-rate sweep | numpy, pandas, brillinger_pipeline |
| `nc_features.py` | NC structural metrics (path lengths, tool counts, layering) per program and corpus | numpy, pandas, brillinger_pipeline |
| `geometry.py` | STL characterization (volume, area, bbox, S/V ratio) per part and corpus | numpy, pandas, (trimesh) |
| `features.py` | assemble per-experiment feature table (NC + geometry + energy) and correlate with energy | numpy, pandas |
| `viz.py` | pure plotting (headless), one fig per analysis + dashboard | matplotlib, numpy, pandas |
| `explore_dataset.py` | runnable CLI: full battery -> report + figures | the above |

`comparison.py` is the narrow two-dataset comparator; `operations.py`
generalizes it to any number of sources and any split dimension. Use the spine
for new work; keep `comparison.py` if you want the tight Brillinger-vs-IN-MaC
path.

## Operation contract

One `OperationRecord` per operation. Required to be useful: `uuid`, `source`,
and `energy_j`. Add `volume_mm3` for SEC, and `time_s` + `baseline_w` for
marginal energy. Metadata (`process`, `operation_type`, `machine`, `material`,
`boundary`, `coolant`, `sampling_hz`) drives grouping and confound detection.
Source-specific signals go in `extra` and are preserved.

Derived on access: `marginal_energy_j = energy_j - baseline_w * time_s`,
`sec_total`, `sec_marginal`, and quality flags (`sec_plausible`, `has_volume`,
`marginal_valid`).

### Boundaries are first-class

`boundary` records what the meter saw: `drive_sum` (Brillinger per-axis sum,
no aux/coolant/control) vs `machine_input` (IN-MaC single total meter). The
engine refuses to compare across boundaries on the `total` basis and warns on
the `marginal` basis, because marginal energy removes idle baseline but not
load present only during cutting (e.g. a flood-coolant pump on a total meter).
This is the core methodological guardrail; do not strip it.

## Plugging in your UUID results

```python
import operations as ops
recs = ops.ops_from_uuid_results(
    your_df,
    source="IN-MaC",
    energy_unit="Wh",                      # converted to J
    column_map={"energy_j": "your_energy_col"},   # override detection
    defaults={"machine": "Hurco VMX30Ui", "material": "Al6061-T6",
              "boundary": "machine_input", "coolant": "flood"})
store = ops.OperationStore(recs)
```

Column detection is heuristic; share a header row and the defaults can be
pinned to your exact names. Energy unit handling covers J / Wh / kWh.

## Extending

- New analysis: `fn(store, **kw) -> DataFrame|dict`, then
  `ops.register("name", fn)`. The engine and confound logic are untouched.
- New source: write an adapter that yields `OperationRecord`s. Set `boundary`
  and `coolant` honestly so comparisons stay valid.

## Tests

Each module has a `test_*.py` with synthetic fixtures and known-answer checks
(Z-map volumes validated against closed-form slot/hole geometry; marginal-SEC
arithmetic; confound firing; adapter unit conversion). Run all four; all pass.

## Known limits (carried in module headers)

- Z-map is 3-axis and cannot represent undercuts or vertical-wall side-milling.
- Per-operation volume needs tool diameters and the work-coordinate origin;
  reconcile total simulated removal against stock-minus-STL.
- The cross-machine SEC ratio bundles machine + coolant + alloy; a within-2x
  result does not isolate the machine effect.
- H1 (1 Hz adequacy) depends on whether the meter integrates or point-samples.

## Open data hooks (need real files)

- A sample Brillinger JSON to lock the channel map and counter semantics.
- The tool-list xlsx for real diameters.
- Your IN-MaC per-operation UUID export to populate the store for real.
