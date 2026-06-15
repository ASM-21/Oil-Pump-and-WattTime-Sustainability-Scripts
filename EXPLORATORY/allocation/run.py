"""
ALLOCATION -- how badly do LCA allocation rules misassign energy vs measured?

Most LCA allocation debates are theoretical. This project uses the body/lid
measured energy pair as ground truth to falsify each rule directly.

Rules evaluated:
  mass      Allocate total CNC energy by mass removed (stock or finished -- pick one)
  time      Allocate by machining duration
  economic  Allocate by material cost proxy (same material, same cost/kg, so
            reduces to mass allocation -- noted explicitly)

Ground truth: measured per-part energy from the operation table (adapter).

Key outputs:
  - Signed error per rule per part (table)
  - Production mix sweep: error as a function of body:lid production ratio
  - Homing share quantification (~11.7% expected)
  - Figure: worst-case allocation error vs production mix

Run from repo root:
    python EXPLORATORY/allocation/run.py

Set CNC_DATA_DIR first -- see EXPLORATORY/shared/adapters.py header.
"""

from __future__ import annotations
import sys
from pathlib import Path
import pandas as pd
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from EXPLORATORY.shared.style import apply_style, save_fig, COLORS, MARKERS
from EXPLORATORY.shared.checks import CheckLog, require, SmokeTestFailure
from EXPLORATORY.shared import adapters

OUT = Path(__file__).parent / "outputs"
OUT.mkdir(exist_ok=True)
log = CheckLog()

# ---------------------------------------------------------------------------
# Mass basis -- VERIFY AGAINST YOUR RECORDS BEFORE CITING IN THE PAPER
# ---------------------------------------------------------------------------
# Choose ONE basis and use it everywhere. Old drafts mixed stock vs finished mass
# (72% vs 84% lighter for lid vs body), which gives different allocation ratios.
# Options:
#   "removed" -- mass_removed = stock_mass - finished_mass
#   "finished" -- finished part mass
#   "stock"   -- raw stock mass
MASS_BASIS = "removed"  # change to "finished" or "stock" if that is what your BOM has

# Values from context doc (unverified). Update once you have confirmed lab records.
MASS_REMOVED_G = {"body": 1437.0, "lid": 448.0}    # from SCOPE_tier_A_B_C.md
MASS_FINISHED_G = {"body": None, "lid": None}       # fill in from lab records
MASS_STOCK_G    = {"body": None, "lid": None}       # fill in from lab records

# Material cost (same material, so same $/kg; economic rule collapses to mass rule)
MATERIAL_COST_PER_KG = 3.50  # USD/kg Al6061, approximate; economic rule is informational


def load() -> pd.DataFrame:
    try:
        return adapters.load_operation_energy()
    except (adapters.DataNotInRepo, NotImplementedError) as e:
        _gap = ROOT / "EXPLORATORY" / "_data_gaps.md"
        with _gap.open("a") as f:
            f.write(f"\n## allocation (parked)\n- {e}\n")
        print(f"PARKED: {e}")
        sys.exit(0)


def _get_mass(part: str) -> float | None:
    """Return mass in grams for the chosen MASS_BASIS, or None if not available."""
    if MASS_BASIS == "removed":
        return MASS_REMOVED_G.get(part)
    if MASS_BASIS == "finished":
        return MASS_FINISHED_G.get(part)
    if MASS_BASIS == "stock":
        return MASS_STOCK_G.get(part)
    raise ValueError(f"Unknown MASS_BASIS={MASS_BASIS!r}")


def compute(df: pd.DataFrame) -> dict:
    result: dict = {}

    # ------------------------------------------------------------------
    # Ground truth: mean measured energy per part across all programs/runs
    # ------------------------------------------------------------------
    # Aggregate to part-run level first (sum operations within each run)
    part_runs = (
        df.groupby(["part", "run_id"])
        .agg(total_energy_wh=("energy_wh", "sum"),
             total_duration_s=("duration_s", "sum"))
        .reset_index()
    )
    # Then mean across runs for each part
    part_mean = (
        part_runs.groupby("part")
        .agg(
            mean_energy_wh=("total_energy_wh", "mean"),
            std_energy_wh=("total_energy_wh", "std"),
            n_runs=("total_energy_wh", "count"),
            mean_duration_s=("total_duration_s", "mean"),
        )
        .reset_index()
    )
    result["part_mean"] = part_mean

    # Lid / body energy ratio
    body_wh = part_mean.loc[part_mean["part"] == "body", "mean_energy_wh"]
    lid_wh  = part_mean.loc[part_mean["part"] == "lid",  "mean_energy_wh"]
    if not body_wh.empty and not lid_wh.empty:
        lid_body_ratio = float(lid_wh.values[0]) / float(body_wh.values[0])
        log.check_against_expected(
            "lid / body energy ratio", lid_body_ratio, 0.677,
            note="quoted in paper as ~67.7%; a DISAGREE here is a finding to report"
        )
        result["lid_body_ratio"] = lid_body_ratio

    # ------------------------------------------------------------------
    # Homing (TRANSITION_OVERHEAD) share of total CNC energy
    # ------------------------------------------------------------------
    homing_wh = df.loc[df["operation_cat"] == "homing", "energy_wh"].sum()
    idle_wh   = df.loc[df["operation_cat"] == "idle",   "energy_wh"].sum()
    total_wh  = df["energy_wh"].sum()
    homing_share = homing_wh / total_wh if total_wh > 0 else 0.0
    log.check_against_expected(
        "homing share of total CNC energy", homing_share, 0.117,
        note="quoted ~11.7%; TRANSITION_OVERHEAD is the homing proxy in our data"
    )
    result["homing_share"] = homing_share
    result["idle_share"] = idle_wh / total_wh if total_wh > 0 else 0.0

    # ------------------------------------------------------------------
    # Allocation rules
    # ------------------------------------------------------------------
    # For each rule, compute the fraction of total energy allocated to each part,
    # then compare to the measured fraction.
    parts = list(part_mean["part"].values)
    measured = {p: float(part_mean.loc[part_mean["part"] == p, "mean_energy_wh"].values[0])
                for p in parts}
    total_measured = sum(measured.values())

    # Mass-based allocation
    mass_g = {p: _get_mass(p) for p in parts}
    mass_available = all(v is not None and v > 0 for v in mass_g.values())
    result["mass_available"] = mass_available

    # Time-based allocation
    duration = {p: float(part_mean.loc[part_mean["part"] == p, "mean_duration_s"].values[0])
                for p in parts}
    total_duration = sum(duration.values())

    rule_rows = []
    for p in parts:
        row: dict = {"part": p,
                     "measured_wh": measured[p],
                     "measured_share_pct": measured[p] / total_measured * 100}

        # Time-based
        time_share = duration[p] / total_duration
        time_allocated = time_share * total_measured
        time_error = (time_allocated - measured[p]) / measured[p] * 100
        row.update({"time_share_pct": time_share * 100,
                    "time_allocated_wh": time_allocated,
                    "time_error_pct": time_error})

        # Mass-based (if mass data available)
        if mass_available:
            total_mass = sum(mass_g.values())
            mass_share = mass_g[p] / total_mass
            mass_allocated = mass_share * total_measured
            mass_error = (mass_allocated - measured[p]) / measured[p] * 100
            row.update({"mass_share_pct": mass_share * 100,
                        "mass_allocated_wh": mass_allocated,
                        "mass_error_pct": mass_error})
        else:
            row.update({"mass_share_pct": None, "mass_allocated_wh": None,
                        "mass_error_pct": None})

        # Economic proxy (same material => reduces to mass; note it explicitly)
        # For different materials this would differ; here we document the collapse.
        row["economic_note"] = ("Same material (Al6061) at same cost/kg; "
                                "economic allocation = mass allocation")
        rule_rows.append(row)

    rule_df = pd.DataFrame(rule_rows)
    result["rule_df"] = rule_df

    # Dual-path check: allocated shares must sum to total measured (conservation)
    time_total = rule_df["time_allocated_wh"].sum()
    log.cross_check(
        "time-allocation conservation (allocated sum vs measured total)",
        time_total, total_measured, rel_tol=0.001,
        note="shares must sum to 100% by construction"
    )
    if mass_available:
        mass_total = rule_df["mass_allocated_wh"].sum()
        log.cross_check(
            "mass-allocation conservation",
            mass_total, total_measured, rel_tol=0.001,
        )

    # ------------------------------------------------------------------
    # Mix sweep: vary production ratio body:lid from 1:5 to 5:1
    # ------------------------------------------------------------------
    # Error = how badly the allocation rule misassigns energy when body:lid
    # production ratio changes. A well-calibrated rule has ~0 error at all ratios.
    sweep_rows = []
    ratios = np.logspace(np.log10(0.2), np.log10(5.0), 50)  # body:lid ratio
    for ratio in ratios:
        # Hypothetical fleet: ratio bodies per lid
        # Total energy = ratio * body_energy + 1 * lid_energy
        e_body = measured.get("body", 0.0)
        e_lid = measured.get("lid", 0.0)
        if e_body == 0 or e_lid == 0:
            continue

        fleet_total = ratio * e_body + e_lid
        true_body_share = ratio * e_body / fleet_total

        # Time-based prediction of body share
        t_body = duration.get("body", 0.0)
        t_lid  = duration.get("lid", 0.0)
        time_body_share = (ratio * t_body) / (ratio * t_body + t_lid)
        time_error_body = (time_body_share - true_body_share) / true_body_share * 100

        row = {"body_lid_ratio": ratio, "true_body_share": true_body_share,
               "time_body_share": time_body_share, "time_error_body_pct": time_error_body}

        if mass_available:
            m_body = mass_g.get("body", 0.0)
            m_lid  = mass_g.get("lid", 0.0)
            mass_body_share = (ratio * m_body) / (ratio * m_body + m_lid)
            mass_error_body = (mass_body_share - true_body_share) / true_body_share * 100
            row.update({"mass_body_share": mass_body_share,
                        "mass_error_body_pct": mass_error_body})

        sweep_rows.append(row)

    result["sweep_df"] = pd.DataFrame(sweep_rows)
    result["total_measured_wh"] = total_measured

    # ------------------------------------------------------------------
    # C1: Specific energy per part (kWh per kg of material removed)
    # ------------------------------------------------------------------
    # Target values from paper context: body ~0.36, lid ~0.78 kWh/kg
    # Only computable when mass data is available (mass_available == True).
    if mass_available:
        sec_rows = []
        for p in parts:
            m_kg = mass_g[p] / 1000.0
            e_kwh = measured[p] / 1000.0
            sec = e_kwh / m_kg
            sec_rows.append({
                "part": p,
                "mass_removed_g": mass_g[p],
                "mean_energy_wh": measured[p],
                "sec_kwh_per_kg": round(sec, 3),
            })
        result["sec_df"] = pd.DataFrame(sec_rows)

        # Cross-check: lid SEC should exceed body SEC (lid is energy-intensive per kg)
        body_sec = next(r["sec_kwh_per_kg"] for r in sec_rows if r["part"] == "body")
        lid_sec  = next(r["sec_kwh_per_kg"] for r in sec_rows if r["part"] == "lid")
        log.check_against_expected("body SEC (kWh/kg removed)", body_sec, 0.36, rel_tol=0.30,
                                   note="context doc target; 30% tol because mass values unverified")
        log.check_against_expected("lid SEC (kWh/kg removed)", lid_sec, 0.78, rel_tol=0.30,
                                   note="context doc target; 30% tol because mass values unverified")

    result["df"] = df
    return result


def smoke_test(r: dict) -> None:
    pm = r["part_mean"]
    rd = r["rule_df"]

    require(len(pm) >= 2, "need at least body and lid to run allocation analysis")
    require((pm["mean_energy_wh"] > 0).all(), "non-positive mean energy per part")
    require(
        abs(rd["time_allocated_wh"].sum() - r["total_measured_wh"]) / r["total_measured_wh"] < 0.001,
        "time-allocation shares do not sum to measured total -- conservation violated"
    )
    if r["mass_available"]:
        require(
            abs(rd["mass_allocated_wh"].sum() - r["total_measured_wh"]) / r["total_measured_wh"] < 0.001,
            "mass-allocation shares do not sum to measured total -- conservation violated"
        )
    require(0 <= r["homing_share"] <= 0.50,
            f"homing share {r['homing_share']:.3f} is outside 0-50% range")
    require(not log.any_disagreements(),
            "a cross-check DISAGREED -- investigate before reporting results")


def plot(r: dict) -> None:
    import matplotlib.pyplot as plt
    apply_style()

    rd = r["rule_df"]
    sw = r["sweep_df"]

    # ---- Error table bar chart ----
    fig, ax = plt.subplots()
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
    ax.set_ylabel("Allocation error (%)\n(allocated - measured) / measured")
    ax.set_title("LCA allocation rule error vs measured")
    ax.legend()
    save_fig(fig, str(OUT / "allocation_error_by_rule"))

    # ---- Mix sweep figure ----
    if not sw.empty:
        fig2, ax2 = plt.subplots()
        ax2.plot(sw["body_lid_ratio"], sw["time_error_body_pct"],
                 color=COLORS[0], linestyle="-", label="Time-based error (body)")
        if "mass_error_body_pct" in sw.columns:
            ax2.plot(sw["body_lid_ratio"], sw["mass_error_body_pct"],
                     color=COLORS[1], linestyle="--", label="Mass-based error (body)")
        ax2.axhline(0, color="black", linewidth=0.8)
        ax2.axvline(1, color="gray", linewidth=0.5, linestyle=":")  # equal production
        ax2.set_xscale("log")
        ax2.set_xlabel("Body : Lid production ratio")
        ax2.set_ylabel("Body allocation error (%)")
        ax2.set_title("Allocation error vs production mix")
        ax2.legend()
        save_fig(fig2, str(OUT / "allocation_error_mix_sweep"))


def write_findings(r: dict) -> None:
    rd = r["rule_df"]
    pm = r["part_mean"]

    rd.to_csv(OUT / "allocation_rule_errors.csv", index=False)
    pm.to_csv(OUT / "part_mean_energy.csv", index=False)
    if not r["sweep_df"].empty:
        r["sweep_df"].to_csv(OUT / "mix_sweep.csv", index=False)
    if "sec_df" in r:
        r["sec_df"].to_csv(OUT / "specific_energy_per_part.csv", index=False)

    lid_ratio_line = (f"- Lid / body energy ratio: {r['lid_body_ratio']:.3f} "
                      f"(expected ~0.677)\n") if "lid_body_ratio" in r else ""

    mass_note = (
        "Mass-based rule evaluated using MASS_BASIS='removed' with context doc estimates "
        f"(body {MASS_REMOVED_G['body']:.0f} g, lid {MASS_REMOVED_G['lid']:.0f} g). "
        "Verify against measured stock/finished masses before citing."
        if not r["mass_available"]
        else
        f"Mass basis: {MASS_BASIS} (body {MASS_REMOVED_G.get('body')} g, "
        f"lid {MASS_REMOVED_G.get('lid')} g)."
    )

    # Build markdown tables manually (avoids requiring tabulate)
    pm_cols = ["part", "mean_energy_wh", "std_energy_wh", "n_runs"]
    pm_lines = ["| " + " | ".join(pm_cols) + " |",
                "|" + "|".join(["---"] * len(pm_cols)) + "|"]
    for _, row in pm[pm_cols].iterrows():
        pm_lines.append(
            f"| {row['part']} | {row['mean_energy_wh']:.3f} | "
            f"{row['std_energy_wh']:.3f} | {int(row['n_runs'])} |"
        )
    pm_table = "\n".join(pm_lines)

    err_cols = ["part", "measured_wh", "time_error_pct"]
    if r["mass_available"]:
        err_cols.append("mass_error_pct")
    err_lines = ["| " + " | ".join(err_cols) + " |",
                 "|" + "|".join(["---"] * len(err_cols)) + "|"]
    for _, row in rd[err_cols].iterrows():
        cells = [str(row["part"]), f"{row['measured_wh']:.3f}", f"{row['time_error_pct']:.1f}%"]
        if r["mass_available"]:
            cells.append(f"{row['mass_error_pct']:.1f}%")
        err_lines.append("| " + " | ".join(cells) + " |")
    err_table = "\n".join(err_lines)

    homing_share = r["homing_share"]
    idle_share = r["idle_share"]

    # Build C1 specific energy table outside f-string
    if "sec_df" in r and not r["sec_df"].empty:
        sec_lines = ["| Part | Mass removed (g) | Mean energy (Wh) | SEC (kWh/kg) |",
                     "|---|---|---|---|"]
        for _, row in r["sec_df"].iterrows():
            sec_lines.append(
                f"| {row['part']} | {row['mass_removed_g']:.0f} | "
                f"{row['mean_energy_wh']:.1f} | {row['sec_kwh_per_kg']:.3f} |"
            )
        c1_section = (
            "### C1 Specific energy per part (kWh / kg removed)\n"
            + "\n".join(sec_lines)
            + "\n- Full table: outputs/specific_energy_per_part.csv\n"
            + "- Context doc targets: body ~0.36, lid ~0.78 kWh/kg\n\n"
        )
    else:
        c1_section = (
            "### C1 Specific energy per part\n"
            "- Skipped: mass data not available (mass_available=False). "
            "Fill in bom.csv to enable.\n\n"
        )

    # Headline body error (safe access)
    body_err_str = "N/A"
    if "body" in rd["part"].values:
        body_err_val = rd.loc[rd["part"] == "body", "time_error_pct"].values[0]
        body_err_str = f"{body_err_val:.1f}%"

    findings_text = (
        "# allocation: findings\n\n"
        "**Status:** explored\n"
        f"**Date:** {pd.Timestamp.today().date()}\n\n"
        "## Headline\n"
        "Allocation rules assign energy to body vs lid with measurable systematic error\n"
        "because the two parts differ in energy-per-unit-mass (lid is lighter but\n"
        f"energy-intensive). Time-based allocation error (body): {body_err_str}.\n"
        f"Homing (non-productive repositioning) accounts for {homing_share*100:.1f}% of\n"
        "total CNC energy; each allocation rule assigns it differently.\n\n"
        "## Numbers\n\n"
        "### Measured energy per part (mean across runs)\n"
        f"{pm_table}\n\n"
        "### Allocation rule errors\n"
        f"{err_table}\n\n"
        f"{lid_ratio_line}"
        f"- Homing share of total CNC energy: {homing_share*100:.1f}% (expected ~11.7%)\n"
        f"- Idle share: {idle_share*100:.1f}%\n\n"
        f"{c1_section}"
        "## Verification\n\n"
        f"{log.to_markdown()}\n"
        "## Caveats\n"
        f"- {mass_note}\n"
        "- Economic allocation collapses to mass allocation for this product (same material,\n"
        "  same cost per kg for body and lid). A different-material product would differ.\n"
        "- Only two parts (body, lid). The mix sweep generalizes qualitatively but cannot\n"
        "  validate across a broader product range.\n"
        "- C1 specific energy values use context doc mass estimates until bom.csv is filled\n"
        "  in with verified stock/finished masses.\n\n"
        "## Feeds the journal paper?\n"
        "Yes -- Tier A, second priority. Supplies:\n"
        "- Allocation rule error table (new Results section or Discussion exhibit)\n"
        "- Mix sweep figure showing worst-case error vs production scenario\n"
        "- Homing share number (paper quotes ~11.7%)\n"
        "- C1 specific energy (kWh/kg) per part: shows aggregation-masking within product\n"
        "- Framing: most allocation debate is theoretical; here we have measured ground truth\n\n"
        "## How to extend\n"
        "- Verify mass_removed values against measured stock/finished masses; update bom.csv.\n"
        "- Add economic rule with a real cost proxy once BOM costs are confirmed.\n"
        "- Extend to a multi-part sweep if more parts are measured later.\n"
    )
    (Path(__file__).parent / "FINDINGS.md").write_text(findings_text)
    print(f"FINDINGS.md written to {Path(__file__).parent / 'FINDINGS.md'}")


def main() -> None:
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
