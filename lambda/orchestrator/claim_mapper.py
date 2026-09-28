"""Turns an FNOL (from JSON or from Textract lines) into the flat record the models expect.

The public API speaks the language of a claims department (dates, yes/no, dollar amounts);
the models speak features (days_to_report, days_policy_to_loss, ...). This module is the
translation layer, and it's where a real carrier would plug in its policy-admin lookups.
"""
import re
from datetime import date, datetime

LOB_ALIASES = {
    "auto": "auto", "personal auto": "auto", "pa": "auto", "automobile": "auto",
    "homeowners": "homeowners", "home": "homeowners", "ho": "homeowners", "property": "homeowners",
    "workers_comp": "workers_comp", "workers' compensation": "workers_comp",
    "workers compensation": "workers_comp", "wc": "workers_comp",
}
LOSS_ALIASES = {
    "collision": "collision", "theft": "theft", "theft / burglary": "theft", "burglary": "theft",
    "vandalism": "vandalism", "vandalism / malicious mischief": "vandalism",
    "weather": "weather", "wind / hail / storm": "weather", "hail": "weather", "wind": "weather",
    "water damage": "water_damage", "water_damage": "water_damage", "fire": "fire",
    "fire / smoke": "fire", "liability - bodily injury": "liability_injury",
    "liability_injury": "liability_injury", "workplace injury": "workplace_injury",
    "workplace_injury": "workplace_injury",
}

# Printed label on the FNOL form  ->  API field name
FORM_LABELS = {
    "Claim Number": "claim_number",
    "Policy Number": "policy_number",
    "Line of Business": "line_of_business",
    "Named Insured": "insured_name",
    "Employer": "insured_name",
    "Employee": "claimant_name",
    "Insured Age": "insured_age",
    "Employee Age": "insured_age",
    "Date of Loss": "loss_date",
    "Time of Loss": "loss_time",
    "Date Reported": "report_date",
    "Policy Effective Date": "policy_effective_date",
    "Loss Location": "loss_location",
    "Type of Loss": "loss_type",
    "Estimated Amount of Loss": "estimated_loss_amount",
    "Deductible": "deductible",
    "Annual Premium": "annual_premium",
    "Coverage Limit": "coverage_limit",
    "Prior Claims (Last 3 Years)": "prior_claims_3yr",
    "Vehicle Year": "asset_year",
    "Year Built": "asset_year",
    "Year of Hire": "asset_year",
    "Vehicle": "vehicle_description",
    "Police Report Filed": "police_report_filed",
    "Witnesses": "witnesses",
    "Injuries Reported": "injuries_reported",
    "Attorney Involved": "attorney_involved",
    "Coverage Change in Last 90 Days": "coverage_change_last_90_days",
}
SECTION_END = ["REPORTED BY", "SIGNATURE", "FOR OFFICE USE", "ADJUSTER NOTES"]


def _date(v):
    if not v:
        return None
    if isinstance(v, date):
        return v
    v = str(v).strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%m-%d-%Y"):
        try:
            return datetime.strptime(v, fmt).date()
        except ValueError:
            pass
    return None


def _money(v):
    if v is None or v == "":
        return None
    try:
        return float(re.sub(r"[^0-9.\-]", "", str(v)) or "nan")
    except ValueError:
        return None


def _yes(v):
    if isinstance(v, bool):
        return int(v)
    if v is None:
        return None
    s = str(v).strip().lower()
    if s.startswith(("y", "true", "1", "x")):
        return 1
    if s.startswith(("n", "false", "0")):
        return 0
    return None


def _int(v):
    m = _money(v)
    return None if m is None or m != m else int(m)


def to_model_record(claim: dict) -> dict:
    """API/FNOL claim -> model feature record (missing values left as None; models impute)."""
    loss = _date(claim.get("loss_date"))
    reported = _date(claim.get("report_date")) or loss
    eff = _date(claim.get("policy_effective_date"))
    lob = LOB_ALIASES.get(str(claim.get("line_of_business", "")).strip().lower())
    lt = LOSS_ALIASES.get(str(claim.get("loss_type", "")).strip().lower())

    hour = None
    t = str(claim.get("loss_time") or "")
    m = re.match(r"\s*(\d{1,2})(?::(\d{2}))?\s*([ap]\.?m\.?)?", t, re.I)
    if m:
        hour = int(m.group(1)) % 24
        if m.group(3) and m.group(3).lower().startswith("p") and hour < 12:
            hour += 12
        if m.group(3) and m.group(3).lower().startswith("a") and hour == 12:
            hour = 0

    days_policy_to_loss = (loss - eff).days if loss and eff else None
    asset_year = _int(claim.get("asset_year"))
    rec = {
        "line_of_business": lob,
        "loss_type": lt,
        "policy_tenure_months": max(1, days_policy_to_loss // 30 + 1) if days_policy_to_loss is not None else None,
        "days_policy_to_loss": days_policy_to_loss,
        "days_to_report": (reported - loss).days if loss and reported else None,
        "insured_age": _int(claim.get("insured_age")),
        "annual_premium": _money(claim.get("annual_premium")),
        "deductible": _money(claim.get("deductible")),
        "prior_claims_3yr": _int(claim.get("prior_claims_3yr")),
        "claim_amount_reported": _money(claim.get("estimated_loss_amount")),
        "asset_age_years": (loss.year - asset_year) if loss and asset_year else None,
        "incident_hour": hour,
        "is_weekend": int(loss.weekday() >= 5) if loss else None,
        "police_report_filed": _yes(claim.get("police_report_filed")),
        "witness_present": _yes(claim.get("witnesses")),
        "injury_reported": _yes(claim.get("injuries_reported")),
        "attorney_involved": _yes(claim.get("attorney_involved")),
        "total_loss_indicated": _yes(claim.get("total_loss_indicated")),
        "coverage_increase_last_90d": _yes(claim.get("coverage_change_last_90_days")),
    }
    return rec


def parse_fnol_lines(lines):
    """Textract LINE text (top-to-bottom) -> API claim dict.

    Robust to two-column layouts: several "Label: value" pairs may land on one line.
    """
    labels = sorted(FORM_LABELS, key=len, reverse=True)
    label_re = re.compile(r"(" + "|".join(re.escape(l) for l in labels) + r")\s*:", re.I)
    claim, desc, in_desc = {}, [], False
    lines = [l.strip() for l in lines if l and l.strip()]
    pending = None  # label seen with its value on the following line
    for raw in lines:
        line = raw.strip()
        if pending and not label_re.match(line) and not line.upper().startswith("DESCRIPTION OF LOSS"):
            claim.setdefault(pending, line)
            pending = None
            continue
        pending = None
        up = line.upper()
        if up.startswith("DESCRIPTION OF LOSS"):
            in_desc = True
            rest = line[len("DESCRIPTION OF LOSS"):].lstrip(" :")
            if rest:
                desc.append(rest)
            continue
        if in_desc:
            if any(up.startswith(s) for s in SECTION_END):
                in_desc = False
            else:
                desc.append(line)
                continue
        matches = list(label_re.finditer(line))
        for i, m in enumerate(matches):
            end = matches[i + 1].start() if i + 1 < len(matches) else len(line)
            val = line[m.end():end].strip()
            key = FORM_LABELS[next(l for l in FORM_LABELS if l.lower() == m.group(1).lower())]
            if val and key not in claim:
                claim[key] = val
            elif not val and i == len(matches) - 1:
                pending = key
    if desc:
        claim["description"] = " ".join(desc).strip()
    loc = claim.get("loss_location")
    if loc and "," in loc:
        city, st = loc.rsplit(",", 1)
        claim["loss_location"] = {"city": city.strip(), "state": st.strip()[:2]}
    return claim
