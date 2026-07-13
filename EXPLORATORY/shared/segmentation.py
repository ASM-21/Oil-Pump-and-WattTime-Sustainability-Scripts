"""
UUID-free segmentation of a 1 Hz power stream.

WHY THIS EXISTS
The paper's attribution method relies on CAM-originated UUIDs riding along
with the power stream. Most installed machines have no such integration. If
operation boundaries can be recovered from the power signal alone, the
attribution method generalizes to retrofit settings. This module provides:

  1. detect_changepoints() - offline binary segmentation on mean shift with a
     BIC-style penalty. Deliberately simple (numpy only, no ruptures/sklearn):
     the claim to defend is "a basic detector suffices at 1 Hz", which is
     stronger and more reproducible than tuning an exotic one.
  2. boundary_recovery() - precision/recall/F1 of detected boundaries against
     reference boundaries (from UUIDs or fixture truth) within a tolerance.
  3. classify_states() - sample-level machine-state decomposition
     (off/idle/positioning/cutting) from power thresholds, for the
     machine-state view that operation boundaries alone do not give.

All functions take plain numpy arrays so they are machine-agnostic: nothing
here knows about parts, programs, or the oil pump.
"""

from __future__ import annotations

import numpy as np

__all__ = [
    "detect_changepoints",
    "boundary_recovery",
    "classify_states",
    "segment_table",
]


# ---------------------------------------------------------------------------
# Changepoint detection
# ---------------------------------------------------------------------------

def _segment_cost(prefix: np.ndarray, prefix_sq: np.ndarray, i: int, j: int) -> float:
    """Sum of squared deviations from the mean for samples [i, j) in O(1),
    using prefix sums. This is the within-segment cost for a mean-shift model."""
    n = j - i
    if n <= 0:
        return 0.0
    s = prefix[j] - prefix[i]
    ss = prefix_sq[j] - prefix_sq[i]
    return float(ss - s * s / n)


def detect_changepoints(
    power_w: np.ndarray,
    min_seg_len: int = 10,
    penalty: float | None = None,
    max_changepoints: int = 200,
) -> list[int]:
    """
    Detect mean-shift changepoints by recursive binary segmentation.

    A split at t inside [i, j) is accepted when it reduces the within-segment
    squared error by more than `penalty`. Default penalty is the BIC-style
    2 * noise_var * log(n), with noise_var estimated robustly from first
    differences (median absolute difference), which is insensitive to the
    level shifts we are trying to detect.

    Returns sorted interior boundary indices (a boundary at k means segments
    [.., k) and [k, ..)). Endpoints are not included.
    """
    x = np.asarray(power_w, dtype=float)
    n = x.size
    if n < 2 * min_seg_len:
        return []

    if penalty is None:
        diffs = np.abs(np.diff(x))
        sigma = np.median(diffs) / 0.9539 + 1e-9  # MAD of diff -> sd estimate
        penalty = 2.0 * sigma**2 * np.log(n)

    prefix = np.concatenate([[0.0], np.cumsum(x)])
    prefix_sq = np.concatenate([[0.0], np.cumsum(x * x)])

    boundaries: list[int] = []
    stack = [(0, n)]
    while stack and len(boundaries) < max_changepoints:
        i, j = stack.pop()
        if j - i < 2 * min_seg_len:
            continue
        cost_full = _segment_cost(prefix, prefix_sq, i, j)

        ks = np.arange(i + min_seg_len, j - min_seg_len + 1)
        if ks.size == 0:
            continue
        # Vectorized split cost over all candidate positions.
        n_l = ks - i
        n_r = j - ks
        s_l = prefix[ks] - prefix[i]
        s_r = prefix[j] - prefix[ks]
        ss_l = prefix_sq[ks] - prefix_sq[i]
        ss_r = prefix_sq[j] - prefix_sq[ks]
        cost_split = (ss_l - s_l**2 / n_l) + (ss_r - s_r**2 / n_r)

        best = int(np.argmin(cost_split))
        if cost_full - cost_split[best] > penalty:
            k = int(ks[best])
            boundaries.append(k)
            stack.append((i, k))
            stack.append((k, j))

    return sorted(boundaries)


def boundary_recovery(
    detected: list[int] | np.ndarray,
    reference: list[int] | np.ndarray,
    tol_s: int = 5,
) -> dict[str, float]:
    """
    Score detected boundaries against reference boundaries.

    A reference boundary is recovered if a detected boundary lies within
    tol_s samples (greedy one-to-one matching, nearest first). Returns
    precision, recall, f1, n_detected, n_reference, mean_abs_offset_s of
    the matched pairs.
    """
    det = sorted(int(d) for d in detected)
    ref = sorted(int(r) for r in reference)
    if not ref:
        return {"precision": float("nan"), "recall": float("nan"),
                "f1": float("nan"), "n_detected": len(det),
                "n_reference": 0, "mean_abs_offset_s": float("nan")}

    pairs = sorted(
        ((abs(d - r), di, ri) for di, d in enumerate(det)
         for ri, r in enumerate(ref) if abs(d - r) <= tol_s),
    )
    used_d: set[int] = set()
    used_r: set[int] = set()
    offsets: list[int] = []
    for dist, di, ri in pairs:
        if di in used_d or ri in used_r:
            continue
        used_d.add(di)
        used_r.add(ri)
        offsets.append(dist)

    tp = len(offsets)
    precision = tp / len(det) if det else 0.0
    recall = tp / len(ref)
    f1 = (2 * precision * recall / (precision + recall)
          if precision + recall else 0.0)
    return {
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "n_detected": len(det),
        "n_reference": len(ref),
        "mean_abs_offset_s": float(np.mean(offsets)) if offsets else float("nan"),
    }


# ---------------------------------------------------------------------------
# Machine-state decomposition
# ---------------------------------------------------------------------------

def classify_states(
    power_w: np.ndarray,
    idle_power_w: float | None = None,
    cutting_margin_frac: float = 0.25,
    smooth_s: int = 5,
) -> np.ndarray:
    """
    Label every 1 Hz sample as one of: "off", "idle", "positioning", "cutting".

    idle_power_w defaults to the stream's 10th percentile (the machine spends
    real time at base load in every observed program). Samples below 5% of
    idle are "off"; within +/- cutting_margin_frac of idle are "idle"; above
    idle * (1 + cutting_margin_frac) are "cutting"; the band between idle and
    cutting is "positioning" (rapids/tool moves draw a little above base).
    A centered median filter of width smooth_s removes single-sample flicker.
    """
    x = np.asarray(power_w, dtype=float)
    if idle_power_w is None:
        idle_power_w = float(np.percentile(x, 10))
    if idle_power_w <= 0:
        idle_power_w = max(float(np.percentile(x, 10)), 1e-6)

    # Median smoothing.
    if smooth_s > 1 and x.size >= smooth_s:
        pad = smooth_s // 2
        padded = np.pad(x, pad, mode="edge")
        windows = np.lib.stride_tricks.sliding_window_view(padded, smooth_s)
        x = np.median(windows, axis=1)[: x.size]

    labels = np.full(x.size, "idle", dtype=object)
    labels[x < 0.05 * idle_power_w] = "off"
    hi = idle_power_w * (1.0 + cutting_margin_frac)
    lo = idle_power_w * (1.0 + 0.05)
    labels[(x >= lo) & (x < hi)] = "positioning"
    labels[x >= hi] = "cutting"
    return labels


def segment_table(power_w: np.ndarray, boundaries: list[int]) -> list[dict]:
    """
    Split a power stream at the given interior boundaries and summarize each
    segment: start_s, end_s, duration_s, mean_w, peak_w, energy_wh (1 Hz
    rectangle rule, adequate for segment summaries).
    """
    x = np.asarray(power_w, dtype=float)
    edges = [0] + sorted(int(b) for b in boundaries) + [x.size]
    out = []
    for i, j in zip(edges[:-1], edges[1:]):
        if j <= i:
            continue
        seg = x[i:j]
        out.append({
            "start_s": i,
            "end_s": j,
            "duration_s": j - i,
            "mean_w": float(seg.mean()),
            "peak_w": float(seg.max()),
            "energy_wh": float(seg.sum() / 3600.0),
        })
    return out
