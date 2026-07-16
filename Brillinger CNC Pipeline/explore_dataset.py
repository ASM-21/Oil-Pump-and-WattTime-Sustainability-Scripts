"""
explore_dataset.py — one command to explore the whole dataset.

Chains: manifest -> schema inspection -> corpus run -> characterization ->
per-axis energy -> sampling sweep -> plots + a saved report. Run this on the
real download once the channel map is confirmed.

    python explore_dataset.py /path/to/brillinger --out ./exploration
    python explore_dataset.py /path/to/brillinger --inspect-only
    python explore_dataset.py /path/to/brillinger --volume --tools tools.json

--volume turns on the Z-map (needs --tools, a JSON of {tool_id: {diameter,type}}).
Without it, energy and per-axis breakdowns run but SEC is left blank.
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import pandas as pd

import config as C
import dataset_explorer as dx
import signals as sig
import viz

log = logging.getLogger("explore")


def _first_complete(manifest: pd.DataFrame):
    comp = manifest[manifest["complete"]]
    return comp.iloc[0] if len(comp) else None


def main(argv=None):
    p = argparse.ArgumentParser(description="Explore a CNC energy dataset")
    p.add_argument("dataset_root")
    p.add_argument("--config", default="brillinger",
                   choices=["brillinger", "inmac"],
                   help="which DatasetConfig to use")
    p.add_argument("--out", default="./exploration")
    p.add_argument("--cache", default=None)
    p.add_argument("--volume", action="store_true",
                   help="compute removed volume via the Z-map (needs --tools)")
    p.add_argument("--tools", default=None,
                   help="JSON file: {tool_id: {diameter, type}}")
    p.add_argument("--nc-key", default="n_number",
                   choices=["n_number", "line_number", "file_line", "block_index"])
    p.add_argument("--inspect-only", action="store_true",
                   help="stop after the manifest and schema inspection")
    p.add_argument("--max-parts", type=int, default=None)
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(name)s %(levelname)s %(message)s")

    cfg = {"brillinger": C.BRILLINGER, "inmac": C.INMAC}[args.config]
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    # 1. manifest
    log.info("building manifest for %s", args.dataset_root)
    manifest = dx.build_manifest(args.dataset_root, cfg, count_samples=True)
    manifest.to_csv(out / "manifest.csv", index=False)
    log.info("manifest: %d experiments, %d complete", len(manifest),
             int(manifest["complete"].sum()) if "complete" in manifest else 0)

    # 2. schema inspection on the first complete experiment
    first = _first_complete(manifest)
    if first is None:
        log.error("no complete experiments (need energy + NC). stopping.")
        return
    log.info("inspecting schema: %s", first["energy_path"])
    schema = dx.bp.inspect_json(first["energy_path"])
    (out / "schema_first_file.json").write_text(json.dumps(schema, indent=2, default=str))

    if args.inspect_only:
        log.info("inspect-only: stopping. Confirm the channel map against the "
                 "schema above before a full run.")
        return

    tools = None
    if args.volume:
        if not args.tools:
            log.error("--volume needs --tools; running without volume.")
        else:
            tools = {int(k): v for k, v in json.loads(Path(args.tools).read_text()).items()}

    # 3. corpus run
    res = dx.corpus_run(manifest, cfg, cache_dir=args.cache, nc_key=args.nc_key,
                        compute_volume=bool(tools), tools=tools)
    store, per_exp, prov = res["store"], res["per_experiment"], res["provenance"]
    per_exp.to_csv(out / "per_experiment.csv", index=False)
    (out / "provenance.json").write_text(json.dumps(prov.as_dict(), indent=2))
    if res["failures"]:
        pd.DataFrame(res["failures"]).to_csv(out / "failures.csv", index=False)
    log.info("processed %d/%d experiments", prov.n_processed, prov.n_experiments)

    # 4. characterization
    ch = dx.characterize_corpus(store, per_exp)
    for name, obj in ch.items():
        if isinstance(obj, pd.DataFrame):
            obj.to_csv(out / f"char_{name}.csv", index=False)

    # 4b. structure + geometry feature table, correlated with energy
    import nc_features
    import geometry
    import features as feat
    nc_cx = nc_features.corpus_nc_complexity(manifest, cfg, max_parts=args.max_parts)
    geo = geometry.corpus_geometry(manifest, cfg, max_parts=args.max_parts)
    if not nc_cx.empty:
        nc_cx.to_csv(out / "nc_complexity.csv", index=False)
    if not geo.empty:
        geo.to_csv(out / "geometry.csv", index=False)
    table = feat.build_feature_table(per_exp, nc_cx if not nc_cx.empty else None,
                                     geo if not geo.empty else None)
    table.to_csv(out / "feature_table.csv", index=False)
    corr = feat.feature_correlations(table, target="energy_j")
    if not corr.empty:
        corr.to_csv(out / "feature_correlations.csv", index=False)
        log.info("top energy correlate: %s (rho=%.2f, n=%d)",
                 corr.iloc[0]["feature"], corr.iloc[0]["correlation"], corr.iloc[0]["n"])

    # 5. per-axis energy on the first experiment (illustrative)
    power = dx.bp.load_power_json(first["energy_path"],
                                 cmap=dx.channel_map_from_config(cfg))
    nc = dx.bp.parse_mpf(first["nc_path"])
    axis_df = sig.axis_energy_breakdown(power, nc, cfg, nc_key=args.nc_key)
    axis_df.to_csv(out / "axis_energy_first.csv")
    labeled = sig.label_samples(power, nc, cfg, nc_key=args.nc_key)

    # 6. corpus sampling sweep (H1)
    sweep = sig.corpus_sampling_sweep(manifest, cfg, max_parts=args.max_parts)
    if not sweep["summary"].empty:
        sweep["summary"].to_csv(out / "sampling_sweep.csv", index=False)

    # 6b. anomaly + drift pass
    import anomalies as anom
    an = anom.run_all(store, per_exp, manifest, cfg, max_parts=args.max_parts)
    for name, tbl in an.items():
        obj = tbl.get("flags") if isinstance(tbl, dict) else tbl
        if isinstance(obj, pd.DataFrame) and not obj.empty:
            obj.to_csv(out / f"anom_{name}.csv", index=False)

    # 7. plots
    figs = out / "figures"
    try:
        viz.save_figure(viz.plot_power_timeline(labeled)[0], figs / "timeline.png")
        viz.save_figure(viz.plot_axis_energy(axis_df)[0], figs / "axis_energy.png")
        if "energy_share_by_operation" in ch:
            viz.save_figure(viz.plot_energy_share(ch["energy_share_by_operation"])[0],
                            figs / "energy_share.png")
        if not sweep["summary"].empty:
            viz.save_figure(viz.plot_sampling_sweep(sweep["summary"])[0],
                            figs / "sampling_sweep.png")
        if not per_exp.empty:
            viz.save_figure(viz.plot_repeatability(per_exp)[0], figs / "repeatability.png")
            viz.dashboard(labeled, axis_df, ch.get("energy_share_by_operation"),
                          sweep["summary"], per_exp, figs / "dashboard.png")
        if not corr.empty:
            viz.save_figure(viz.plot_feature_correlations(corr)[0],
                            figs / "feature_correlations.png")
            top_feat = corr.iloc[0]["feature"]
            viz.save_figure(viz.plot_feature_vs_target(table, top_feat)[0],
                            figs / f"energy_vs_{top_feat}.png")
        log.info("figures written to %s", figs)
    except Exception as exc:  # noqa: BLE001
        log.warning("plotting step failed: %s", exc)

    # 8. self-contained HTML report
    try:
        import report as rpt
        flags = {k: (v.get("flags") if isinstance(v, dict) else v)
                 for k, v in an.items()}
        context = {
            "provenance": prov.as_dict(),
            "manifest": manifest,
            "per_experiment": per_exp,
            "characterization": ch,
            "sampling_summary": sweep["summary"],
            "feature_correlations": corr,
            "feature_table": table,
            "anomalies": flags,
            "figures": {
                "dashboard": figs / "dashboard.png",
                "power timeline": figs / "timeline.png",
                "per-axis energy": figs / "axis_energy.png",
                "sampling sweep": figs / "sampling_sweep.png",
                "feature correlations": figs / "feature_correlations.png",
            },
        }
        report_path = rpt.generate_report(context, out / "report.html")
        log.info("report written to %s", report_path)
    except Exception as exc:  # noqa: BLE001
        log.warning("report generation failed: %s", exc)

    log.info("done. outputs in %s", out)


if __name__ == "__main__":
    main()
