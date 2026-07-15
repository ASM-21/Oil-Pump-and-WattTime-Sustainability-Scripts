"""
Validate nc_features, geometry, features, and the extended entry-point.

Checks:
  - NC complexity matches the known synthetic program (block/tool counts,
    cutting distance computed from coordinates)
  - geometry features recover a box's volume and bounding box exactly
  - feature table joins NC + geometry + energy on experiment
  - correlations run and rank features against energy
  - the new plots render; the entry-point produces the feature artifacts
"""

import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd
import trimesh

import config as C
import dataset_explorer as dx
import nc_features as ncf
import geometry as geo
import features as feat
import viz
import explore_dataset

logging.basicConfig(level=logging.WARNING)

MPF = """; part
N10 G90 G54
N20 T1 M6
N30 S6000 M3 F600
N40 G0 X10 Y10 Z2
N50 G1 Z-3 F300
N60 G1 X50 Y10 F600
N70 G0 Z20
N80 M5
N90 M30
"""
LINE_W = {10: 300, 20: 1000, 30: 700, 40: 500, 50: 1400, 60: 1400,
          70: 500, 80: 700, 90: 300}


def write_part(folder, eid, scale, box_dims):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{eid}.mpf").write_text(MPF)
    counter, p_sp, p_x = [], [], []
    for ln, w in LINE_W.items():
        w *= scale
        for _ in range(500):
            counter.append(ln); p_sp.append(w*0.8); p_x.append(w*0.2)
    n = len(counter)
    json.dump({"CYCLE": counter, "POWER|1": p_x, "POWER|2": [0.0]*n,
               "POWER|3": [0.0]*n, "POWER|4": [0.0]*n, "POWER|5": [0.0]*n,
               "POWER|6": p_sp, "POWER|7": [0.0]*n}, open(folder/f"{eid}.json", "w"))
    # a box STL of known volume
    box = trimesh.creation.box(extents=box_dims)
    box.export(folder / f"{eid}.stl")


def main():
    root = Path("feat_demo")
    # three parts with different box sizes so geometry features vary
    write_part(root/"a1", "a1", 1.0, (20, 10, 5))
    write_part(root/"a2", "a2", 1.1, (24, 12, 6))
    write_part(root/"b1", "b1", 1.6, (40, 18, 10))
    cfg = C.BRILLINGER
    man = dx.build_manifest(root, cfg)
    man.loc[man["experiment"] == "b1", "material"] = "Al6061-T6"

    print("=" * 60, "\n[A] NC complexity vs known program")
    nc = dx.bp.parse_mpf(str(root/"a1"/"a1.mpf"))
    cx = ncf.nc_complexity(nc)
    print(cx.to_string())
    # expected: 2 cutting blocks (N50 plunge, N60 slot), 1 tool change, 1 tool.
    # cutting distance: N50 plunge z 2->-3 = 5mm; N60 X10->50 = 40mm; total 45.
    ok_counts = cx["n_cutting_blocks"] == 2 and cx["n_tool_changes"] == 1 and cx["n_tools"] == 1
    ok_dist = np.isclose(cx["cutting_distance_mm"], 45.0)
    print(f"\n  counts (2 cut, 1 toolchange, 1 tool): {ok_counts}")
    print(f"  cutting distance 45 mm: {ok_dist} ({cx['cutting_distance_mm']:.1f})")

    print("\n" + "=" * 60, "\n[B] geometry vs known box")
    g = geo.geometry_features(str(root/"a1"/"a1.stl"))
    print({k: round(v, 2) if isinstance(v, float) else v for k, v in g.items()})
    # box 20x10x5 -> volume 1000, bbox extents 20,10,5
    ok_vol = np.isclose(g["volume_mm3"], 1000.0, rtol=1e-3)
    ok_bbox = np.isclose(g["bbox_x_mm"], 20) and np.isclose(g["bbox_z_mm"], 5)
    ok_sv = np.isclose(g["sv_ratio_per_mm"], g["surface_area_mm2"]/1000.0)
    print(f"\n  volume 1000 mm^3: {ok_vol}  bbox 20x_x5: {ok_bbox}  sv ratio: {ok_sv}")

    print("\n" + "=" * 60, "\n[C] feature table join + correlations")
    res = dx.corpus_run(man, cfg)
    nc_cx = ncf.corpus_nc_complexity(man, cfg)
    geo_df = geo.corpus_geometry(man, cfg)
    table = feat.build_feature_table(res["per_experiment"], nc_cx, geo_df)
    print("table columns:", list(table.columns))
    print(table[["experiment", "energy_j", "n_cutting_blocks",
                 "bbox_volume_mm3", "sv_ratio_per_mm"]].to_string(index=False))
    has_join = "n_cutting_blocks" in table.columns and "bbox_volume_mm3" in table.columns
    corr = feat.feature_correlations(table, target="energy_j")
    print("\ncorrelations with energy:")
    print(corr.to_string(index=False))
    ok_feat = has_join and not corr.empty

    print("\n" + "=" * 60, "\n[D] new plots render")
    figs = Path("feat_figs")
    p1 = viz.save_figure(viz.plot_feature_correlations(corr)[0], figs/"corr.png")
    top = corr.iloc[0]["feature"]
    p2 = viz.save_figure(viz.plot_feature_vs_target(table, top)[0], figs/"scatter.png")
    sizes = [Path(p).stat().st_size for p in (p1, p2)]
    ok_plots = all(s > 1000 for s in sizes)
    print(f"  corr.png, scatter.png sizes: {sizes}  ok: {ok_plots}")

    print("\n" + "=" * 60, "\n[E] entry-point produces feature artifacts")
    outdir = Path("feat_out")
    explore_dataset.main([str(root), "--out", str(outdir), "--cache", "feat_cache"])
    want = ["feature_table.csv", "feature_correlations.csv", "nc_complexity.csv",
            "geometry.csv"]
    present = {f: (outdir/f).exists() for f in want}
    fig_ok = (outdir/"figures"/"feature_correlations.png").exists()
    print("  ", present, "| corr fig:", fig_ok)
    ok_cli = all(present.values()) and fig_ok

    results = {"nc_complexity": bool(ok_counts and ok_dist),
               "geometry": bool(ok_vol and ok_bbox and ok_sv),
               "feature_table": bool(ok_feat), "plots": bool(ok_plots),
               "entry_point": bool(ok_cli)}
    print("\n" + "=" * 60)
    print("RESULTS:", results)
    print("ALL PASS:", all(results.values()))


if __name__ == "__main__":
    main()
