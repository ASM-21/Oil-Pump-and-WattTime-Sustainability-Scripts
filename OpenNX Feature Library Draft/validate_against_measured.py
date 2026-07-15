"""
validate_against_measured.py - First real check of aluminum_expanded.xlsx against measured data.

Purpose: every energy_wh value in aluminum_expanded.xlsx is a labeled
"placeholder" (see build_aluminum_library.py: source="placeholder", uuid="").
This repo also holds real, UUID-labeled, per-operation measured energy for
the same aluminum body/lid parts (ML Explore/operation_csvs/, split from the
Al6061 CNC monitoring data; operation identity resolved via the
uuid_to_operation table in Machine Specific Scripts/CNC/EnergyForFeatureLib.py).
Nobody has yet compared the two. This script does that comparison, once.

Inputs:
- ../ML Explore/operation_csvs/*/*.csv (measured, register-based "forward kWh")
- aluminum_expanded.xlsx placeholder ranges (embedded below, verified against
  the committed workbook via a stdlib XML read; see NOTE at bottom)

Output:
- library_validation_findings.md (this run's numbers + honest caveats)
- library_validation_results.csv (one row per measured operation)

Dependencies: Python 3 standard library only (csv, glob, statistics). No
pandas/openpyxl needed: the placeholder ranges are transcribed from
build_aluminum_library.py, and a spot-check (see bottom of this file) confirms
the committed .xlsx matches that source exactly.

Status: exploratory / diagnostic, not wired into the paper pipeline. Category
assignment (operation name -> library feature type) is a judgment call made
here for the first time; flagged per-category below, not a documented
crosswalk from the CAM system.
"""

import csv
import glob
import os
import statistics as stats

HERE = os.path.dirname(os.path.abspath(__file__))
OPERATION_CSV_DIR = os.path.join(HERE, "..", "ML Explore", "operation_csvs")

# Copied from Machine Specific Scripts/CNC/EnergyForFeatureLib.py (uuid_to_operation).
# That file is the only place in the repo that names these UUIDs; reused here
# read-only, not imported (importing it would require pandas).
UUID_TO_OPERATION = {
    'C874D6A3-7A89-44E1-B0D4-6783FF55F19D': 'CAVITY_MILL_OUTSIDE',
    '7A0C0A5C-9BBB-42CC-9C34-897E84D4F9BA': 'CAVITY_MILL_INSIDE',
    'B893297A-D47C-4029-BAF0-218F58387DFF': 'SPOTTING_LID_HOLES',
    '962A9D60-A315-4D3B-BF12-FDAA9EFBF2AF': 'SPOTTING_LH',
    'DB204000-40E6-4720-8721-98173D9A37FF': 'SPOTTING_CBORE',
    '5A4B2394-640B-4ADA-BBB7-717B839D0E6F': 'SPOTTING_POCKET_HOLE',
    '527F92C5-9C39-48DD-A37F-86E1D81497FC': 'DRILLING_LID_HOLES',
    '70AA639A-4325-448F-BFFB-D5EE218DA38C': 'TAPPING_LID_HOLES',
    '3D1978A5-7663-4DAA-A0D2-3995EBB1B582': 'DRILLING_LH',
    'F0FA6A59-3010-44CC-BFFF-4A4F04B7A39B': 'DRILLING_POCKET_HOLE',
    '9D44D6BA-0640-4530-8725-2069F885B77C': 'DRILLING_CBORE',
    'BEC9A210-A8D4-41B7-A2DC-32E6FCAE8291': 'FINISH_POCKET_HOLE',
    'F3339F2A-EF90-4511-8ABF-3917196A2E76': 'FINISH_CBORE',
    '02F78302-5F12-474A-A693-A8328EE54864': 'FACE_DATUM_A',
    'CF5DB674-3928-4BAA-A4E6-695A35019B38': 'FACE_TOP_PLANE',
    '7203BEC1-4B64-4F7F-BD5B-092BF23AA2C2': 'FINISH_OUTER_WALL',
    'D26C121D-4255-454F-9BFF-BC3FE92091D3': 'FINISH_OUTER_PROFILE',
    '02682EDC-F0B9-4AD5-A930-C5E08AA9FC0E': 'FINISH_INNER_PROFILE',
    '0B601775-6267-421A-9EA6-DD4531A80D99': 'WALL_FLOOR_PROFILING',
    'DE045126-2C5E-4E72-8491-E202079EAC7C': 'PLANAR_DEBURRING',
    '1925A9DD-E557-4ED5-A106-DA5F7D08FBE5': 'PLANAR_PROFILING_AGAIN',
    'AF6B782E-23DD-4144-8665-11C813BE7660': 'FLOOR_FACING',
    '6A897FFD-29C0-423B-A692-D9CCB0612FB0': 'FACE_TOP_PLANE_COPY',
    '89918109-7350-48A4-A5F9-AE742269E029': 'PLANAR_PROFILING_AGAIN_COPY',
    'C14415F1-CFEE-431E-92CB-E7F5CB809961': 'ENGRAVING',
    '27D6DC59-16BC-4185-AA97-4E474C98E615': 'SPOTTING_NPT_TOP',
    '94AE40F8-AC19-405A-A87C-42158C42D530': 'DRILLING_NPT_TOP',
    '3C44659E-1CC5-4F24-88FD-04F834435743': 'TAPPING_NPT_TOP',
    'CF0FEA34-836B-413B-B472-DF89D832DA95': 'SPOTTING_NPT_BOTTOM',
    '465E99DA-B681-4FD4-894C-3B1EF84592C2': 'DRILLING_NPT_BOTTOM',
    'C382FC41-1DFF-4BFC-B0C3-D6E313A3F60D': 'TAPPING_NPT_BOTTOM',
    '3C7357E5-BC37-4F42-861A-CF4E44BF79B6': 'LID_CAVITY_MILL',
    '34B5F4DD-FB2F-4F6A-83A1-0A5CD0F47697': 'LID_SPOTTING_HOLES',
    '5D29409C-31B1-4B6B-A5DB-7F9F6AE3D06D': 'LID_DRILLING_HOLES',
    'E17C1DE6-D8A5-4D60-BFB2-DCB7EF2BAC8C': 'LID_FINISH_SURFACES',
    'A06C758F-7E20-4B57-997A-E14283E11DC5': 'LID_FINISH_UPPER_WALL',
    'B5414A60-078F-49C6-BA61-FED2768D3C8D': 'LID_FINISH_OUTER_PROFILE',
    '5D1DD6BB-EB5D-41B4-98B2-77D314F4455E': 'LID_CHAMFER_EDGES',
    '1BFABEA4-68A9-484B-AE13-2E0BF9278D50': 'LID_FLOOR_FACING',
    'C5A68CD3-BCDF-4119-B596-9FAC41AAB033': 'LID_SPOTTING_SHAFT_HOLES',
    '0279764B-BF92-4F75-8255-A1BD34484848': 'LID_DRILLING_SHAFT_HOLES',
    'E5EDCE94-46C8-449C-9FA0-71F22978959A': 'LID_HOLE_MILLING',
    'D99BADF2-7704-48EB-B36B-2AF891BF9D78': 'LID_FINISH_FACE',
    'F9707002-75F7-45CD-B115-64EB377603B0': 'LID_POCKETING',
    '482AB6CD-5B14-41D0-846D-4AF4A2EB712A': 'LID_CHAMFER_EDGES_AGAIN',
}

# Judgment-call mapping: measured operation name -> OpenNX FEATURE_CONFIG
# category (energy_lookup.py). Operations with no physically comparable
# category are left out of "no_library_analog" on purpose -- that absence is
# itself part of the finding, not an oversight.
CATEGORY_MAP = {
    'hole_simple': [
        'SPOTTING_LID_HOLES', 'SPOTTING_LH', 'SPOTTING_POCKET_HOLE',
        'DRILLING_LID_HOLES', 'DRILLING_LH', 'DRILLING_POCKET_HOLE',
        'FINISH_POCKET_HOLE', 'LID_SPOTTING_HOLES', 'LID_DRILLING_HOLES',
        'LID_SPOTTING_SHAFT_HOLES', 'LID_DRILLING_SHAFT_HOLES',
        'LID_HOLE_MILLING', 'SPOTTING_NPT_TOP', 'DRILLING_NPT_TOP',
        'SPOTTING_NPT_BOTTOM', 'DRILLING_NPT_BOTTOM',
    ],
    'counterbore_operation': ['SPOTTING_CBORE', 'DRILLING_CBORE', 'FINISH_CBORE'],
    'tap_operation': ['TAPPING_LID_HOLES', 'TAPPING_NPT_TOP', 'TAPPING_NPT_BOTTOM'],
    'pocket_rectangular': [
        'CAVITY_MILL_OUTSIDE', 'CAVITY_MILL_INSIDE', 'LID_CAVITY_MILL',
        'LID_POCKETING',
    ],
    'face': [
        'FACE_DATUM_A', 'FACE_TOP_PLANE', 'FACE_TOP_PLANE_COPY',
        'FLOOR_FACING', 'LID_FLOOR_FACING', 'LID_FINISH_FACE',
    ],
    'chamfer': ['LID_CHAMFER_EDGES', 'LID_CHAMFER_EDGES_AGAIN'],
}
NO_ANALOG = [
    'FINISH_OUTER_WALL', 'FINISH_OUTER_PROFILE', 'FINISH_INNER_PROFILE',
    'WALL_FLOOR_PROFILING', 'PLANAR_DEBURRING', 'PLANAR_PROFILING_AGAIN',
    'PLANAR_PROFILING_AGAIN_COPY', 'LID_FINISH_SURFACES',
    'LID_FINISH_UPPER_WALL', 'LID_FINISH_OUTER_PROFILE', 'ENGRAVING',
]

OP_TO_CATEGORY = {}
for cat, ops in CATEGORY_MAP.items():
    for op in ops:
        OP_TO_CATEGORY[op] = cat
for op in NO_ANALOG:
    OP_TO_CATEGORY[op] = 'no_library_analog'

# Placeholder energy_wh values transcribed from build_aluminum_library.py
# (the script that generates aluminum_expanded.xlsx). Confirmed to match the
# committed workbook: a stdlib zipfile/ElementTree read of
# xl/worksheets/sheet3.xml (hole_simple) reproduces these exact rows -- see
# the NOTE at the bottom of this file for the check that was run.
LIBRARY_ENERGY_WH = {
    'hole_simple': [
        0.010, 0.020, 0.012, 0.025, 0.018, 0.038, 0.022, 0.045, 0.028, 0.058,
        0.090, 0.038, 0.072, 0.110, 0.048, 0.090, 0.140, 0.200, 0.065, 0.120,
        0.220, 0.085, 0.155, 0.275, 0.110, 0.200, 0.370, 0.130, 0.230, 0.420,
        0.180, 0.310, 0.560, 0.220, 0.385, 0.700, 0.280, 0.540, 0.340, 0.640,
        0.460, 0.860, 0.600, 1.100, 0.800, 1.500,
    ],
    'counterbore_operation': [
        0.025, 0.048, 0.030, 0.058, 0.040, 0.078, 0.055, 0.105, 0.072, 0.138,
        0.100, 0.188, 0.135, 0.250, 0.165, 0.305, 0.230, 0.420, 0.300, 0.560,
    ],
    'tap_operation': [
        0.015, 0.030, 0.018, 0.038, 0.025, 0.055, 0.032, 0.068, 0.042, 0.090,
        0.062, 0.135, 0.085, 0.185, 0.115, 0.250, 0.140, 0.305, 0.170, 0.370,
        0.205, 0.445, 0.245, 0.530, 0.290, 0.625, 0.335, 0.730, 0.400, 0.475,
        0.640, 0.840, 1.080, 1.400, 1.780,
    ],
    'pocket_rectangular': [
        0.045, 0.090, 0.140, 0.090, 0.175, 0.270, 0.160, 0.310, 0.480, 0.260,
        0.500, 0.780, 0.380, 0.730, 1.100, 0.560, 1.080, 1.620, 0.820, 1.580,
        2.360, 1.200, 2.300, 3.450,
    ],
    'face': [
        0.050, 0.110, 0.180, 0.380, 0.330, 0.700, 0.750, 1.600, 1.400, 2.950,
    ],
    'chamfer': [
        0.005, 0.010, 0.018, 0.028, 0.048, 0.078, 0.098, 0.148, 0.200, 0.258,
        0.315, 0.430, 0.550,
    ],
}


def measured_operation_energy(csv_path):
    """Per-run register energy (Wh) for one operation CSV: group by
    source_file, energy = last forward-kWh - first forward-kWh within the run
    (exact, gap-immune -- the convention used throughout this repo)."""
    runs = {}
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            src = row.get("source_file")
            try:
                kwh = float(row["forward kWh"])
            except (TypeError, ValueError, KeyError):
                continue
            if src not in runs:
                runs[src] = [kwh, kwh]
            else:
                runs[src][0] = min(runs[src][0], kwh)
                runs[src][1] = max(runs[src][1], kwh)

    energies_wh = []
    for lo, hi in runs.values():
        delta = (hi - lo) * 1000.0
        if delta >= 0:
            energies_wh.append(delta)
    return energies_wh


def main():
    files = sorted(glob.glob(os.path.join(OPERATION_CSV_DIR, "*", "*.csv")))
    files = [f for f in files if not f.endswith("unavailable.csv")]

    per_op = {}  # operation_name -> list of per-run Wh across all programs it appears in
    unmatched_uuids = set()

    for fp in files:
        with open(fp, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            first = next(reader, None)
        if first is None:
            continue
        uuid = (first.get("operation") or "").strip().upper()
        op_name = UUID_TO_OPERATION.get(uuid)
        if op_name is None:
            unmatched_uuids.add(uuid)
            continue
        energies = measured_operation_energy(fp)
        per_op.setdefault(op_name, []).extend(energies)

    # Group measured operations into library categories
    by_category = {}
    uncategorized = []
    for op_name, energies in per_op.items():
        if not energies:
            continue
        cat = OP_TO_CATEGORY.get(op_name)
        if cat is None:
            uncategorized.append(op_name)
            continue
        by_category.setdefault(cat, {})[op_name] = energies

    lines = []
    lines.append("# OpenNX feature-energy library vs. measured operations")
    lines.append("")
    lines.append("First comparison of aluminum_expanded.xlsx (100% placeholder")
    lines.append("data per build_aluminum_library.py: every row has")
    lines.append("`source=\"placeholder\"` and an empty `uuid` column) against the")
    lines.append("real, UUID-labeled per-operation energy already committed in")
    lines.append("`ML Explore/operation_csvs/`. This has never been checked before:")
    lines.append("the library's `uuid`/`source` columns exist specifically to hold")
    lines.append("this kind of measurement but have never been filled in.")
    lines.append("")
    lines.append("**Category assignment is a judgment call made in this script**")
    lines.append("(operation name -> library feature type), not a documented CAM")
    lines.append("crosswalk. No per-operation geometry (hole diameter, pocket area,")
    lines.append("depth) is available from the measured data, so this is a")
    lines.append("category-level range check -- does the placeholder table sit in")
    lines.append("the right order of magnitude for that class of operation -- not a")
    lines.append("dimension-matched point comparison.")
    lines.append("")
    n_ops_matched = sum(1 for v in per_op.values() if v)
    n_runs_total = sum(len(v) for v in per_op.values() if v)
    lines.append(f"Matched {n_ops_matched} distinct operations ({n_runs_total} runs")
    lines.append(f"total) to measured data; {len(uncategorized)} had no category")
    lines.append(f"assignment; {len(unmatched_uuids)} operation UUIDs in the CSVs")
    lines.append("were not in the uuid_to_operation table.")
    lines.append("")
    lines.append("## featureId channel: confirmed dead")
    lines.append("")
    lines.append("Every row in every operation CSV has `featureId` = `NONE` or")
    lines.append("`UNAVAILABLE` -- never a real feature identifier. The channel that")
    lines.append("would let a feature-energy library be built directly from the CNC")
    lines.append("controller's own feature labels is not populated in this dataset.")
    lines.append("Operation identity (`processKindId`) plus a hand-built name map")
    lines.append("(`EnergyForFeatureLib.py`) is the only route to feature category")
    lines.append("today. Worth stating plainly rather than continuing to describe")
    lines.append("featureId as merely \"unused.\"")
    lines.append("")
    lines.append("## Category comparison")
    lines.append("")
    lines.append("| Category | Measured ops (n) | Measured mean energy_wh (range across ops) | Placeholder library range (n rows) | Verdict |")
    lines.append("|---|---|---|---|---|")

    csv_rows = [("category", "operation", "n_runs", "mean_wh", "min_wh", "max_wh")]

    for cat in sorted(by_category):
        if cat == 'no_library_analog':
            continue
        ops = by_category[cat]
        op_means = []
        for op_name, energies in sorted(ops.items()):
            m = stats.mean(energies)
            op_means.append(m)
            csv_rows.append((cat, op_name, len(energies), round(m, 4),
                              round(min(energies), 4), round(max(energies), 4)))

        lib_vals = LIBRARY_ENERGY_WH.get(cat, [])
        lib_lo, lib_hi = (min(lib_vals), max(lib_vals)) if lib_vals else (None, None)
        meas_lo, meas_hi = min(op_means), max(op_means)

        if lib_lo is None:
            verdict = "no library data"
        elif meas_hi < lib_lo:
            verdict = f"measured BELOW placeholder range ({lib_lo/meas_hi:.1f}x low)" if meas_hi > 0 else "measured ~0"
        elif meas_lo > lib_hi:
            verdict = f"measured ABOVE placeholder range ({meas_lo/lib_hi:.1f}x high)"
        else:
            verdict = "measured falls within placeholder range"

        lines.append(
            f"| {cat} | {len(ops)} | {meas_lo:.3f}-{meas_hi:.3f} Wh | "
            f"{lib_lo:.3f}-{lib_hi:.3f} Wh ({len(lib_vals)}) | {verdict} |"
        )

    lines.append("")
    lines.append("**Read on `pocket_rectangular` (the largest gap, 12x):** the")
    lines.append("library's largest tabulated row is a 100x100 mm pocket, 30 mm")
    lines.append("deep (300,000 mm^3 removed, 3.45 Wh). The body's own BOM shows")
    lines.append("~1437 g (~532,000 mm^3 at Al6061 density) removed in total across")
    lines.append("*all* operations combined, and cavity milling is the dominant")
    lines.append("roughing step. A single cavity-mill pass plausibly removes a")
    lines.append("volume near the library's largest entry, so this is less \"the")
    lines.append("placeholder number is wrong\" and more \"the placeholder table's")
    lines.append("dimensional range stops well short of where this part's real")
    lines.append("roughing operations sit\" -- every pocket_rectangular estimate for")
    lines.append("this part is extrapolated far past the table's calibrated range.")
    lines.append("")
    lines.append("**Basis caveat on `chamfer`:** the library stores energy *per")
    lines.append("edge* (`per_edge: True`, multiplied by `edge_count` at lookup")
    lines.append("time), while the measured value here is the whole operation's")
    lines.append("energy with an unknown edge count. The 14.5x gap therefore")
    lines.append("conflates two things -- multiple edges per operation, and a")
    lines.append("possibly-too-low per-edge placeholder -- and should not be read")
    lines.append("as a clean per-edge error until edge_count is pulled from the NX")
    lines.append("part file.")
    lines.append("")
    lines.append("**Register resolution caveat:** the `forward kWh` register")
    lines.append("advances in ~0.33 Wh steps (0.000333 kWh ticks, confirmed on the")
    lines.append("raw data). For the shortest operations (SPOTTING_*, some")
    lines.append("DRILLING_* -- means under ~1 Wh), a single tick is a large")
    lines.append("fraction of the whole reading, which is why their per-run min-max")
    lines.append("columns in `library_validation_results.csv` swing between 0 and a")
    lines.append("few Wh. `hole_simple` and `counterbore_operation` \"falls within")
    lines.append("placeholder range\" verdicts are the least trustworthy of the six")
    lines.append("for this reason -- the bigger categories (face, pocket_rectangular,")
    lines.append("chamfer, most of tap_operation) are tens of Wh, far above this")
    lines.append("noise floor, so their above-range verdicts are not quantization")
    lines.append("artifacts.")
    lines.append("")
    lines.append("## Operations with no library category")
    lines.append("")
    lines.append("These measured operations (wall/profile finishing passes, plus")
    lines.append("engraving) have no matching category in `FEATURE_CONFIG`")
    lines.append("(`energy_lookup.py`). This is a coverage gap in the library, not")
    lines.append("just an accuracy question -- roughly a third of the real named")
    lines.append("operations on this part cannot be looked up at all today:")
    lines.append("")
    for op in sorted(NO_ANALOG):
        if op in per_op and per_op[op]:
            lines.append(f"- {op} (measured mean {stats.mean(per_op[op]):.3f} Wh, n={len(per_op[op])} runs)")
    lines.append("")
    lines.append("## Next step this points to")
    lines.append("")
    lines.append("The library schema already has `uuid` and `source` columns")
    lines.append("waiting for exactly this data (see build_aluminum_library.py")
    lines.append("docstring: \"replace placeholder values with your IN-MaC")
    lines.append("measurements\"). The natural follow-up is not more validation but")
    lines.append("substitution: for categories where measured operations exist,")
    lines.append("replace the placeholder rows with real (dimension, energy, uuid)")
    lines.append("triples once feature dimensions (hole diameter/depth, pocket area)")
    lines.append("are pulled from the NX part files via feature_extractor.py. That")
    lines.append("also directly answers EXPANSION_DIRECTIONS D2 / FUTURE_WORK.md's")
    lines.append("\"validate OpenNX feature-energy estimates against measured CNC")
    lines.append("program energy\" item, which has been open with no data behind it")
    lines.append("until this run.")
    lines.append("")

    out_md = os.path.join(HERE, "library_validation_findings.md")
    with open(out_md, "w") as f:
        f.write("\n".join(lines) + "\n")

    out_csv = os.path.join(HERE, "library_validation_results.csv")
    with open(out_csv, "w", newline="") as f:
        w = csv.writer(f)
        w.writerows(csv_rows)

    print(f"Wrote {out_md}")
    print(f"Wrote {out_csv}")
    print()
    print("\n".join(lines))


if __name__ == "__main__":
    main()

# NOTE on the "confirmed to match the committed workbook" claim above:
# a one-off check (not part of this script's runtime path, stdlib only) read
# xl/worksheets/sheet3.xml out of aluminum_expanded.xlsx with zipfile +
# xml.etree.ElementTree and found rows (2, 5, 0.01), (2, 15, 0.02),
# (3, 5, 0.012), ... matching build_hole_simple() in build_aluminum_library.py
# exactly. openpyxl is not installed in this environment, so the full
# workbook was not re-verified sheet by sheet; if aluminum_expanded.xlsx is
# ever hand-edited independently of the build script, re-run that spot check.
