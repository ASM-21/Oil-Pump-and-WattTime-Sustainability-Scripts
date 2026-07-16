"""
Cross-dataset SEC comparison: Brillinger (Spinner U5-630) vs IN-MaC (Hurco
VMX30Ui), on a defensible common basis.

WHY THIS IS HARDER THAN A JOIN
------------------------------
The two datasets do not measure the same thing:

  Brillinger : sum of per-axis drive power (spindle + linear/rotary drives).
               Excludes control electronics, cooling, lighting. Dry machining.
  IN-MaC     : true total machine input from a single clamp meter. Includes
               everything: drives, controls, AND a flood-coolant pump. No
               per-axis breakdown is available.

Consequences:
  1. You cannot put Brillinger's drive sum and IN-MaC's machine input on the
     same axis directly. The only basis both can reach is MARGINAL energy:
     energy above the machine's own idle baseline.
  2. Even marginal energy does not fully reconcile. IN-MaC's coolant pump draws
     power during cutting that is absent from its idle baseline and absent from
     Brillinger entirely. That term inflates IN-MaC marginal SEC relative to
     Brillinger and is NOT removable from a single total meter.
  3. The alloy differs: Brillinger AlCuMgPb is free-machining leaded aluminum
     with lower cutting energy than IN-MaC 6061-T6. This is a material effect,
     not a machine effect, and no normalization removes it.

This module computes the marginal-SEC comparison and reports (1) (2) (3) as
explicit, labeled terms so the H3 "within 2x across machines" claim can be made
honestly or retired. The code does not silently reconcile what cannot be
reconciled from the available measurements.

IN-MaC ADAPTER: what you must export
------------------------------------
`from_inmac` needs, per operation type you want to compare:
  - total machine energy during that operation's cutting blocks (J), from the
    IAMMETER joined to your UUID operation tags;
  - cutting time in that operation (s);
  - removed volume for that operation (mm^3), e.g. from the same Z-map run on
    the Hurco NC, or CAM;
  - the machine idle baseline power (W), characterized with spindle off, drives
    energized, coolant in its cutting-time state if you want the strict
    marginal-over-idle definition.
Provide a coolant_w estimate if you have one; it is reported, not subtracted.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Normalized record
# ---------------------------------------------------------------------------

@dataclass
class DatasetMeta:
    """Provenance and the confound flags that no arithmetic can fix."""
    name: str
    machine: str
    material: str
    boundary: str               # "drive_sum" | "machine_input"
    coolant: str                # "dry" | "flood" | "mist"
    sampling_hz: float
    notes: str = ""


def _marginal_energy(total_energy_j: float, baseline_w: float,
                     time_s: float) -> float:
    """Energy above the machine's idle baseline over the cutting interval.

    This is the only quantity both a per-axis rig and a single total meter can
    both produce on a comparable footing. For a drive-sum dataset with no
    constant auxiliary load, baseline_w is ~0 and marginal == total.
    """
    return total_energy_j - baseline_w * time_s


def build_records(meta: DatasetMeta,
                  per_op: dict) -> pd.DataFrame:
    """Turn one dataset's per-operation numbers into normalized rows.

    per_op maps operation -> dict with keys:
        total_energy_j, time_s, volume_mm3, baseline_w, [coolant_w]
    """
    rows = []
    for op, d in per_op.items():
        total = d["total_energy_j"]
        t = d.get("time_s", np.nan)
        vol = d.get("volume_mm3", np.nan)
        base = d.get("baseline_w", 0.0)
        marg = _marginal_energy(total, base, t) if np.isfinite(t) else np.nan

        sec_total = total / vol if vol and vol > 0 else np.nan
        sec_marg = marg / vol if vol and vol > 0 and np.isfinite(marg) else np.nan

        rows.append({
            "dataset": meta.name,
            "machine": meta.machine,
            "material": meta.material,
            "boundary": meta.boundary,
            "coolant": meta.coolant,
            "operation": op,
            "total_energy_j": total,
            "baseline_w": base,
            "coolant_w": d.get("coolant_w", np.nan),
            "time_s": t,
            "volume_mm3": vol,
            "marginal_energy_j": marg,
            "sec_total_j_per_mm3": sec_total,
            "sec_marginal_j_per_mm3": sec_marg,
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Adapters
# ---------------------------------------------------------------------------

def from_brillinger(energy_by_op: pd.DataFrame,
                    volume_by_op: pd.DataFrame,
                    material: str = "AlCuMgPb",
                    baseline_w: float = 0.0,
                    machine: str = "Spinner U5-630",
                    sampling_hz: float = 500.0,
                    energy_col: str = "energy_j",
                    volume_col: str = "volume_mm3") -> pd.DataFrame:
    """Normalize Brillinger pipeline outputs.

    energy_by_op from bp.align_and_integrate()['by_operation']; volume_by_op
    from mr.simulate_removal()['by_operation']. baseline_w defaults to 0 because
    the drive sum carries essentially no constant auxiliary load; set it only if
    you have a measured drive idle figure.
    """
    meta = DatasetMeta(name="Brillinger", machine=machine, material=material,
                       boundary="drive_sum", coolant="dry",
                       sampling_hz=sampling_hz,
                       notes="per-axis drive sum; excludes aux/coolant/control")
    joined = energy_by_op[[energy_col]].join(volume_by_op[[volume_col]], how="left")
    per_op = {}
    for op, row in joined.iterrows():
        per_op[op] = {
            "total_energy_j": float(row[energy_col]),
            "time_s": float(energy_by_op.loc[op, "time_s"])
            if "time_s" in energy_by_op.columns else np.nan,
            "volume_mm3": float(row[volume_col]) if pd.notna(row[volume_col]) else np.nan,
            "baseline_w": baseline_w,
        }
    return build_records(meta, per_op)


def from_inmac(per_op: dict,
               material: str = "Al6061-T6",
               machine: str = "Hurco VMX30Ui",
               coolant: str = "flood",
               sampling_hz: float = 1.0) -> pd.DataFrame:
    """Normalize IN-MaC measurements.

    per_op maps operation -> {total_energy_j, time_s, volume_mm3, baseline_w,
    [coolant_w]}. total_energy_j is machine-input energy during that operation's
    cutting blocks (single meter, includes aux + coolant). See module docstring
    for how to export it.
    """
    meta = DatasetMeta(name="IN-MaC", machine=machine, material=material,
                       boundary="machine_input", coolant=coolant,
                       sampling_hz=sampling_hz,
                       notes="single total meter; coolant pump load present "
                             "during cut and not isolable")
    return build_records(meta, per_op)


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------

def compare(brillinger_df: pd.DataFrame,
            inmac_df: pd.DataFrame,
            basis: str = "marginal",
            operations=("cutting",)) -> dict:
    """Side-by-side SEC on a chosen basis, with a confounds report.

    basis:
        "marginal" : SEC from energy above idle baseline. The defensible
            common basis given a single total meter on the IN-MaC side.
        "total"    : SEC from raw energy on each dataset's native boundary.
            NOT comparable across the boundary gap; provided for inspection
            only and flagged as such.

    Returns the merged table, the per-operation ratio, and a list of
    unreconciled effects that bound how literally the ratio can be read.
    """
    if basis not in ("marginal", "total"):
        raise ValueError("basis must be marginal|total")
    sec_col = "sec_marginal_j_per_mm3" if basis == "marginal" else "sec_total_j_per_mm3"

    b = brillinger_df[brillinger_df["operation"].isin(operations)]
    i = inmac_df[inmac_df["operation"].isin(operations)]

    merged = b.merge(i, on="operation", suffixes=("_brill", "_inmac"))
    merged["sec_brill"] = merged[f"{sec_col}_brill"]
    merged["sec_inmac"] = merged[f"{sec_col}_inmac"]
    merged["ratio_inmac_over_brill"] = merged["sec_inmac"] / merged["sec_brill"]

    table = merged[["operation", "sec_brill", "sec_inmac",
                    "ratio_inmac_over_brill"]].copy()

    confounds = []
    # boundary
    if basis == "total" and set(b["boundary"]) != set(i["boundary"]):
        confounds.append(
            "BOUNDARY: total-basis SEC compares drive_sum (Brillinger) against "
            "machine_input (IN-MaC). These are different systems; the ratio is "
            "not interpretable. Use basis='marginal'."
        )
    if basis == "marginal":
        confounds.append(
            "BOUNDARY RESIDUAL: marginal energy removes each machine's idle "
            "baseline but not load that appears only during cutting. On IN-MaC "
            "this includes the flood-coolant pump, which raises IN-MaC marginal "
            "SEC by an amount a single total meter cannot separate out."
        )
    # coolant
    if set(b["coolant"]) != set(i["coolant"]):
        cw = i["coolant_w"].dropna()
        est = f" (estimated coolant draw {cw.iloc[0]:.0f} W)" if len(cw) else ""
        confounds.append(
            f"COOLANT: Brillinger dry vs IN-MaC {i['coolant'].iloc[0]}. Coolant "
            f"energy inflates IN-MaC SEC and is not in Brillinger at all{est}."
        )
    # material
    if set(b["material"]) != set(i["material"]):
        confounds.append(
            f"MATERIAL: {b['material'].iloc[0]} vs {i['material'].iloc[0]}. "
            "Free-machining leaded aluminum cuts at lower specific energy than "
            "6061-T6. This is a material effect, not a machine effect, and is "
            "not removed by any baseline correction."
        )
    # machine
    confounds.append(
        f"MACHINE: {b['machine'].iloc[0]} (5-axis) vs {i['machine'].iloc[0]} "
        "(3-axis). Drive count, mass, and efficiency differ."
    )

    # verdict against the H3 within-2x claim
    verdict = None
    if len(table) and table["ratio_inmac_over_brill"].notna().any():
        r = table["ratio_inmac_over_brill"].dropna()
        within = ((r >= 0.5) & (r <= 2.0)).all()
        verdict = {
            "ratios": r.round(3).tolist(),
            "all_within_2x": bool(within),
            "caveat": "Ratio reflects machine + coolant + alloy together. A "
                      "within-2x result does not isolate the machine effect; a "
                      "beyond-2x result may be driven by coolant or alloy, not "
                      "the machine.",
        }

    return {"table": table, "merged": merged, "confounds": confounds,
            "h3_verdict": verdict, "basis": basis}


def print_report(cmp: dict) -> None:
    print(f"basis: {cmp['basis']}\n")
    print("SEC comparison (J/mm^3):")
    print(cmp["table"].to_string(index=False))
    if cmp["h3_verdict"]:
        v = cmp["h3_verdict"]
        print(f"\nH3 ratios (IN-MaC / Brillinger): {v['ratios']}")
        print(f"all within 2x: {v['all_within_2x']}")
        print(f"caveat: {v['caveat']}")
    print("\nunreconciled confounds:")
    for c in cmp["confounds"]:
        print(f"  - {c}")
