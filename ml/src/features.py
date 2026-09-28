"""Shared feature engineering for the structured-data models (fraud + severity).

Kept dependency-light (numpy + pandas) and compatible with the SageMaker
scikit-learn 1.2 container so the exact same code runs in training and serving.
"""
import math

import numpy as np
import pandas as pd

LOBS = ["auto", "homeowners", "workers_comp"]
LOSS_TYPES = ["collision", "theft", "vandalism", "weather", "water_damage", "fire",
              "liability_injury", "workplace_injury"]

NUMERIC = [
    "policy_tenure_months", "days_policy_to_loss", "days_to_report", "insured_age",
    "annual_premium", "deductible", "prior_claims_3yr", "claim_amount_reported",
    "asset_age_years", "incident_hour", "is_weekend", "police_report_filed",
    "witness_present", "injury_reported", "attorney_involved", "total_loss_indicated",
    "coverage_increase_last_90d",
]

# Plain-English explanations used in API responses (adjusters shouldn't need to read feature names)
FEATURE_LABELS = {
    "policy_tenure_months": "Policy tenure",
    "days_policy_to_loss": "Days between policy start and loss",
    "days_to_report": "Days taken to report the loss",
    "insured_age": "Insured age",
    "annual_premium": "Annual premium",
    "deductible": "Deductible",
    "prior_claims_3yr": "Prior claims in last 3 years",
    "claim_amount_reported": "Amount claimed",
    "asset_age_years": "Vehicle / property age",
    "incident_hour": "Time of day of loss",
    "is_weekend": "Loss occurred on a weekend",
    "police_report_filed": "Police report filed",
    "witness_present": "Independent witness",
    "injury_reported": "Injury reported",
    "attorney_involved": "Attorney involved",
    "total_loss_indicated": "Total loss indicated",
    "coverage_increase_last_90d": "Coverage increased in last 90 days",
    "night_loss": "Loss between 11pm and 5am",
    "log_amount": "Amount claimed",
    "amount_to_premium": "Amount claimed vs. annual premium",
    "early_loss": "Loss within 60 days of policy start",
    "late_report": "Reported more than 14 days after loss",
}
for _l in LOBS:
    FEATURE_LABELS[f"lob_{_l}"] = f"Line of business: {_l}"
for _t in LOSS_TYPES:
    FEATURE_LABELS[f"loss_{_t}"] = f"Loss type: {_t.replace('_', ' ')}"

DEFAULTS = {
    "policy_tenure_months": 24, "days_policy_to_loss": 365, "days_to_report": 2,
    "insured_age": 45, "annual_premium": 1500, "deductible": 500, "prior_claims_3yr": 0,
    "claim_amount_reported": 5000, "asset_age_years": 8, "incident_hour": 14, "is_weekend": 0,
    "police_report_filed": 0, "witness_present": 0, "injury_reported": 0,
    "attorney_involved": 0, "total_loss_indicated": 0, "coverage_increase_last_90d": 0,
}


def _num(v, default):
    try:
        if v is None or (isinstance(v, str) and v.strip() == ""):
            return float(default)
        if isinstance(v, bool):
            return float(v)
        if isinstance(v, str) and v.strip().lower() in ("y", "yes", "true"):
            return 1.0
        if isinstance(v, str) and v.strip().lower() in ("n", "no", "false"):
            return 0.0
        f = float(v)
        return default if math.isnan(f) else f
    except (TypeError, ValueError):
        return float(default)


def build_features(records) -> pd.DataFrame:
    """records: list[dict] or DataFrame of raw claim fields -> model-ready DataFrame."""
    df = records if isinstance(records, pd.DataFrame) else pd.DataFrame(list(records))
    out = pd.DataFrame(index=df.index)
    for c in NUMERIC:
        col = df[c] if c in df else pd.Series([None] * len(df), index=df.index)
        out[c] = [_num(v, DEFAULTS[c]) for v in col]
    out["night_loss"] = out["incident_hour"].isin([23, 0, 1, 2, 3, 4]).astype(float)
    out["log_amount"] = np.log1p(out["claim_amount_reported"].clip(lower=0))
    out["amount_to_premium"] = out["claim_amount_reported"] / out["annual_premium"].clip(lower=100)
    out["early_loss"] = (out["days_policy_to_loss"] < 60).astype(float)
    out["late_report"] = (out["days_to_report"] > 14).astype(float)
    blank = pd.Series([""] * len(df), index=df.index)
    lob = df["line_of_business"].fillna("").astype(str).str.lower() if "line_of_business" in df else blank
    lt = df["loss_type"].fillna("").astype(str).str.lower() if "loss_type" in df else blank
    for l in LOBS:
        out[f"lob_{l}"] = (lob == l).astype(float)
    for t in LOSS_TYPES:
        out[f"loss_{t}"] = (lt == t).astype(float)
    return out


FEATURE_COLUMNS = list(build_features([{"line_of_business": "auto", "loss_type": "collision"}]).columns)


def parse_request(body, content_type):
    """Accept application/json ({"instances":[...]}, a list, or one object) or text/csv with header."""
    import io
    import json
    if isinstance(body, (bytes, bytearray)):
        body = body.decode("utf-8")
    if content_type and "csv" in content_type:
        return pd.read_csv(io.StringIO(body)).to_dict("records")
    data = json.loads(body)
    if isinstance(data, dict) and "instances" in data:
        return data["instances"]
    if isinstance(data, dict):
        return [data]
    return data
