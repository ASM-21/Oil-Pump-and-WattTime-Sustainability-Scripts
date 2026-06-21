"""
WEAR / RUN ORDER -- does energy drift with run order within an operation?

Tests whether tool wear shows up as a systematic energy trend across replicate
runs. If yes, it is an explanatory variable for the high-CV operations. If no,
it is a clean result that strengthens the "variability is by category, not wear"
claim.

Analysis (when data is available):
  - OLS: energy ~ run_index per operation; Spearman r per operation
  - Benjamini-Hochberg FDR correction at 0.10
  - Group by operation category; test whether high-CV categories trend more

Dual-path: OLS slope sign/significance agrees with Spearman sign/significance.

Run from repo root:
    python EXPLORATORY/wear_runorder/run.py

Set CNC_DATA_DIR first -- see EXPLORATORY/shared/adapters.py header.
"""

from __future__ import annotations
import sys
from pathlib import Path
import pandas as pd
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from EXPLORATORY.shared.style import apply_style, save_fig, COLORS
from EXPLORATORY.shared.checks import CheckLog, require, SmokeTestFailure
from EXPLORATORY.shared import adapters

OUT = Path(__file__).parent / "outputs"
OUT.mkdir(exist_ok=True)
log = CheckLog()


def load() -> pd.DataFrame:
    try:
        return adapters.load_operation_energy()
    except (adapters.DataNotInRepo, NotImplementedError) as e:
        _gap = ROOT / "EXPLORATORY" / "_data_gaps.md"
        with _gap.open("a") as f:
            f.write(f"\n## wear_runorder (parked)\n- {e}\n")
        print(f"PARKED: {e}")
        sys.exit(0)


def _assign_run_order(df: pd.DataFrame) -> pd.DataFrame:
    """
    Assign a sequential run index within each (part, program, operation_id) group.

    The existing adapter does not attach timestamps (start/end are NaT), so the
    only available ordering is by run_id (part number). This is a proxy for
    production order within the study period. If the lab ran parts sequentially
    without re-ordering (likely), run_id order is a reasonable wear proxy.
    If parts were run out of order, this analysis is unreliable -- note in findings.
    """
    df = df.copy()
    df = df.sort_values(["part", "program", "operation_id", "run_id"])
    df["run_index"] = df.groupby(["part", "program", "operation_id"]).cumcount()
    return df


def compute(df: pd.DataFrame) -> dict:
    from scipy import stats as scipy_stats

    df = _assign_run_order(df)
    result_rows = []

    # Exclude operations with fewer than 5 runs (too few for trend detection)
    grp = df.groupby(["part", "program", "operation_id", "operation_cat"])
    for (part, program, op_id, op_cat), group in grp:
        if len(group) < 5:
            continue

        x = group["run_index"].to_numpy(dtype=float)
        y = group["energy_wh"].to_numpy(dtype=float)
        n = len(x)
        mean_y = y.mean()

        # OLS slope (energy ~ run_index)
        slope_ols, intercept, r_val, p_ols, _ = scipy_stats.linregress(x, y)
        slope_pct_per_run = slope_ols / mean_y * 100  # % change per run

        # Spearman (non-parametric, no linearity assumption)
        rho, p_spearman = scipy_stats.spearmanr(x, y)

        result_rows.append({
            "part": part, "program": program,
            "operation_id": op_id, "operation_cat": op_cat,
            "n_runs": n, "mean_wh": mean_y,
            "cv_pct": y.std() / mean_y * 100,
            "slope_ols_wh_per_run": slope_ols,
            "slope_pct_per_run": slope_pct_per_run,
            "r_squared": r_val ** 2,
            "p_ols": p_ols,
            "spearman_rho": rho,
            "p_spearman": p_spearman,
        })

    if not result_rows:
        print("No operations had >= 5 runs. Cannot compute trends.")
        return {"trend_df": pd.DataFrame(), "df": df}

    trend_df = pd.DataFrame(result_rows)

    # Benjamini-Hochberg FDR correction on OLS p-values
    from statsmodels.stats.multitest import multipletests
    reject, q_vals, _, _ = multipletests(trend_df["p_ols"].values, alpha=0.10, method="fdr_bh")
    trend_df["q_ols"] = q_vals
    trend_df["significant_fdr10"] = reject

    # Dual-path: for significant operations, OLS slope sign should agree with Spearman sign
    sig = trend_df[trend_df["significant_fdr10"]].copy()
    if not sig.empty:
        sign_agree = (np.sign(sig["slope_ols_wh_per_run"]) == np.sign(sig["spearman_rho"])).all()
        log.cross_check(
            "OLS vs Spearman sign agreement (significant ops)",
            float(sign_agree), 1.0, rel_tol=0.0,
            note="1.0=agree, 0.0=disagree; should be 1.0 for all significant ops"
        )

    result = {
        "trend_df": trend_df,
        "n_significant": int(reject.sum()),
        "df": df,
    }
    return result


def smoke_test(r: dict) -> None:
    td = r["trend_df"]
    require(not td.empty, "trend table is empty -- no operations had >= 5 runs")
    require("q_ols" in td.columns, "BH correction not applied -- statsmodels missing?")
    require(not log.any_disagreements(),
            "a cross-check DISAGREED -- investigate before reporting results")


def plot(r: dict) -> None:
    import matplotlib.pyplot as plt
    apply_style()

    td = r["trend_df"]
    if td.empty:
        return

    # Volcano-style plot: slope % per run vs -log10(q)
    fig, ax = plt.subplots()
    nonsig = td[~td["significant_fdr10"]]
    sig    = td[td["significant_fdr10"]]

    ax.scatter(nonsig["slope_pct_per_run"], -np.log10(nonsig["q_ols"] + 1e-10),
               s=8, color=COLORS[0], alpha=0.6, label="Not significant (FDR 10%)")
    if not sig.empty:
        ax.scatter(sig["slope_pct_per_run"], -np.log10(sig["q_ols"] + 1e-10),
                   s=14, color=COLORS[2], marker="^", label="Significant (FDR 10%)")

    ax.axvline(0, color="black", linewidth=0.8)
    ax.set_xlabel("OLS slope (% energy change per run)")
    ax.set_ylabel("-log10(q)")
    ax.set_title("Run-order energy trend per operation")
    ax.legend()
    save_fig(fig, str(OUT / "wear_runorder_volcano"))


def write_findings(r: dict) -> None:
    td = r["trend_df"]
    if not td.empty:
        td.to_csv(OUT / "trend_results.csv", index=False)

    n_sig = r.get("n_significant", 0)
    n_total = len(td)

    findings_text = f"""# wear_runorder: findings

**Status:** {"null-result" if n_sig == 0 else "explored"}
**Date:** {pd.Timestamp.today().date()}

## Headline
{"No significant run-order energy trend was found in any of the " + str(n_total) + " operations tested (FDR 10%). Tool wear does not appear as a detectable energy drift over the study's replication range." if n_sig == 0 else f"{n_sig} of {n_total} operations showed a significant run-order energy trend (FDR 10%). See trend_results.csv for per-operation slopes."}

## Numbers
- Operations tested (>= 5 runs): {n_total}
- Significant at FDR 10%: {n_sig}

## Verification

{log.to_markdown()}

## Caveats
- Run ordering is by run_id (part number) as a proxy for production sequence.
  If parts were machined out of numerical order, the run-index assignment is
  unreliable and trends cannot be interpreted as tool wear.
- This analysis is on energy per operation, not cutting force or surface finish.
  Tool wear can affect those metrics without reaching the power meter's noise floor.

## Feeds the journal paper?
{"Yes, as a limitations-section note: 'No significant energy drift with run order was found, suggesting that within the study's replication range, tool wear does not manifest as a detectable energy increase.'" if n_sig == 0 else "Yes -- this is a finding to explore further and report."}

## How to extend
- Attach actual machining timestamps (not run_id order) once load_power_stream()
  is implemented, to confirm the run-order proxy is valid.
- Analyze peak power as an alternative wear indicator.
"""
    (Path(__file__).parent / "FINDINGS.md").write_text(findings_text)
    print(f"FINDINGS.md written to {Path(__file__).parent / 'FINDINGS.md'}")


def main() -> None:
    try:
        import scipy  # noqa: F401
        import statsmodels  # noqa: F401
    except ImportError as e:
        print(f"PARKED: missing dependency: {e}")
        print("Install with: pip install scipy statsmodels")
        _gap = ROOT / "EXPLORATORY" / "_data_gaps.md"
        with _gap.open("a") as f:
            f.write(f"\n## wear_runorder (parked)\n- Missing: {e}\n")
        sys.exit(0)

    df = load()
    r = compute(df)
    try:
        smoke_test(r)
    except SmokeTestFailure as e:
        print(f"SMOKE TEST FAILED: {e}")
        sys.exit(1)
    plot(r)
    write_findings(r)
    print("OK")


if __name__ == "__main__":
    main()
