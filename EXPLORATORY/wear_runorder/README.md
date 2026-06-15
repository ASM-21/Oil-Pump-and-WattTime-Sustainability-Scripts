# wear_runorder

**Question:** Does energy drift systematically with run order within an operation, as a signal of tool wear?

**Status:** ready to run (set CNC_DATA_DIR first; also needs scipy and statsmodels)

## Plan

Per operation: OLS regression of energy on run index, plus Spearman rank correlation.
Benjamini-Hochberg FDR correction at 0.10 across all operations. Groups results by
operation category to test whether high-CV categories show more trending.

This project is a "limitations section strengthener" -- a null result (no significant
trend) is a valid and likely finding that clarifies what drives the high-CV operations.

## How to run

```
pip install scipy statsmodels   # if not already installed
export CNC_DATA_DIR=/path/to/your/Al6061_csv_folder
python EXPLORATORY/wear_runorder/run.py
```

## Effort box

**First real result:** per-operation trend table (slope %/run, CI, p, q) and the
grouped figure. A null result (q > 0.10 for all operations) is the expected finding.

## Caveats to watch

The adapter assigns run order by part number (run_id), not by machining timestamp,
because per-operation timestamps are not available from the existing data loader.
If parts were machined out of numerical order, the run-index proxy is unreliable
and this analysis should be flagged as exploratory only.

## Dependencies

- scipy
- statsmodels
