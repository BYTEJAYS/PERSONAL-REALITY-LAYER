"""Train the active-day predictor — a real fitted ML model.

Pipeline: read git history → build a daily timeline → engineer leakage-free
features → time-based train/test split → fit logistic regression by gradient
descent → evaluate on held-out days (AUC / precision / recall) → save weights to
artifacts/active_day_model.json → forecast tomorrow.

    cd backend && python scripts/train_predictor.py [repo ...]
"""

from __future__ import annotations

import os
import sys
from datetime import timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, os.pardir))  # backend/ on path → import ml
sys.path.insert(0, HERE)                            # scripts/ → reuse train.py ingest

from ml import features as F                         # noqa: E402
from ml.logreg import (LogisticRegression, accuracy,  # noqa: E402
                       precision_recall_f1, roc_auc)
import train as ingest                               # noqa: E402


def main(argv: list[str]) -> None:
    sources = ["git"]
    repos: list[str] = []
    for a in argv:
        if a.startswith("--sources="):
            sources = [s.strip() for s in a.split("=", 1)[1].split(",") if s.strip()]
        else:
            repos.append(a)

    print(f"   sources: {', '.join(sources)}")
    mems = ingest.collect(sources, repos or None)
    if len(mems) < 10:
        print(f"Need more history to train (have {len(mems)} memories).")
        return

    # Cap the timeline to recent days so a lone old event can't stretch the span
    # over a long empty gap (degenerate split).
    window = None if "--full-span" in argv else 90
    X, y, dates = F.build_dataset(mems, window_days=window)
    n = len(X)
    pos = sum(y)
    base_rate = pos / n

    # Time-based split — train on the past, test on the most recent days.
    cut = int(n * 0.8)
    Xtr, ytr = X[:cut], y[:cut]
    Xte, yte = X[cut:], y[cut:]

    pos_tr, pos_te = sum(ytr), sum(yte)
    MIN_POS = 30
    trustworthy = pos_tr >= MIN_POS and pos_te >= 5

    print(f"\n⟳ Training active-day predictor")
    print(f"   {n} days · {pos} active ({base_rate*100:.1f}% base rate) · "
          f"{len(Xtr)} train / {len(Xte)} test  ({pos_tr}/{pos_te} active)\n")
    if not trustworthy:
        print("   ⚠  INSUFFICIENT DATA — this is a working scaffold, not a")
        print(f"      trustworthy model. Need ≥{MIN_POS} active days to train (have "
              f"{pos_tr}). Metrics below will overfit; add more signal sources.\n")

    model = LogisticRegression(lr=0.2, epochs=1200, l2=1e-2, class_weight=True)
    model.fit(Xtr, ytr, feature_names=F.FEATURE_NAMES)

    p_tr = model.predict_proba(Xtr)
    p_te = model.predict_proba(Xte)

    print("   ── Performance ──────────────────────────────")
    print(f"   train  AUC {roc_auc(ytr, p_tr):.3f} | acc {accuracy(ytr, p_tr):.3f}")
    if sum(yte) and sum(yte) < len(yte):
        prec, rec, f1 = precision_recall_f1(yte, p_te)
        print(f"   test   AUC {roc_auc(yte, p_te):.3f} | acc {accuracy(yte, p_te):.3f} "
              f"| P {prec:.2f} R {rec:.2f} F1 {f1:.2f}")
    else:
        print(f"   test   (held-out window has no class variety — {sum(yte)}/{len(yte)} active)")

    # Learned feature importances (standardised coefficients).
    print("\n   ── What predicts an active day ──────────────")
    coefs = sorted(zip(model.feature_names, model.w), key=lambda t: abs(t[1]), reverse=True)
    for name, w in coefs[:8]:
        arrow = "↑" if w > 0 else "↓"
        print(f"     {arrow} {name:<18} {w:+.3f}")

    # Save model.
    art = os.path.join(HERE, os.pardir, "artifacts")
    os.makedirs(art, exist_ok=True)
    path = os.path.join(art, "active_day_model.json")
    payload = model.to_dict()
    payload["trustworthy"] = trustworthy
    payload["train_positives"] = pos_tr
    import json
    with open(path, "w") as fh:
        json.dump(payload, fh, indent=2)

    # Forecast tomorrow.
    counts, start, end = F.daily_counts(mems)
    tomorrow = end + timedelta(days=1)
    prob = model.predict_one(F.features_for_future(tomorrow, counts, start, end))
    print(f"\n   ── Forecast ─────────────────────────────────")
    tag = "" if trustworthy else "  (low confidence — insufficient data)"
    print(f"     P(active on {tomorrow.isoformat()}) = {prob*100:.1f}%{tag}")
    print(f"\n✓ Model saved → {os.path.relpath(path)}\n")


if __name__ == "__main__":
    main(sys.argv[1:])
