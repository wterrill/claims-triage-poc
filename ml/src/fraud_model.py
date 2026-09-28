"""Model 1 - Fraud risk scorer (gradient-boosted trees).

Same file is used for:
  * training   - SageMaker training job entry point (or `python fraud_model.py --local`)
  * inference  - SageMaker scikit-learn serving (model_fn / input_fn / predict_fn / output_fn)

Response per claim:
  {"fraud_score": 0.83, "risk_level": "high",
   "top_factors": [{"factor": "...", "value": 21, "typical": 410, "impact": 0.31}, ...]}
"""
import argparse
import json
import os
import shutil
import sys

import joblib
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from features import (FEATURE_COLUMNS, FEATURE_LABELS, NUMERIC, build_features,  # noqa: E402
                      parse_request)

MODEL_FILE = "fraud_model.joblib"
EXPLAIN_FIELDS = [f for f in NUMERIC if f not in ("insured_age", "annual_premium", "deductible")]


# ----------------------------------------------------------------------------- training
def train(args):
    from sklearn.ensemble import GradientBoostingClassifier
    from sklearn.metrics import average_precision_score, roc_auc_score
    from sklearn.model_selection import train_test_split

    df = pd.read_csv(os.path.join(args.train, "claims_history.csv"))
    X = build_features(df)[FEATURE_COLUMNS]
    y = df["is_fraud"].astype(int)
    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.2, stratify=y, random_state=7)

    clf = GradientBoostingClassifier(n_estimators=args.n_estimators, max_depth=args.max_depth,
                                     learning_rate=args.learning_rate, subsample=0.8, random_state=7)
    clf.fit(X_tr, y_tr)
    p = clf.predict_proba(X_te)[:, 1]
    metrics = {
        "auc": round(float(roc_auc_score(y_te, p)), 4),
        "average_precision": round(float(average_precision_score(y_te, p)), 4),
        "base_rate": round(float(y.mean()), 4),
        "precision_at_top5pct": round(float(y_te.values[np.argsort(-p)[: max(1, len(p) // 20)]].mean()), 4),
        "n_train": int(len(X_tr)), "n_test": int(len(X_te)),
    }
    # Metrics printed in a regex-friendly way so SageMaker can chart them
    for k, v in metrics.items():
        print(f"metric_{k}={v};")

    legit = df[df["is_fraud"] == 0]
    baseline = {f: float(legit[f].median()) for f in EXPLAIN_FIELDS}
    joblib.dump({"model": clf, "columns": FEATURE_COLUMNS, "baseline": baseline,
                 "thresholds": {"medium": 0.25, "high": 0.55}}, os.path.join(args.model_dir, MODEL_FILE))
    json.dump(metrics, open(os.path.join(args.model_dir, "metrics.json"), "w"), indent=2)
    _bundle_code(args.model_dir)
    print("fraud model saved")


def _bundle_code(model_dir):
    """Copy inference code into model.tar.gz so the artifact is self-contained."""
    code = os.path.join(model_dir, "code")
    os.makedirs(code, exist_ok=True)
    here = os.path.dirname(os.path.abspath(__file__))
    for f in ("features.py", os.path.basename(__file__)):
        shutil.copy(os.path.join(here, f), code)


# ----------------------------------------------------------------------------- inference
def model_fn(model_dir):
    return joblib.load(os.path.join(model_dir, MODEL_FILE))


def input_fn(body, content_type="application/json"):
    return parse_request(body, content_type)


def predict_fn(records, art):
    clf, cols, base = art["model"], art["columns"], art["baseline"]
    X = build_features(records)[cols]
    scores = clf.predict_proba(X)[:, 1]

    results = []
    for i, rec in enumerate(records):
        # Counterfactual explanation: how much does the score drop if this one field were "typical"?
        variants = []
        for f in EXPLAIN_FIELDS:
            r = dict(rec)
            r[f] = base[f]
            variants.append(r)
        Xv = build_features(variants)[cols]
        # measure impact in log-odds so saturated (very high/low) scores still explain well
        pv = np.clip(clf.predict_proba(Xv)[:, 1], 1e-6, 1 - 1e-6)
        si = np.clip(scores[i], 1e-6, 1 - 1e-6)
        drops = np.log(si / (1 - si)) - np.log(pv / (1 - pv))
        feats = build_features([rec]).iloc[0]
        factors = []
        for j in np.argsort(-drops)[:3]:
            if drops[j] <= 0.15:
                continue
            f = EXPLAIN_FIELDS[j]
            factors.append({"factor": FEATURE_LABELS.get(f, f), "field": f,
                            "value": _clean(feats[f]), "typical": _clean(base[f]),
                            "impact": round(float(drops[j]), 3)})
        s = float(scores[i])
        level = "high" if s >= art["thresholds"]["high"] else "medium" if s >= art["thresholds"]["medium"] else "low"
        results.append({"fraud_score": round(s, 4), "risk_level": level, "top_factors": factors})
    return results


def output_fn(prediction, accept="application/json"):
    return json.dumps({"predictions": prediction}), "application/json"


def _clean(v):
    v = float(v)
    return int(v) if v.is_integer() else round(v, 2)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-estimators", type=int, default=300)
    ap.add_argument("--max-depth", type=int, default=3)
    ap.add_argument("--learning-rate", type=float, default=0.05)
    ap.add_argument("--model-dir", default=os.environ.get("SM_MODEL_DIR", "model/fraud"))
    ap.add_argument("--train", default=os.environ.get("SM_CHANNEL_TRAIN", "data"))
    a = ap.parse_args()
    os.makedirs(a.model_dir, exist_ok=True)
    train(a)
