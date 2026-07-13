"""
Power-signature features and fingerprint classification.

WHY THIS EXISTS
Operation-level energy totals throw away the waveform. If an operation's
identity is recoverable from its 1 Hz power signature alone, then (a) the
UUID attribution scheme can be spot-checked from the signal, and (b) machines
without CAM integration can still get approximate operation-level attribution
(see shared/segmentation.py for the boundary half of that claim).

Deliberately minimal ML: z-scored features and a nearest-centroid classifier,
evaluated leave-one-run-out. If THAT identifies operations, the signal is
plainly informative; a fancier model would only cloud the claim.

Machine-agnostic: works on any (segment -> 1 Hz power array) mapping.
"""

from __future__ import annotations

import numpy as np

__all__ = [
    "extract_features",
    "FEATURE_NAMES",
    "NearestCentroid",
    "leave_one_group_out",
]

FEATURE_NAMES = [
    "duration_s",
    "mean_w",
    "peak_w",
    "p25_w",
    "p75_w",
    "cv",
    "idle_frac",
    "mean_abs_diff_w",
    "burst_rate",
]


def extract_features(power_w: np.ndarray, idle_power_w: float) -> dict[str, float]:
    """
    Summarize one operation's 1 Hz power trace as a fixed-length signature.

    idle_power_w is the machine base load (estimate it once per stream, e.g.
    the stream's 10th percentile); features that separate "working" from
    "dwelling" depend on it.

    Features (all robust to trace length):
      duration_s        - number of samples (1 Hz)
      mean_w, peak_w    - level statistics
      p25_w, p75_w      - distribution shape
      cv                - sd/mean, unitless spread
      idle_frac         - fraction of samples within 10% of base load
      mean_abs_diff_w   - mean |first difference|, transientness
      burst_rate        - fraction of samples that jump > 20% of base load
                          in one second (drill peck / tap reverse signature)
    """
    x = np.asarray(power_w, dtype=float)
    if x.size == 0:
        raise ValueError("empty power trace")
    mean = float(x.mean())
    sd = float(x.std())
    diffs = np.abs(np.diff(x)) if x.size > 1 else np.array([0.0])
    return {
        "duration_s": float(x.size),
        "mean_w": mean,
        "peak_w": float(x.max()),
        "p25_w": float(np.percentile(x, 25)),
        "p75_w": float(np.percentile(x, 75)),
        "cv": sd / mean if mean else 0.0,
        "idle_frac": float(np.mean(np.abs(x - idle_power_w) <= 0.10 * idle_power_w)),
        "mean_abs_diff_w": float(diffs.mean()),
        "burst_rate": float(np.mean(diffs > 0.20 * idle_power_w)),
    }


class NearestCentroid:
    """
    Z-scored nearest-centroid classifier.

    fit(X, y): X is (n_samples, n_features), y an array of labels. Features
    are standardized with the training set's mean/sd; each class is its
    centroid in that space. predict() returns the nearest centroid's label
    (Euclidean). predict_with_distance() also returns the distance, usable
    as an anomaly score (an operation far from every centroid is a drifted
    or mislabeled run).
    """

    def fit(self, X: np.ndarray, y) -> "NearestCentroid":
        X = np.asarray(X, dtype=float)
        self.mu_ = X.mean(axis=0)
        self.sd_ = X.std(axis=0)
        self.sd_[self.sd_ == 0] = 1.0
        Z = (X - self.mu_) / self.sd_
        self.labels_ = np.array(sorted(set(map(str, y))))
        y = np.asarray([str(v) for v in y])
        self.centroids_ = np.vstack([Z[y == c].mean(axis=0) for c in self.labels_])
        return self

    def _distances(self, X: np.ndarray) -> np.ndarray:
        Z = (np.asarray(X, dtype=float) - self.mu_) / self.sd_
        return np.linalg.norm(Z[:, None, :] - self.centroids_[None, :, :], axis=2)

    def predict(self, X: np.ndarray) -> np.ndarray:
        return self.labels_[np.argmin(self._distances(X), axis=1)]

    def predict_with_distance(self, X: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        d = self._distances(X)
        idx = np.argmin(d, axis=1)
        return self.labels_[idx], d[np.arange(len(idx)), idx]


def leave_one_group_out(
    X: np.ndarray,
    y,
    groups,
) -> dict:
    """
    Leave-one-group-out evaluation of NearestCentroid.

    Groups are runs: train on all runs but one, predict the held-out run,
    repeat. This is the honest protocol for replicated manufacturing data;
    random row splits would leak run identity through shared conditions.

    Returns {"accuracy", "n_correct", "n_total", "per_label": {label: acc},
    "confusion": {(true, pred): count}}.
    """
    X = np.asarray(X, dtype=float)
    y = np.asarray([str(v) for v in y])
    groups = np.asarray([str(g) for g in groups])

    n_correct = 0
    n_total = 0
    confusion: dict[tuple[str, str], int] = {}
    label_hits: dict[str, list[int]] = {}

    for g in sorted(set(groups)):
        test = groups == g
        train = ~test
        # Every class must appear in training; drop test rows whose label
        # is absent from the training fold (can happen with tiny fixtures).
        train_labels = set(y[train])
        usable = test & np.isin(y, sorted(train_labels))
        if not usable.any() or not train.any():
            continue
        clf = NearestCentroid().fit(X[train], y[train])
        pred = clf.predict(X[usable])
        for t, p in zip(y[usable], pred):
            n_total += 1
            n_correct += int(t == p)
            confusion[(t, p)] = confusion.get((t, p), 0) + 1
            label_hits.setdefault(t, []).append(int(t == p))

    return {
        "accuracy": n_correct / n_total if n_total else float("nan"),
        "n_correct": n_correct,
        "n_total": n_total,
        "per_label": {k: float(np.mean(v)) for k, v in sorted(label_hits.items())},
        "confusion": confusion,
    }
