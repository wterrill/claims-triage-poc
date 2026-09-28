"""Model 2 - Severity / reserve estimator (gradient-boosted regression with quantiles).

Predicts the expected ultimate incurred cost of a claim plus a P10-P90 range, and maps
that to a reserve band the claims team already understands.

Response per claim:
  {"predicted_cost": 18250.0, "range_low": 7900.0, "range_high": 46100.0,
   "suggested_reserve": 18250.0, "reserve_band": "moderate"}
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
from features import FEATURE_COLUMNS, build_features, parse_request  # noqa: E402

MODEL_FILE = "severity_model.joblib"
BANDS = [(5000, "low"), (25000, "moderate"), (100000, "high"), (float("inf"), "severe")]


def train(args):
    from sklearn.ensemble import GradientBoostingRegressor
    from sklearn.metrics import mean_absolute_error, r2_score
    from sklearn.model_selection import train_test_split

    df = pd.read_csv(os.path.join(args.train, "claims_history.csv"))
    X = build_features(df)[FEATURE_COLUMNS]
    y = np.log(df["incurred_cost"].clip(lower=50))
    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.2, random_state=11)

    common = dict(n_estimators=args.n_estimators, max_depth=args.max_depth,
                  learning_rate=args.learning_rate, subsample=0.8, random_state=11)
    mid = GradientBoostingRegressor(loss="squared_error", **common).fit(X_tr, y_tr)
    lo = GradientBoostingRegressor(loss="quantile", alpha=0.1, **common).fit(X_tr, y_tr)
    hi = GradientBoostingRegressor(loss="quantile", alpha=0.9, **common).fit(X_tr, y_tr)

    # log-normal mean correction so the point estimate is unbiased in dollars
    resid_var = float(np.var(y_tr - mid.predict(X_tr)))
    pred = np.exp(mid.predict(X_te) + resid_var / 2)
    actual = np.exp(y_te)
    lo_p, hi_p = np.exp(lo.predict(X_te)), np.exp(hi.predict(X_te))
    metrics = {
        "r2_log": round(float(r2_score(y_te, mid.predict(X_te))), 4),
        "mae_dollars": round(float(mean_absolute_error(actual, pred)), 2),
        "median_abs_pct_error": round(float(np.median(np.abs(pred - actual) / actual)), 4),
        "p10_p90_coverage": round(float(((actual >= lo_p) & (actual <= hi_p)).mean()), 4),
        "n_train": int(len(X_tr)), "n_test": int(len(X_te)),
    }
    for k, v in metrics.items():
        print(f"metric_{k}={v};")

    joblib.dump({"mid": mid, "lo": lo, "hi": hi, "resid_var": resid_var, "columns": FEATURE_COLUMNS},
                os.path.join(args.model_dir, MODEL_FILE))
    json.dump(metrics, open(os.path.join(args.model_dir, "metrics.json"), "w"), indent=2)
    code = os.path.join(args.model_dir, "code")
    os.makedirs(code, exist_ok=True)
    here = os.path.dirname(os.path.abspath(__file__))
    for f in ("features.py", os.path.basename(__file__)):
        shutil.copy(os.path.join(here, f), code)
    print("severity model saved")


def model_fn(model_dir):
    return joblib.load(os.path.join(model_dir, MODEL_FILE))


def input_fn(body, content_type="application/json"):
    return parse_request(body, content_type)


def predict_fn(records, art):
    X = build_features(records)[art["columns"]]
    mid = np.exp(art["mid"].predict(X) + art["resid_var"] / 2)
    lo = np.exp(art["lo"].predict(X))
    hi = np.exp(art["hi"].predict(X))
    out = []
    for m, l, h in zip(mid, lo, hi):
        l, h = min(l, m), max(h, m)
        band = next(name for cap, name in BANDS if m < cap)
        out.append({"predicted_cost": _r(m), "range_low": _r(l), "range_high": _r(h),
                    "suggested_reserve": _r(m), "reserve_band": band})
    return out


def output_fn(prediction, accept="application/json"):
    return json.dumps({"predictions": prediction}), "application/json"


def _r(v):
    return float(round(float(v), -1))  # nearest $10 - reserves are never set to the penny


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-estimators", type=int, default=300)
    ap.add_argument("--max-depth", type=int, default=3)
    ap.add_argument("--learning-rate", type=float, default=0.05)
    ap.add_argument("--model-dir", default=os.environ.get("SM_MODEL_DIR", "model/severity"))
    ap.add_argument("--train", default=os.environ.get("SM_CHANNEL_TRAIN", "data"))
    a = ap.parse_args()
    os.makedirs(a.model_dir, exist_ok=True)
    train(a)
