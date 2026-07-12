#!/usr/bin/env python3
"""
estimate_energy.py
==================

Estimate per-pass energy for each operation and compare regression models, to see
which model best predicts energy for which operation. Points straight at the
folder of per-operation CSVs from split_operations.py; no separate feature step.

Setup
-----
Target (one value per operation pass):
  energy_kwh_meter   forward-kWh meter delta over the pass (default if present)
  energy_wh_integral active-power integral over the pass, in Wh
Choose with --target {auto, kwh_meter, wh_integral}.

Predictors: every channel summary EXCEPT the energy group (power/voltage/current/
kWh/...). Predicting energy from power would be circular, so the energy sensors are
removed and the question becomes how well the *other* sensors (spindle, axis,
vibration, thermal) plus pass duration explain energy. Drop duration with
--exclude-duration to test whether the sensors carry energy signal on their own.

Evaluation: GroupKFold grouped by run (source_file), so whole runs are held out.
Operations with too few runs/passes to cross-validate honestly are skipped and
listed (this is where quality_check.py earns its keep).

Outputs (into --output, default ./ml/energy):
  results_energy_by_operation.csv   operation x algorithm: R2 / MAE / RMSE / nRMSE
  best_model_per_operation.csv      winning model per operation
  results_pooled.csv                one model across all operations (baseline)
  feature_importance_by_operation.csv  top sensors driving energy, per operation
  *.png                             per-operation R2 chart (if matplotlib present)

Usage
-----
  python estimate_energy.py --input ./operation_csvs
  python estimate_energy.py --input ./operation_csvs --target wh_integral --exclude-duration
"""

from __future__ import annotations

import argparse
import warnings
from pathlib import Path
from typing import Dict, List, Tuple

_HERE = Path(__file__).resolve().parent

import numpy as np
import pandas as pd

from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LinearRegression, Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import GroupKFold, cross_val_predict
from sklearn.neighbors import KNeighborsRegressor
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVR

import features as F

warnings.filterwarnings("ignore")


def make_models() -> Dict[str, Pipeline]:
    def pipe(reg):
        return Pipeline([
            ("impute", SimpleImputer(strategy="median")),
            ("scale", StandardScaler()),
            ("reg", reg),
        ])
    return {
        "linear": pipe(LinearRegression()),
        "ridge": pipe(Ridge(alpha=1.0)),
        "random_forest": pipe(RandomForestRegressor(n_estimators=300, random_state=0)),
        "grad_boost": pipe(GradientBoostingRegressor(random_state=0)),
        "svr_rbf": pipe(SVR(kernel="rbf", C=10, gamma="scale")),
        "knn": pipe(KNeighborsRegressor(n_neighbors=5)),
    }


def pick_target(table: pd.DataFrame, choice: str) -> str:
    have = [t for t in F.TARGET_COLUMNS if t in table.columns]
    if not have:
        raise ValueError("No energy target columns found. Need a forward-kWh or "
                         "active-power channel in the source data.")
    name = {"kwh_meter": "energy_kwh_meter", "wh_integral": "energy_wh_integral"}.get(choice)
    if choice == "auto":
        # Prefer the meter if it actually varies, else the power integral.
        if "energy_kwh_meter" in have and table["energy_kwh_meter"].std() > 0:
            return "energy_kwh_meter"
        return "energy_wh_integral" if "energy_wh_integral" in have else have[0]
    if name not in table.columns:
        raise ValueError(f"Requested target {name} not available. Have: {have}")
    return name


def predictor_columns(table: pd.DataFrame, groups: Dict[str, List[str]],
                      include_duration: bool) -> List[str]:
    """All feature columns minus the energy group (anti-leakage) and targets."""
    cols = F.feature_columns(table, include_duration=include_duration)
    energy_cols = set(groups.get("energy", []))
    return [c for c in cols if c not in energy_cols]


def _metrics(y, pred) -> Dict[str, float]:
    rmse = float(np.sqrt(mean_squared_error(y, pred)))
    denom = float(np.mean(np.abs(y))) or np.nan
    return {
        "r2": float(r2_score(y, pred)),
        "mae": float(mean_absolute_error(y, pred)),
        "rmse": rmse,
        "nrmse": rmse / denom if denom else np.nan,
    }


def eval_subset(models, X, y, groups, n_splits) -> Dict[str, Dict[str, float]]:
    cv = GroupKFold(n_splits=n_splits)
    out = {}
    for name, model in models.items():
        try:
            pred = cross_val_predict(model, X, y, groups=groups, cv=cv)
            out[name] = _metrics(y, pred)
        except Exception as exc:  # noqa: BLE001
            out[name] = {"r2": np.nan, "mae": np.nan, "rmse": np.nan, "nrmse": np.nan,
                         "error": str(exc)}
    return out


def per_operation(models, table, target, pred_cols, min_passes, min_runs
                  ) -> Tuple[pd.DataFrame, List[Tuple[str, str]]]:
    rows = []
    skipped = []
    for op, g in table.groupby("operation"):
        n_passes = len(g)
        n_runs = g["source_file"].nunique()
        if n_passes < min_passes or n_runs < min_runs:
            skipped.append((op, f"{n_passes} passes / {n_runs} runs"))
            continue
        n_splits = min(5, n_runs)
        res = eval_subset(models, g[pred_cols], g[target], g["source_file"], n_splits)
        for alg, m in res.items():
            rows.append({"operation": op, "algorithm": alg, "n_passes": n_passes,
                         "n_runs": n_runs, **{k: v for k, v in m.items() if k != "error"}})
    return pd.DataFrame(rows), skipped


def pooled(models, table, target, pred_cols) -> pd.DataFrame:
    n_runs = table["source_file"].nunique()
    res = eval_subset(models, table[pred_cols], table[target],
                      table["source_file"], min(5, n_runs))
    return pd.DataFrame([{"algorithm": a, **m} for a, m in res.items()])


def importance_by_operation(table, target, pred_cols, min_passes, top=10) -> pd.DataFrame:
    rows = []
    for op, g in table.groupby("operation"):
        if len(g) < min_passes:
            continue
        X = SimpleImputer(strategy="median").fit_transform(g[pred_cols])
        rf = RandomForestRegressor(n_estimators=300, random_state=0).fit(X, g[target])
        imp = pd.Series(rf.feature_importances_, index=pred_cols).sort_values(ascending=False)
        for feat, val in imp.head(top).items():
            rows.append({"operation": op, "feature": feat, "importance": float(val)})
    return pd.DataFrame(rows)


def maybe_plot(by_op: pd.DataFrame, out_dir: Path) -> None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return
    grid = by_op.pivot(index="operation", columns="algorithm", values="r2")
    fig, ax = plt.subplots(figsize=(1.3 * grid.shape[1] + 2, 0.5 * grid.shape[0] + 2))
    im = ax.imshow(grid.values, aspect="auto", cmap="RdYlGn", vmin=0, vmax=1)
    ax.set_xticks(range(grid.shape[1])); ax.set_xticklabels(grid.columns, rotation=45, ha="right")
    ax.set_yticks(range(grid.shape[0])); ax.set_yticklabels(grid.index)
    for i in range(grid.shape[0]):
        for j in range(grid.shape[1]):
            v = grid.values[i, j]
            ax.text(j, i, "" if np.isnan(v) else f"{v:.2f}", ha="center", va="center", fontsize=8)
    ax.set_title("Energy regression R2 (operation x algorithm)")
    fig.colorbar(im, ax=ax, label="R2")
    fig.tight_layout(); fig.savefig(out_dir / "energy_r2_by_operation.png", dpi=130); plt.close(fig)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Per-operation energy regression model comparison.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    ap.add_argument("--input", default=str(_HERE / "operation_csvs"))
    ap.add_argument("--output", default=str(_HERE / "ml/energy"))
    ap.add_argument("--target", choices=["auto", "kwh_meter", "wh_integral"], default="auto")
    ap.add_argument("--exclude-duration", action="store_true",
                    help="Drop duration/n_samples so only sensor signal predicts energy.")
    ap.add_argument("--min-samples", type=int, default=0,
                    help="Drop passes shorter than this many samples before modeling.")
    ap.add_argument("--min-passes", type=int, default=6)
    ap.add_argument("--min-runs", type=int, default=3)
    args = ap.parse_args()

    out_dir = Path(args.output); out_dir.mkdir(parents=True, exist_ok=True)
    table, groups = F.prepare(args.input, "segment")

    if args.min_samples > 0 and "n_samples" in table:
        before = len(table)
        table = table[table["n_samples"] >= args.min_samples].copy()
        print(f"Length filter: kept {len(table)}/{before} passes "
              f"(>= {args.min_samples} samples).")

    target = pick_target(table, args.target)
    pred_cols = predictor_columns(table, groups, include_duration=not args.exclude_duration)
    print(f"Target: {target}. Predictors: {len(pred_cols)} columns "
          f"(energy sensors excluded{', duration excluded' if args.exclude_duration else ''}).\n")

    models = make_models()
    by_op, skipped = per_operation(models, table, target, pred_cols,
                                   args.min_passes, args.min_runs)
    if by_op.empty:
        print("No operation had enough runs/passes to evaluate. See quality_check.py.")
        for op, why in skipped:
            print(f"  skipped {op}: {why}")
        return 1

    pooled_df = pooled(models, table, target, pred_cols)
    importance = importance_by_operation(table, target, pred_cols, args.min_passes)

    by_op.to_csv(out_dir / "results_energy_by_operation.csv", index=False)
    best = (by_op.sort_values("r2", ascending=False)
            .groupby("operation").first().reset_index()
            [["operation", "algorithm", "r2", "mae", "rmse", "nrmse", "n_passes", "n_runs"]])
    best.to_csv(out_dir / "best_model_per_operation.csv", index=False)
    pooled_df.to_csv(out_dir / "results_pooled.csv", index=False)
    importance.to_csv(out_dir / "feature_importance_by_operation.csv", index=False)
    maybe_plot(by_op, out_dir)

    # ---- console summary -------------------------------------------------
    print("Best energy model per operation:")
    for _, r in best.iterrows():
        print(f"  {r['operation']:18s} -> {r['algorithm']:15s} "
              f"R2={r['r2']:.3f}  nRMSE={r['nrmse']:.3f}  (n={r['n_passes']}, runs={r['n_runs']})")
    if best["algorithm"].nunique() > 1:
        print("  => different operations are best estimated by different models.")
    else:
        print(f"  => {best['algorithm'].iloc[0]} estimates energy best across operations.")

    pooled_best = pooled_df.sort_values("r2", ascending=False).iloc[0]
    mean_perop_r2 = best["r2"].mean()
    print(f"\nPooled single model best: {pooled_best['algorithm']} R2={pooled_best['r2']:.3f}")
    print(f"Mean per-operation R2:    {mean_perop_r2:.3f}")
    print("  => " + ("per-operation models help." if mean_perop_r2 > pooled_best["r2"] + 0.02
                     else "a single pooled model is competitive here."))

    if not importance.empty:
        print("\nTop energy driver per operation:")
        for op, gg in importance.groupby("operation"):
            top = gg.sort_values("importance", ascending=False).iloc[0]
            print(f"  {op:18s} {top['feature']} ({top['importance']:.2f})")

    if skipped:
        print("\nSkipped (too little data, see quality_check.py):")
        for op, why in skipped:
            print(f"  {op}: {why}")

    print(f"\nWrote results to {out_dir}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
