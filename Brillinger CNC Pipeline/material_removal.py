"""
Z-map material removal simulation for per-operation SEC.

Per-operation specific cutting energy needs removed volume per operation. The
NC code does not carry axial depth or radial width, so volume cannot be derived
by formula for general toolpaths. This module runs a heightfield (Z-map / dexel)
simulation of the stock: each cutting move sweeps its tool through the surface,
and removed volume is the resulting height decrease. Radial width and depth
emerge from the material state rather than being assumed.

SCOPE AND ACCURACY (read before citing numbers)
------------------------------------------------
- 3-axis only. The heightfield is a top-down z(x,y) surface. It is valid when
  the rotary axes B1, C1 are ~0 (the Brillinger descriptor states they
  typically are). True 5-axis cuts with a tilted tool are not represented.
- A heightfield cannot represent undercuts or overhangs. Side-milling a vertical
  wall, or any feature where material exists below removed material, is not
  captured. Good for 2.5D pocketing, facing, drilling, and 3-axis surfacing.
- Tool modeled as a flat-bottomed cylinder by default. Ball-nose tip geometry is
  approximated as flat, which slightly overestimates removal near the tip on
  finishing passes. A ball option is provided.
- Drill tip cone is ignored (cylinder approximation); error is one tool radius of
  depth per hole, negligible for deep holes.
- Rasterization introduces a few-percent error that shrinks with finer `res`.

Always reconcile: total simulated removal should match (stock - final part)
volume from the STL within tolerance. `simulate_removal` reports the residual.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

import brillinger_pipeline as bp


# ---------------------------------------------------------------------------
# Tool table
# ---------------------------------------------------------------------------

def load_tool_table(xlsx_path: str | Path,
                    id_col: Optional[str] = None,
                    dia_col: Optional[str] = None) -> dict:
    """Best-effort load of a tool list xlsx into {tool_id: {diameter, type}}.

    The real column names are unverified, so detection is heuristic: a column
    whose header contains 'T'/'tool'/'no' for the id, and one containing 'dia'
    or 'D' for diameter. If detection fails, pass id_col / dia_col explicitly,
    or skip this and supply a manual dict to simulate_removal.
    """
    df = pd.read_excel(xlsx_path)
    cols = {c.lower(): c for c in df.columns}

    def _find(cands):
        for key, orig in cols.items():
            if any(c in key for c in cands):
                return orig
        return None

    id_col = id_col or _find(["tool no", "tool_id", "t-no", "tool", "no"])
    dia_col = dia_col or _find(["diameter", "dia", "d_w", "ø", "durchmesser"])
    type_col = _find(["type", "art", "kind"])

    if id_col is None or dia_col is None:
        warnings.warn(f"could not auto-detect tool columns from {list(df.columns)}; "
                      "pass id_col/dia_col or supply a manual tool dict.")
        return {}

    table = {}
    for _, row in df.iterrows():
        try:
            tid = int(float(row[id_col]))
        except (ValueError, TypeError):
            continue
        table[tid] = {
            "diameter": float(row[dia_col]),
            "type": str(row[type_col]) if type_col else "",
        }
    return table


# ---------------------------------------------------------------------------
# Heightfield
# ---------------------------------------------------------------------------

@dataclass
class ZMap:
    """Top-down stock heightfield on a regular XY grid.

    Cells store the current top-surface z. Cutting lowers cells the tool passes
    over to the tool-bottom z; removed volume is the summed height decrease.
    """
    xmin: float
    xmax: float
    ymin: float
    ymax: float
    top_z: float
    bottom_z: float
    res: float = 0.25            # mm per cell

    def __post_init__(self):
        self.nx = max(1, int(np.ceil((self.xmax - self.xmin) / self.res)))
        self.ny = max(1, int(np.ceil((self.ymax - self.ymin) / self.res)))
        self.cell_area = self.res * self.res
        self.h = np.full((self.ny, self.nx), float(self.top_z))
        # cell-center coordinates
        self._xs = self.xmin + (np.arange(self.nx) + 0.5) * self.res
        self._ys = self.ymin + (np.arange(self.ny) + 0.5) * self.res

    def _stamp_disk(self, cx: float, cy: float, radius: float, z: float,
                    ball: bool = False) -> float:
        """Lower all cells within `radius` of (cx,cy) to z (or a ball profile).

        Returns volume removed by this stamp (mm^3). Idempotent: re-stamping the
        same region at the same z removes nothing, so overlapping stamps along a
        path union correctly without double counting.
        """
        z = max(z, self.bottom_z)
        # bounding box of the disk in cell indices
        i0 = max(0, int((cx - radius - self.xmin) / self.res))
        i1 = min(self.nx, int(np.ceil((cx + radius - self.xmin) / self.res)))
        j0 = max(0, int((cy - radius - self.ymin) / self.res))
        j1 = min(self.ny, int(np.ceil((cy + radius - self.ymin) / self.res)))
        if i0 >= i1 or j0 >= j1:
            return 0.0

        xs = self._xs[i0:i1]
        ys = self._ys[j0:j1]
        dx = xs[None, :] - cx
        dy = ys[:, None] - cy
        r2 = dx * dx + dy * dy
        mask = r2 <= radius * radius
        if not mask.any():
            return 0.0

        sub = self.h[j0:j1, i0:i1]
        if ball:
            # ball-nose: floor rises toward the rim by r - sqrt(r^2 - d^2)
            rise = radius - np.sqrt(np.maximum(radius * radius - r2, 0.0))
            target = z + rise
        else:
            target = np.full_like(sub, z)

        new = np.where(mask, np.minimum(sub, target), sub)
        removed = float(np.sum((sub - new)) * self.cell_area)
        self.h[j0:j1, i0:i1] = new
        return removed

    def sweep_segment(self, p0, p1, radius: float, ball: bool = False) -> float:
        """Sweep the tool from p0 to p1, stamping along the path. Handles ramps
        in Z by interpolating the tool-bottom z along the segment."""
        x0, y0, z0 = p0
        x1, y1, z1 = p1
        length_xy = float(np.hypot(x1 - x0, y1 - y0))
        # sub-step fine enough that consecutive disks overlap
        step = max(self.res, radius / 2.0)
        n = max(1, int(np.ceil(length_xy / step)))
        removed = 0.0
        for k in range(n + 1):
            t = k / n
            cx = x0 + t * (x1 - x0)
            cy = y0 + t * (y1 - y0)
            cz = z0 + t * (z1 - z0)
            removed += self._stamp_disk(cx, cy, radius, cz, ball=ball)
        return removed

    def total_removed(self) -> float:
        return float(np.sum(self.top_z - self.h) * self.cell_area)


# ---------------------------------------------------------------------------
# Arc handling
# ---------------------------------------------------------------------------

def _arc_polyline(block, n_seg: int = 24):
    """Approximate a G2/G3 arc as a list of (x,y,z) points.

    Supports incremental center (I,J relative to start) and CR= radius. Falls
    back to a straight chord if the arc cannot be resolved, logging once.
    """
    x0, y0 = block["x0"], block["y0"]
    x1, y1 = block["x1"], block["y1"]
    z0, z1 = block["z0"], block["z1"]
    cw = block["motion"] == "G2"

    cx = cy = None
    if block.get("I") is not None or block.get("J") is not None:
        cx = x0 + (block.get("I") or 0.0)
        cy = y0 + (block.get("J") or 0.0)
    elif block.get("CR") is not None:
        # midpoint-offset construction from radius (sign of CR picks the minor/
        # major arc in Sinumerik; we take the minor arc here)
        r = abs(block["CR"])
        mx, my = (x0 + x1) / 2.0, (y0 + y1) / 2.0
        dx, dy = x1 - x0, y1 - y0
        chord = np.hypot(dx, dy)
        if chord == 0 or chord > 2 * r:
            return [(x0, y0, z0), (x1, y1, z1)]
        h = np.sqrt(max(r * r - (chord / 2) ** 2, 0.0))
        ox, oy = -dy / chord, dx / chord
        sign = -1.0 if cw else 1.0
        cx, cy = mx + sign * h * ox, my + sign * h * oy

    if cx is None:
        return [(x0, y0, z0), (x1, y1, z1)]

    a0 = np.arctan2(y0 - cy, x0 - cx)
    a1 = np.arctan2(y1 - cy, x1 - cx)
    r = np.hypot(x0 - cx, y0 - cy)
    if cw and a1 > a0:
        a1 -= 2 * np.pi
    if not cw and a1 < a0:
        a1 += 2 * np.pi

    pts = []
    for k in range(n_seg + 1):
        t = k / n_seg
        a = a0 + t * (a1 - a0)
        pts.append((cx + r * np.cos(a), cy + r * np.sin(a), z0 + t * (z1 - z0)))
    return pts


# ---------------------------------------------------------------------------
# Simulation driver
# ---------------------------------------------------------------------------

def simulate_removal(nc_df: pd.DataFrame,
                     tools: dict,
                     stock_dims_mm: tuple = bp.STOCK_DIMS_MM,
                     stock_origin: str = "corner",
                     res: float = 0.25,
                     ball_types=("ball",),
                     part_volume_mm3: Optional[float] = None) -> dict:
    """Run the Z-map over all cutting blocks and aggregate removed volume.

    Parameters
    ----------
    nc_df : output of bp.parse_mpf (must include x0..z1 position columns).
    tools : {tool_id: {'diameter': mm, 'type': str}}.
    stock_origin : 'corner' (stock spans [0,L] in X and Y, top at z=0, extends
        down by thickness) or 'center' (stock centered on XY origin). Adjust to
        match the program's work-coordinate setup.
    part_volume_mm3 : final part solid volume, e.g. from
        bp.mesh_volume_mm3(stl). If given, the reconciliation residual is
        reported against (stock - part).

    Returns dict with per-block volume, per-operation volume, totals, and the
    reconciliation residual.
    """
    needed = {"x0", "y0", "z0", "x1", "y1", "z1"}
    if not needed.issubset(nc_df.columns):
        raise ValueError("nc_df lacks position columns; re-run parse_mpf from "
                         "the updated pipeline.")

    lx, ly, lz = stock_dims_mm
    if stock_origin == "corner":
        xmin, xmax, ymin, ymax = 0.0, lx, 0.0, ly
    elif stock_origin == "center":
        xmin, xmax, ymin, ymax = -lx / 2, lx / 2, -ly / 2, ly / 2
    else:
        raise ValueError("stock_origin must be corner|center")
    top_z, bottom_z = 0.0, -lz   # convention: stock top at z=0

    zmap = ZMap(xmin, xmax, ymin, ymax, top_z, bottom_z, res=res)

    vols = np.zeros(len(nc_df))
    missing_tool = set()
    unresolved_arcs = 0

    cutting = nc_df[nc_df["operation"] == "cutting"]
    for idx, blk in cutting.iterrows():
        tid = blk["T"]
        try:
            tid_int = int(tid)
        except (ValueError, TypeError):
            tid_int = None
        tool = tools.get(tid_int)
        if tool is None:
            missing_tool.add(tid)
            continue
        radius = tool["diameter"] / 2.0
        ball = any(b in tool.get("type", "").lower() for b in ball_types)

        if None in (blk["x0"], blk["y0"], blk["z0"], blk["x1"], blk["y1"], blk["z1"]):
            continue

        if blk["motion"] in ("G2", "G3"):
            pts = _arc_polyline(blk)
            if len(pts) == 2 and blk.get("I") is None and blk.get("CR") is None:
                unresolved_arcs += 1
            seg_removed = 0.0
            for a, b in zip(pts[:-1], pts[1:]):
                seg_removed += zmap.sweep_segment(a, b, radius, ball=ball)
            vols[nc_df.index.get_loc(idx)] = seg_removed
        else:
            vols[nc_df.index.get_loc(idx)] = zmap.sweep_segment(
                (blk["x0"], blk["y0"], blk["z0"]),
                (blk["x1"], blk["y1"], blk["z1"]),
                radius, ball=ball,
            )

    out = nc_df.copy()
    out["removed_volume_mm3"] = vols

    by_op = (out.groupby("operation")["removed_volume_mm3"].sum()
             .rename("volume_mm3").to_frame())
    total_sim = float(vols.sum())

    result = {
        "per_block": out,
        "by_operation": by_op,
        "total_removed_mm3": total_sim,
        "zmap": zmap,
    }

    if missing_tool:
        warnings.warn(f"no tool entry for tool ids {missing_tool}; their cuts "
                      "contributed zero volume. Add them to the tool dict.")
    if unresolved_arcs:
        warnings.warn(f"{unresolved_arcs} arc blocks lacked I/J or CR and were "
                      "treated as straight chords.")

    if part_volume_mm3 is not None:
        stock_vol = lx * ly * lz
        expected = stock_vol - part_volume_mm3
        residual = total_sim - expected
        result["reconciliation"] = {
            "stock_mm3": stock_vol,
            "part_mm3": part_volume_mm3,
            "expected_removed_mm3": expected,
            "simulated_removed_mm3": total_sim,
            "residual_mm3": residual,
            "residual_pct": 100.0 * residual / expected if expected else np.nan,
        }
    return result


def per_operation_sec(energy_by_op: pd.DataFrame,
                      volume_by_op: pd.DataFrame,
                      energy_col: str = "energy_j",
                      volume_col: str = "volume_mm3") -> pd.DataFrame:
    """Join per-operation energy and volume into SEC (J/mm^3).

    Energy from bp.align_and_integrate()['by_operation'], volume from
    simulate_removal()['by_operation']. SEC is reported only where removed
    volume is positive (rapids, tool changes, dwell have none and are NaN).
    """
    df = energy_by_op[[energy_col]].join(volume_by_op[[volume_col]], how="outer")
    df["sec_j_per_mm3"] = np.where(
        df[volume_col].fillna(0) > 0,
        df[energy_col] / df[volume_col],
        np.nan,
    )
    flag = (df["sec_j_per_mm3"] < 0.1) | (df["sec_j_per_mm3"] > 100)
    df["sec_plausible"] = ~flag & df["sec_j_per_mm3"].notna()
    return df
