"""Logistic regression, from scratch.

Standardised features, gradient-descent fit with L2 regularisation and optional
class weighting (for imbalanced targets like rare active days). Serialises to a
plain dict so a trained model can be saved as JSON and reloaded for inference.
"""

from __future__ import annotations

import json
import math


def _sigmoid(z: float) -> float:
    if z < -35:
        return 1e-15
    if z > 35:
        return 1.0
    return 1.0 / (1.0 + math.exp(-z))


class LogisticRegression:
    def __init__(self, lr: float = 0.1, epochs: int = 800, l2: float = 1e-3,
                 class_weight: bool = True):
        self.lr = lr
        self.epochs = epochs
        self.l2 = l2
        self.class_weight = class_weight
        self.w: list[float] = []
        self.b: float = 0.0
        self.mean: list[float] = []
        self.std: list[float] = []
        self.feature_names: list[str] = []

    # --- standardisation ---
    def _fit_scaler(self, X: list[list[float]]) -> None:
        n, d = len(X), len(X[0])
        self.mean = [sum(row[j] for row in X) / n for j in range(d)]
        self.std = []
        for j in range(d):
            var = sum((row[j] - self.mean[j]) ** 2 for row in X) / n
            self.std.append(math.sqrt(var) or 1.0)

    def _scale(self, row: list[float]) -> list[float]:
        return [(row[j] - self.mean[j]) / self.std[j] for j in range(len(row))]

    # --- training ---
    def fit(self, X: list[list[float]], y: list[int], feature_names: list[str] | None = None):
        n, d = len(X), len(X[0])
        self.feature_names = feature_names or [f"x{j}" for j in range(d)]
        self._fit_scaler(X)
        Xs = [self._scale(row) for row in X]

        pos = sum(y) or 1
        neg = (n - sum(y)) or 1
        wp = n / (2 * pos) if self.class_weight else 1.0
        wn = n / (2 * neg) if self.class_weight else 1.0

        self.w = [0.0] * d
        self.b = 0.0
        for _ in range(self.epochs):
            gw = [0.0] * d
            gb = 0.0
            for i in range(n):
                z = self.b + sum(self.w[j] * Xs[i][j] for j in range(d))
                err = _sigmoid(z) - y[i]
                sw = wp if y[i] == 1 else wn
                err *= sw
                for j in range(d):
                    gw[j] += err * Xs[i][j]
                gb += err
            for j in range(d):
                gw[j] = gw[j] / n + self.l2 * self.w[j]
                self.w[j] -= self.lr * gw[j]
            self.b -= self.lr * (gb / n)
        return self

    def predict_proba(self, X: list[list[float]]) -> list[float]:
        out = []
        for row in X:
            s = self._scale(row)
            z = self.b + sum(self.w[j] * s[j] for j in range(len(s)))
            out.append(_sigmoid(z))
        return out

    def predict_one(self, row: list[float]) -> float:
        return self.predict_proba([row])[0]

    # --- persistence ---
    def to_dict(self) -> dict:
        return {"w": self.w, "b": self.b, "mean": self.mean, "std": self.std,
                "feature_names": self.feature_names,
                "hyper": {"lr": self.lr, "epochs": self.epochs, "l2": self.l2}}

    @classmethod
    def from_dict(cls, d: dict) -> "LogisticRegression":
        m = cls()
        m.w, m.b, m.mean, m.std = d["w"], d["b"], d["mean"], d["std"]
        m.feature_names = d["feature_names"]
        return m

    def save(self, path: str) -> None:
        with open(path, "w") as fh:
            json.dump(self.to_dict(), fh, indent=2)

    @classmethod
    def load(cls, path: str) -> "LogisticRegression":
        with open(path) as fh:
            return cls.from_dict(json.load(fh))


# --- metrics ----------------------------------------------------------------
def accuracy(y: list[int], p: list[float], thr: float = 0.5) -> float:
    return sum((pi >= thr) == bool(yi) for yi, pi in zip(y, p)) / len(y)


def precision_recall_f1(y: list[int], p: list[float], thr: float = 0.5) -> tuple[float, float, float]:
    tp = sum(1 for yi, pi in zip(y, p) if yi == 1 and pi >= thr)
    fp = sum(1 for yi, pi in zip(y, p) if yi == 0 and pi >= thr)
    fn = sum(1 for yi, pi in zip(y, p) if yi == 1 and pi < thr)
    prec = tp / (tp + fp) if (tp + fp) else 0.0
    rec = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
    return prec, rec, f1


def roc_auc(y: list[int], p: list[float]) -> float:
    """Mann–Whitney U formulation — robust to class imbalance."""
    pos = [pi for yi, pi in zip(y, p) if yi == 1]
    neg = [pi for yi, pi in zip(y, p) if yi == 0]
    if not pos or not neg:
        return float("nan")
    ranked = sorted(((pi, yi) for yi, pi in zip(y, p)), key=lambda t: t[0])
    rank_sum = 0.0
    i = 0
    r = 1
    while i < len(ranked):
        j = i
        while j < len(ranked) and ranked[j][0] == ranked[i][0]:
            j += 1
        avg_rank = (r + (r + (j - i) - 1)) / 2.0
        for k in range(i, j):
            if ranked[k][1] == 1:
                rank_sum += avg_rank
        r += (j - i)
        i = j
    n_pos, n_neg = len(pos), len(neg)
    return (rank_sum - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg)
