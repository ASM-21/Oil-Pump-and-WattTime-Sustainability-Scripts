"""
METHOD COMPARISON -- register (forward_kwh) vs active-power integration

Loads CNC data once, then reruns the key metrics AND all figures from each
EXPLORATORY project under both energy methods side-by-side. The "active-power"
variant swaps energy_wh to the trapezoid-integrated values (negatives clipped).

Figures produced (EXPLORATORY/compare_outputs/):
  cmp_allocation_error_by_rule    -- allocation error bars, both methods
  cmp_allocation_mix_sweep        -- allocation error vs production ratio
  cmp_estimation_error_by_level   -- ladder error bars, both methods
  cmp_duration_vs_energy          -- scatter + L0/L1 slopes, both methods
  cmp_wear_volcano                -- run-order trend volcano, both methods

CSVs:
  compare_operation_level.csv
  compare_allocation.csv
  compare_estimation_ladder.csv
  compare_wear_trend.csv

Run from repo root:
    python EXPLORATORY/compare_methods.py
"""

from __future__ import annotations
import sys
from pathlib import Path
import pandas as pd
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from EXPLORATORY.shared import adapters
from EXPLORATORY.shared.style import apply_style, save_fig, COLORS

OUT = Path(__file__).parent / "compare_outputs"
OUT.mkdir(exist_ok=True)

# Constants -- must match each project's run.py
CNC_RATED_POWER_W      = 13_400.0
MASS_REMOVED_G         = {"body": 1437.0, "lid": 448.0}
SEC_KARA_LI_KWH_PER_KG = 2.5


# ---------------------------------------------------------------------------
# Load / prep
# ---------------------------------------------------------------------------

def _pct_diff(a: float, b: float) -> float:
    if a == 0 or np.isnan(a) or np.isnan(b):
        return float("nan")
    return (b - a) / a * 100.0


def _load() -> pd.DataFrame:
    try:
        return adapters.load_operation_energy()
    except (adapters.DataNotInRepo, NotImplementedError) as e:
        print(f"PARKED: {e}")
        sys.exit(0)


def _make_active_df(df: pd.DataFrame) -> pd.DataFrame:
    """Copy with energy_wh replaced by energy_wh_active."""
    if df["energy_wh_active"].isna().all():
        print(
            "WARNING: energy_wh_active is all NaN -- active power stream absent.\n"
            "  Active-power panels will be empty."
        )
    df_act = df.copy()
    df_act["energy_wh"] = df_act["energy_wh_active"]
    return df_act


# ---------------------------------------------------------------------------
# Compute helpers (self-contained, no module-level log/OUT from projects)
# ---------------------------------------------------------------------------

def _compute_allocation(df: pd.DataFrame) -> dict:
    mass_g = MASS_REMOVED_G
    mass_available = all(v is not None and v > 0 for v in mass_g.values())

    part_runs = (
        df.groupby(["part", "run_id"])
        .agg(total_energy_wh=("energy_wh", "sum"), total_duration_s=("duration_s", "sum"))
        .reset_index()
    )
    part_mean = (
        part_runs.groupby("part")
        .agg(mean_energy_wh=("total_energy_wh", "mean"),
             mean_duration_s=("total_duration_s", "mean"))
        .reset_index()
    )

    parts = list(part_mean["part"].values)
    measured = {p: float(part_mean.loc[part_mean["part"] == p, "mean_energy_wh"].values[0])
                for p in parts}
    duration = {p: float(part_mean.loc[part_mean["part"] == p, "mean_duration_s"].values[0])
                for p in parts}
    total_measured = sum(measured.values())
    total_duration = sum(duration.values())

    rule_rows = []
    for p in parts:
        row: dict = {"part": p}
        time_share = duration[p] / total_duration
        time_allocated = time_share * total_measured
        row["time_error_pct"] = (time_allocated - measured[p]) / measured[p] * 100
        if mass_available:
            total_mass = sum(mass_g.values())
            mass_share = mass_g[p] / total_mass
            mass_allocated = mass_share * total_measured
            row["mass_error_pct"] = (mass_allocated - measured[p]) / measured[p] * 100
        rule_rows.append(row)
    rule_df = pd.DataFrame(rule_rows)

    # Mix sweep
    sweep_rows = []
    ratios = np.logspace(np.log10(0.2), np.log10(5.0), 50)
    e_body = measured.get("body", 0.0)
    e_lid  = measured.get("lid",  0.0)
    t_body = duration.get("body", 0.0)
    t_lid  = duration.get("lid",  0.0)
    if e_body > 0 and e_lid > 0:
        for ratio in ratios:
            fleet_total    = ratio * e_body + e_lid
            true_body_share = ratio * e_body / fleet_total
            time_body_share = (ratio * t_body) / (ratio * t_body + t_lid)
            time_error_body = (time_body_share - true_body_share) / true_body_share * 100
            row2: dict = {"body_lid_ratio": ratio, "time_error_body_pct": time_error_body}
            if mass_available:
                m_body = mass_g["body"]
                m_lid  = mass_g["lid"]
                mass_body_share = (ratio * m_body) / (ratio * m_body + m_lid)
                mass_error_body = (mass_body_share - true_body_share) / true_body_share * 100
                row2["mass_error_body_pct"] = mass_error_body
            sweep_rows.append(row2)

    return {
        "rule_df": rule_df,
        "sweep_df": pd.DataFrame(sweep_rows),
        "mass_available": mass_available,
    }


def _compute_estimation_ladder(df: pd.DataFrame) -> dict:
    total_wh = df["energy_wh"].sum()
    total_s  = df["duration_s"].sum()
    avg_power_w = total_wh * 3600.0 / total_s

    program_runs = (
        df.groupby(["part", "program", "run_id"])
        .agg(L4_energy_wh=("energy_wh", "sum"), total_duration_s=("duration_s", "sum"))
        .reset_index()
    )
    program_runs["L3_energy_wh"] = program_runs["L4_energy_wh"]
    program_runs["L0_energy_wh"] = CNC_RATED_POWER_W * program_runs["total_duration_s"] / 3600.0
    program_runs["L1_energy_wh"] = avg_power_w       * program_runs["total_duration_s"] / 3600.0
    mass_kwh = {p: SEC_KARA_LI_KWH_PER_KG * g / 1000.0 for p, g in MASS_REMOVED_G.items()}
    program_runs["L2_energy_wh"] = program_runs["part"].map(mass_kwh) * 1000.0
    for lvl in ["L0", "L1", "L2", "L3"]:
        program_runs[f"{lvl}_error_pct"] = (
            (program_runs[f"{lvl}_energy_wh"] - program_runs["L4_energy_wh"])
            / program_runs["L4_energy_wh"] * 100.0
        )

    return {"program_runs": program_runs, "avg_power_w": avg_power_w, "df": df}


def _compute_wear_runorder(df: pd.DataFrame) -> dict:
    from scipy import stats as scipy_stats
    from statsmodels.stats.multitest import multipletests

    df = df.copy().sort_values(["part", "program", "operation_id", "run_id"])
    df["run_index"] = df.groupby(["part", "program", "operation_id"]).cumcount()

    result_rows = []
    for (part, program, op_id, op_cat), group in df.groupby(
            ["part", "program", "operation_id", "operation_cat"]):
        if len(group) < 5:
            continue
        x = group["run_index"].to_numpy(float)
        y = group["energy_wh"].to_numpy(float)
        if np.isnan(y).any():
            continue
        mean_y = y.mean()
        slope, _, r_val, p_ols, _ = scipy_stats.linregress(x, y)
        rho, p_spearman = scipy_stats.spearmanr(x, y)
        result_rows.append({
            "part": part, "program": program,
            "operation_id": op_id, "operation_cat": op_cat,
            "n_runs": len(x), "mean_wh": mean_y,
            "slope_pct_per_run": slope / mean_y * 100,
            "r_squared": r_val ** 2,
            "p_ols": p_ols,
            "spearman_rho": rho,
            "p_spearman": p_spearman,
        })

    if not result_rows:
        return {"trend_df": pd.DataFrame(), "n_significant": 0}

    trend_df = pd.DataFrame(result_rows)
    reject, q_vals, _, _ = multipletests(trend_df["p_ols"].values, alpha=0.10, method="fdr_bh")
    trend_df["q_ols"] = q_vals
    trend_df["significant_fdr10"] = reject
    return {"trend_df": trend_df, "n_significant": int(reject.sum())}


# ---------------------------------------------------------------------------
# Comparison tables (CSV outputs)
# ---------------------------------------------------------------------------

def compare_operation_level(df_reg: pd.DataFrame, df_act: pd.DataFrame) -> pd.DataFrame:
    def _agg(df, sfx):
        return (df.groupby(["part", "operation_cat"])
                .agg(**{f"mean_wh_{sfx}": ("energy_wh", "mean"),
                        f"std_wh_{sfx}":  ("energy_wh", "std"),
                        "n": ("energy_wh", "count")})
                .reset_index())
    reg = _agg(df_reg, "reg")
    act = _agg(df_act, "act").drop(columns="n")
    merged = reg.merge(act, on=["part", "operation_cat"])
    merged["diff_pct"] = merged.apply(
        lambda r: round(_pct_diff(r["mean_wh_reg"], r["mean_wh_act"]), 2), axis=1)
    return merged.sort_values(["part", "operation_cat"]).reset_index(drop=True)


def _alloc_summary(df):
    part_mean = (
        df.groupby(["part", "run_id"])
        .agg(wh=("energy_wh", "sum"), s=("duration_s", "sum"))
        .reset_index()
        .groupby("part")
        .agg(mean_wh=("wh", "mean"), mean_s=("s", "mean"))
        .reset_index()
    )
    body_wh = float(part_mean.loc[part_mean["part"] == "body", "mean_wh"].values[0])
    lid_wh  = float(part_mean.loc[part_mean["part"] == "lid",  "mean_wh"].values[0])
    body_s  = float(part_mean.loc[part_mean["part"] == "body", "mean_s"].values[0])
    lid_s   = float(part_mean.loc[part_mean["part"] == "lid",  "mean_s"].values[0])
    total_wh = body_wh + lid_wh
    time_share_body = body_s / (body_s + lid_s)
    time_err = (time_share_body * total_wh - body_wh) / body_wh * 100
    return {"body_mean_wh": body_wh, "lid_mean_wh": lid_wh,
            "lid_body_ratio": lid_wh / body_wh, "time_alloc_body_err_%": time_err}


def compare_allocation(df_reg, df_act):
    rows = []
    for method, df in [("register", df_reg), ("active_power", df_act)]:
        row = {"method": method}
        row.update({k: round(v, 4) for k, v in _alloc_summary(df).items()})
        rows.append(row)
    df_out = pd.DataFrame(rows)
    reg = df_out[df_out["method"] == "register"].iloc[0]
    act = df_out[df_out["method"] == "active_power"].iloc[0]
    diff = {"method": "diff_%"}
    for col in ["body_mean_wh", "lid_mean_wh", "lid_body_ratio", "time_alloc_body_err_%"]:
        diff[col] = round(_pct_diff(float(reg[col]), float(act[col])), 2)
    return pd.concat([df_out, pd.DataFrame([diff])], ignore_index=True)


def compare_estimation_ladder(df_reg, df_act):
    rows = []
    for method, df in [("register", df_reg), ("active_power", df_act)]:
        r = _compute_estimation_ladder(df)
        pr = r["program_runs"]
        rows.append({
            "method": method,
            "fleet_avg_power_w": round(r["avg_power_w"], 1),
            "u_cnc": round(r["avg_power_w"] / CNC_RATED_POWER_W, 4),
            "L0_error_%_mean": round(pr["L0_error_pct"].mean(), 1),
            "L1_error_%_mean": round(pr["L1_error_pct"].mean(), 1),
        })
    df_out = pd.DataFrame(rows)
    reg = df_out[df_out["method"] == "register"].iloc[0]
    act = df_out[df_out["method"] == "active_power"].iloc[0]
    diff = {"method": "diff_%"}
    for col in ["fleet_avg_power_w", "u_cnc", "L0_error_%_mean", "L1_error_%_mean"]:
        diff[col] = round(_pct_diff(float(reg[col]), float(act[col])), 2)
    return pd.concat([df_out, pd.DataFrame([diff])], ignore_index=True)


def compare_wear_trend(df_reg, df_act):
    from scipy import stats as scipy_stats
    rows = []
    for method, df in [("register", df_reg), ("active_power", df_act)]:
        df = df.copy().sort_values(["part", "program", "operation_id", "run_id"])
        df["run_index"] = df.groupby(["part", "program", "operation_id"]).cumcount()
        n_tested, n_sig, slopes = 0, 0, []
        for (_, op_id), g in df.groupby(["part", "operation_id"]):
            if len(g) < 5:
                continue
            x, y = g["run_index"].to_numpy(float), g["energy_wh"].to_numpy(float)
            if np.isnan(y).any():
                continue
            slope, _, _, p, _ = scipy_stats.linregress(x, y)
            n_tested += 1
            if p < 0.05:
                n_sig += 1
            slopes.append(abs(slope / y.mean() * 100))
        rows.append({
            "method": method, "n_ops_tested": n_tested, "n_significant_p05": n_sig,
            "median_|slope|_%/run": round(float(np.median(slopes)), 3) if slopes else float("nan"),
        })
    df_out = pd.DataFrame(rows)
    reg = df_out[df_out["method"] == "register"].iloc[0]
    act = df_out[df_out["method"] == "active_power"].iloc[0]
    diff = {
        "method": "diff_%",
        "n_ops_tested": "",
        "n_significant_p05": int(act["n_significant_p05"]) - int(reg["n_significant_p05"]),
        "median_|slope|_%/run": round(_pct_diff(
            float(reg["median_|slope|_%/run"]), float(act["median_|slope|_%/run"])), 2),
    }
    return pd.concat([df_out, pd.DataFrame([diff])], ignore_index=True)


# ---------------------------------------------------------------------------
# Figure helpers: draw one panel onto a given Axes
# ---------------------------------------------------------------------------

def _ax_allocation_error(ax, r: dict, title: str) -> None:
    rd = r["rule_df"]
    parts = rd["part"].tolist()
    x = np.arange(len(parts))
    width = 0.35
    ax.bar(x - width / 2, rd["time_error_pct"], width,
           label="Time-based", color=COLORS[0], alpha=0.85)
    if r["mass_available"] and "mass_error_pct" in rd.columns:
        ax.bar(x + width / 2, rd["mass_error_pct"], width,
               label="Mass-based", color=COLORS[1], alpha=0.85)
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels([p.capitalize() for p in parts])
    ax.set_ylabel("Allocation error (%)")
    ax.set_title(title)
    ax.legend()


def _ax_mix_sweep(ax, r: dict, title: str) -> None:
    sw = r["sweep_df"]
    if sw.empty:
        ax.text(0.5, 0.5, "no data", transform=ax.transAxes, ha="center")
        return
    ax.plot(sw["body_lid_ratio"], sw["time_error_body_pct"],
            color=COLORS[0], linestyle="-", label="Time-based (body)")
    if "mass_error_body_pct" in sw.columns:
        ax.plot(sw["body_lid_ratio"], sw["mass_error_body_pct"],
                color=COLORS[1], linestyle="--", label="Mass-based (body)")
    ax.axhline(0, color="black", linewidth=0.8)
    ax.axvline(1, color="gray", linewidth=0.5, linestyle=":")
    ax.set_xscale("log")
    ax.set_xlabel("Body : Lid ratio")
    ax.set_ylabel("Body allocation error (%)")
    ax.set_title(title)
    ax.legend()


def _ax_estimation_bars(ax, r: dict, title: str) -> None:
    pr = r["program_runs"]
    levels = ["L0", "L1", "L2", "L3"]
    labels = ["L0 rated", "L1 avg pwr", "L2 SEC", "L3 prog"]
    x = np.arange(len(levels))
    width = 0.35
    for i, part in enumerate(["body", "lid"]):
        part_data = pr[pr["part"] == part]
        if part_data.empty:
            continue
        means = [part_data[f"{lvl}_error_pct"].mean() for lvl in levels]
        ax.bar(x + i * width - width / 2, means, width,
               label=part.capitalize(), color=COLORS[i], alpha=0.85)
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=15, ha="right")
    ax.set_ylabel("Signed error (%)")
    ax.set_title(title)
    ax.legend()


def _ax_duration_scatter(ax, r: dict, title: str) -> None:
    df = r["df"]
    valid = df["energy_wh"].notna() & df["duration_s"].notna()
    ax.scatter(df.loc[valid, "duration_s"] / 60, df.loc[valid, "energy_wh"],
               s=6, alpha=0.5, color=COLORS[0], label="Operations (L4)")
    t_range = np.linspace(0, df["duration_s"].max(), 100)
    avg_w = r["avg_power_w"]
    ax.plot(t_range / 60, avg_w * t_range / 3600,
            color=COLORS[1], linestyle="--", label=f"L1 ({avg_w:.0f} W)")
    ax.plot(t_range / 60, CNC_RATED_POWER_W * t_range / 3600,
            color=COLORS[2], linestyle=":", label=f"L0 ({CNC_RATED_POWER_W/1000:.1f} kW)")
    ax.set_xlabel("Duration (min)")
    ax.set_ylabel("Energy (Wh)")
    ax.set_title(title)
    ax.legend()


def _ax_volcano(ax, r: dict, title: str) -> None:
    td = r["trend_df"]
    if td.empty:
        ax.text(0.5, 0.5, "no data", transform=ax.transAxes, ha="center")
        ax.set_title(title)
        return
    nonsig = td[~td["significant_fdr10"]]
    sig    = td[td["significant_fdr10"]]
    ax.scatter(nonsig["slope_pct_per_run"], -np.log10(nonsig["q_ols"] + 1e-10),
               s=8, color=COLORS[0], alpha=0.6, label="Not sig (FDR 10%)")
    if not sig.empty:
        ax.scatter(sig["slope_pct_per_run"], -np.log10(sig["q_ols"] + 1e-10),
                   s=14, color=COLORS[2], marker="^", label="Significant")
    ax.axvline(0, color="black", linewidth=0.8)
    ax.set_xlabel("OLS slope (%/run)")
    ax.set_ylabel("-log10(q)")
    ax.set_title(title)
    ax.legend()


# ---------------------------------------------------------------------------
# Side-by-side figure generators
# ---------------------------------------------------------------------------

def _fig2(ax_fn, r_reg, r_act, stem: str) -> None:
    """Create a 1×2 figure: left=register, right=active power."""
    import matplotlib.pyplot as plt
    fig, (ax_l, ax_r) = plt.subplots(1, 2, figsize=(7.2, 2.6))
    ax_fn(ax_l, r_reg, "Register (forward_kWh)")
    ax_fn(ax_r, r_act, "Active power (trapezoid)")
    fig.tight_layout()
    save_fig(fig, str(OUT / stem))


def plot_all(r_reg_alloc, r_act_alloc,
             r_reg_ladder, r_act_ladder,
             r_reg_wear,   r_act_wear) -> None:
    apply_style()

    _fig2(_ax_allocation_error, r_reg_alloc,  r_act_alloc,  "cmp_allocation_error_by_rule")
    _fig2(_ax_mix_sweep,        r_reg_alloc,  r_act_alloc,  "cmp_allocation_mix_sweep")
    _fig2(_ax_estimation_bars,  r_reg_ladder, r_act_ladder, "cmp_estimation_error_by_level")
    _fig2(_ax_duration_scatter, r_reg_ladder, r_act_ladder, "cmp_duration_vs_energy")
    _fig2(_ax_volcano,          r_reg_wear,   r_act_wear,   "cmp_wear_volcano")

    print(f"5 figures (PNG + PDF) written to {OUT}/")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def _section(title: str) -> None:
    print()
    print("=" * 60)
    print(title)
    print("=" * 60)


def main() -> None:
    print("Loading CNC data (both energy streams)...")
    df = _load()

    n_active_nan = df["energy_wh_active"].isna().sum()
    n_total = len(df)
    print(f"  {n_total} operation rows  |  energy_wh_active valid: {n_total - n_active_nan}  NaN: {n_active_nan}")

    df_reg = df.copy()
    df_act = _make_active_df(df)

    # --- comparison tables ---
    _section("OPERATION LEVEL: mean energy per category (Wh)")
    op_cmp = compare_operation_level(df_reg, df_act)
    print(op_cmp.to_string(index=False))
    op_cmp.to_csv(OUT / "compare_operation_level.csv", index=False)

    _section("ALLOCATION: lid/body ratio + time-allocation error")
    alloc_cmp = compare_allocation(df_reg, df_act)
    print(alloc_cmp.to_string(index=False))
    alloc_cmp.to_csv(OUT / "compare_allocation.csv", index=False)

    _section("ESTIMATION LADDER: fleet avg power + L0/L1 error")
    ladder_cmp = compare_estimation_ladder(df_reg, df_act)
    print(ladder_cmp.to_string(index=False))
    ladder_cmp.to_csv(OUT / "compare_estimation_ladder.csv", index=False)

    _section("WEAR / RUN ORDER: significant trend count")
    try:
        wear_cmp = compare_wear_trend(df_reg, df_act)
        print(wear_cmp.to_string(index=False))
        wear_cmp.to_csv(OUT / "compare_wear_trend.csv", index=False)
        wear_available = True
    except ImportError as e:
        print(f"  SKIPPED (missing dependency): {e}")
        print("  Install with: pip install scipy statsmodels")
        wear_available = False

    # --- compute result dicts for figures ---
    _section("Generating figures...")
    r_reg_alloc  = _compute_allocation(df_reg)
    r_act_alloc  = _compute_allocation(df_act)
    r_reg_ladder = _compute_estimation_ladder(df_reg)
    r_act_ladder = _compute_estimation_ladder(df_act)

    if wear_available:
        r_reg_wear = _compute_wear_runorder(df_reg)
        r_act_wear = _compute_wear_runorder(df_act)
    else:
        empty = {"trend_df": pd.DataFrame(), "n_significant": 0}
        r_reg_wear = r_act_wear = empty

    plot_all(r_reg_alloc, r_act_alloc,
             r_reg_ladder, r_act_ladder,
             r_reg_wear,   r_act_wear)

    print()
    print(f"All outputs in {OUT}/")
    print("OK")


if __name__ == "__main__":
    main()
