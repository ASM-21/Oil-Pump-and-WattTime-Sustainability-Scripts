"""
viz.py — plotting for exploration. Pure: every function takes a prepared
DataFrame and returns a Matplotlib (fig, ax). No data loading or analysis here,
so it stays decoupled from the pipeline and is easy to restyle for your repo.

Headless-safe (Agg backend) so it runs in batch and saves to disk.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# stable color per operation type across all plots
_OP_COLORS = {
    "cutting": "#c0392b", "rapid": "#2980b9", "positioning": "#16a085",
    "tool_change": "#8e44ad", "dwell": "#7f8c8d", "drilling": "#d35400",
    "other": "#bdc3c7", "unmatched": "#ecf0f1", "air_move": "#95a5a6",
    "infill": "#27ae60",
}


def _opc(op: str) -> str:
    return _OP_COLORS.get(op, "#34495e")


def save_figure(fig, path: str | Path, dpi: int = 130) -> str:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    return str(path)


def plot_power_timeline(labeled: pd.DataFrame, value_col: str = "power_drives_sum",
                        ax=None, max_points: int = 50000):
    """Power over time, shaded by operation segment. The first thing to look at:
    it shows the run structure and lets you eyeball whether the operation
    classification and NC alignment are sane."""
    df = labeled
    if len(df) > max_points:                      # decimate for plotting only
        df = df.iloc[:: len(df) // max_points + 1]
    if ax is None:
        fig, ax = plt.subplots(figsize=(11, 3.2))
    else:
        fig = ax.figure

    t = df["t_s"].to_numpy()
    ax.plot(t, df[value_col].to_numpy(), lw=0.6, color="#2c3e50", zorder=3)

    # shade contiguous operation runs
    ops_arr = df["operation"].to_numpy()
    if len(ops_arr):
        change = np.where(ops_arr[1:] != ops_arr[:-1])[0] + 1
        bounds = [0, *change.tolist(), len(ops_arr) - 1]
        seen = set()
        for a, b in zip(bounds[:-1], bounds[1:]):
            op = ops_arr[a]
            ax.axvspan(t[a], t[b], color=_opc(op), alpha=0.22,
                       label=op if op not in seen else None, zorder=1)
            seen.add(op)
        ax.legend(loc="upper right", fontsize=7, ncol=4, framealpha=0.9)

    ax.set_xlabel("time (s)")
    ax.set_ylabel(value_col.replace("_", " ") + " (W)")
    ax.set_title("power timeline by operation")
    ax.margins(x=0)
    return fig, ax


def plot_axis_energy(axis_df: pd.DataFrame, ax=None, drop_all: bool = True):
    """Stacked bar of per-axis energy by operation. Distinctively enabled by the
    per-axis data: shows mechanically where the energy goes."""
    df = axis_df.drop(index="__all__", errors="ignore") if drop_all else axis_df
    ecols = [c for c in df.columns if c.startswith("energy_") and c != "energy_total_j"]
    if ax is None:
        fig, ax = plt.subplots(figsize=(8, 4))
    else:
        fig = ax.figure
    bottom = np.zeros(len(df))
    x = np.arange(len(df))
    for c in ecols:
        axis = c.replace("energy_", "").replace("_j", "")
        ax.bar(x, df[c].to_numpy(), bottom=bottom, label=axis)
        bottom += df[c].to_numpy()
    ax.set_xticks(x)
    ax.set_xticklabels(df.index, rotation=30, ha="right")
    ax.set_ylabel("energy (J)")
    ax.set_title("per-axis energy by operation")
    ax.legend(fontsize=8, ncol=4)
    return fig, ax


def plot_energy_share(share_df: pd.DataFrame, by: str = "operation_type", ax=None):
    """Bar of energy share by group (where the energy goes, aggregated)."""
    if ax is None:
        fig, ax = plt.subplots(figsize=(6, 4))
    else:
        fig = ax.figure
    labels = share_df[by].to_numpy()
    ax.bar(labels, share_df["share"].to_numpy(),
           color=[_opc(str(o)) for o in labels])
    ax.set_ylabel("share of total energy")
    ax.set_title(f"energy share by {by}")
    ax.set_ylim(0, 1)
    for i, v in enumerate(share_df["share"].to_numpy()):
        ax.text(i, v + 0.01, f"{v:.0%}", ha="center", fontsize=8)
    plt.setp(ax.get_xticklabels(), rotation=30, ha="right")
    return fig, ax


def plot_sampling_sweep(summary_df: pd.DataFrame, ax=None):
    """Energy error vs sampling rate, one line per meter model. The H1 picture."""
    if ax is None:
        fig, ax = plt.subplots(figsize=(7, 4))
    else:
        fig = ax.figure
    for method, g in summary_df.groupby("method"):
        g = g.sort_values("rate_hz")
        ax.plot(g["rate_hz"], g["worst_abs_error_pct"], marker="o", label=method)
    ax.axhline(1.0, color="grey", ls="--", lw=0.8, label="1% error")
    ax.set_xscale("log")
    ax.set_xlabel("sampling rate (Hz)")
    ax.set_ylabel("worst-case energy error (%)")
    ax.set_title("energy error vs sampling rate (corpus)")
    ax.legend(fontsize=8)
    return fig, ax


def plot_repeatability(per_exp: pd.DataFrame, ax=None):
    """Per-part energy bar, colored by material. Shows part-to-part spread."""
    if ax is None:
        fig, ax = plt.subplots(figsize=(8, 4))
    else:
        fig = ax.figure
    mats = sorted(per_exp["material"].unique())
    cmap = {m: plt.cm.tab10(i) for i, m in enumerate(mats)}
    x = np.arange(len(per_exp))
    ax.bar(x, per_exp["energy_j"].to_numpy(),
           color=[cmap[m] for m in per_exp["material"]])
    ax.set_xticks(x)
    ax.set_xticklabels(per_exp["experiment"], rotation=45, ha="right", fontsize=7)
    ax.set_ylabel("total energy (J)")
    ax.set_title("energy per experiment")
    handles = [plt.Rectangle((0, 0), 1, 1, color=cmap[m]) for m in mats]
    ax.legend(handles, mats, fontsize=8)
    return fig, ax


def plot_sec_distribution(store_frame: pd.DataFrame, by: str = "material",
                          metric: str = "sec_marginal", ax=None):
    """Strip/box of per-operation SEC by group (e.g. material), cutting only."""
    df = store_frame[(store_frame["operation_type"] == "cutting")
                     & store_frame[metric].notna()]
    if ax is None:
        fig, ax = plt.subplots(figsize=(6, 4))
    else:
        fig = ax.figure
    groups = sorted(df[by].unique())
    data = [df.loc[df[by] == grp, metric].to_numpy() for grp in groups]
    if any(len(d) for d in data):
        ax.boxplot(data, labels=groups, showfliers=False)
        for i, d in enumerate(data, start=1):
            ax.scatter(np.full(len(d), i) + np.random.uniform(-0.08, 0.08, len(d)),
                       d, s=18, alpha=0.6, zorder=3)
    ax.set_ylabel(metric.replace("_", " ") + " (J/mm^3)")
    ax.set_title(f"cutting SEC by {by}")
    return fig, ax


def plot_feature_correlations(corr_df: pd.DataFrame, target: str = "energy_j",
                              top: int = 12, ax=None):
    """Horizontal bar of feature correlations with the target, strongest first.
    corr_df from features.feature_correlations."""
    if ax is None:
        fig, ax = plt.subplots(figsize=(7, 5))
    else:
        fig = ax.figure
    d = corr_df.head(top).iloc[::-1]
    colors = ["#c0392b" if v < 0 else "#2980b9" for v in d["correlation"]]
    ax.barh(d["feature"], d["correlation"], color=colors)
    ax.axvline(0, color="black", lw=0.8)
    ax.set_xlim(-1, 1)
    ax.set_xlabel(f"Spearman correlation with {target}")
    ax.set_title("structure/geometry vs energy")
    for i, (v, n) in enumerate(zip(d["correlation"], d["n"])):
        ax.text(v + (0.03 if v >= 0 else -0.03), i, f"n={n}",
                va="center", ha="left" if v >= 0 else "right", fontsize=7)
    return fig, ax


def plot_feature_vs_target(table: pd.DataFrame, feature: str,
                           target: str = "energy_j", ax=None):
    """Scatter of one feature against the target, with a fitted trend line."""
    d = table[[feature, target]].dropna()
    if ax is None:
        fig, ax = plt.subplots(figsize=(5.5, 4.5))
    else:
        fig = ax.figure
    ax.scatter(d[feature], d[target], s=40, alpha=0.8, color="#34495e", zorder=3)
    if len(d) >= 2 and d[feature].nunique() >= 2:
        b, a = np.polyfit(d[feature], d[target], 1)
        xs = np.linspace(d[feature].min(), d[feature].max(), 50)
        ax.plot(xs, a + b * xs, color="#c0392b", lw=1.2, zorder=2)
    ax.set_xlabel(feature)
    ax.set_ylabel(target)
    ax.set_title(f"{target} vs {feature}")
    return fig, ax


def dashboard(labeled, axis_df, energy_share_df, sweep_summary,
              per_exp, out_path: str | Path):
    """Compose the key panels into one figure and save it."""
    fig = plt.figure(figsize=(14, 9))
    gs = fig.add_gridspec(3, 2, height_ratios=[1, 1, 1])

    plot_power_timeline(labeled, ax=fig.add_subplot(gs[0, :]))
    plot_axis_energy(axis_df, ax=fig.add_subplot(gs[1, 0]))
    plot_energy_share(energy_share_df, ax=fig.add_subplot(gs[1, 1]))
    plot_sampling_sweep(sweep_summary, ax=fig.add_subplot(gs[2, 0]))
    plot_repeatability(per_exp, ax=fig.add_subplot(gs[2, 1]))

    fig.suptitle("dataset exploration dashboard", fontsize=13)
    fig.tight_layout(rect=[0, 0, 1, 0.98])
    return save_figure(fig, out_path)
