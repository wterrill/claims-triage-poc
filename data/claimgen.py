"""
Synthetic claims generator for the Claims Triage Assistant POC.

Produces realistic-looking (but entirely fictional) P&C claims across three
lines of business with:
  * structured FNOL fields
  * a free-text loss narrative written in legacy adjuster shorthand
  * ground-truth labels: is_fraud, paid_amount, loss_category, and
    injury / litigation / total_loss flags

Nothing here describes a real person, policy, or company.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, asdict, field
from datetime import date, timedelta

# --------------------------------------------------------------------------
# Reference data
# --------------------------------------------------------------------------
FIRST = ["James", "Maria", "Robert", "Linda", "Michael", "Patricia", "David", "Jennifer",
         "William", "Elizabeth", "Carlos", "Aisha", "Thomas", "Karen", "Daniel", "Nancy",
         "Kevin", "Priya", "Brian", "Sandra", "Luis", "Donna", "Tyrone", "Megan", "Wei",
         "Rachel", "Hector", "Olga", "Samuel", "Grace", "Omar", "Heather", "Victor", "Julie"]
LAST = ["Anderson", "Brooks", "Castillo", "Dawson", "Everett", "Fischer", "Garcia", "Hughes",
        "Iverson", "Jackson", "Kowalski", "Lindqvist", "Morales", "Nguyen", "O'Neill", "Patel",
        "Quinn", "Ramirez", "Schultz", "Thompson", "Underwood", "Vasquez", "Whitaker", "Young",
        "Zimmerman", "Okafor", "Delgado", "Novak", "Harrington", "Bishop"]
STATES = ["IL", "WI", "IN", "MI", "OH", "MO", "IA", "MN", "KY", "TN"]
CITIES = {"IL": ["Springfield", "Peoria", "Naperville", "Joliet", "Rockford"],
          "WI": ["Madison", "Green Bay", "Kenosha"], "IN": ["Fort Wayne", "Evansville", "Carmel"],
          "MI": ["Lansing", "Grand Rapids", "Kalamazoo"], "OH": ["Toledo", "Dayton", "Akron"],
          "MO": ["Columbia", "Springfield", "St. Joseph"], "IA": ["Cedar Rapids", "Davenport"],
          "MN": ["Rochester", "Duluth"], "KY": ["Lexington", "Bowling Green"],
          "TN": ["Knoxville", "Chattanooga"]}
STREETS = ["Oak", "Maple", "Cedar", "Elm", "Lakeview", "Prairie", "Hillcrest", "Main",
           "Washington", "Lincoln", "Sunset", "River", "Meadow", "Park"]
VEHICLES = [("Ford", "F-150"), ("Chevrolet", "Silverado"), ("Toyota", "Camry"), ("Honda", "Accord"),
            ("Honda", "CR-V"), ("Toyota", "RAV4"), ("Nissan", "Altima"), ("Jeep", "Grand Cherokee"),
            ("Hyundai", "Elantra"), ("Subaru", "Outback"), ("Dodge", "Ram 1500"), ("Kia", "Sorento")]
EMPLOYERS = ["Midwest Packaging Co.", "Prairie Logistics LLC", "Lakeshore Fabrication",
             "Heartland Foods Distribution", "Riverbend Construction", "Tri-County Warehousing",
             "Great Plains Machining", "Summit Healthcare Services"]

LOB_LOSS_TYPES = {
    "auto": ["collision", "theft", "vandalism", "weather", "liability_injury"],
    "homeowners": ["water_damage", "fire", "weather", "theft", "liability_injury"],
    "workers_comp": ["workplace_injury"],
}
LOB_WEIGHTS = {"auto": 0.55, "homeowners": 0.30, "workers_comp": 0.15}

# Median cost ($) and lognormal sigma per (lob, loss_type)
COST_PARAMS = {
    ("auto", "collision"): (4200, 0.75), ("auto", "theft"): (9500, 0.7),
    ("auto", "vandalism"): (1800, 0.6), ("auto", "weather"): (3100, 0.7),
    ("auto", "liability_injury"): (14000, 0.9),
    ("homeowners", "water_damage"): (8200, 0.8), ("homeowners", "fire"): (38000, 1.0),
    ("homeowners", "weather"): (11000, 0.85), ("homeowners", "theft"): (4800, 0.7),
    ("homeowners", "liability_injury"): (17000, 0.9),
    ("workers_comp", "workplace_injury"): (9000, 1.0),
}

LOSS_CATEGORIES = ["collision", "theft", "vandalism", "weather", "water_damage", "fire",
                   "liability_injury", "workplace_injury"]

# --------------------------------------------------------------------------
# Narrative templates (legacy adjuster shorthand on purpose)
# --------------------------------------------------------------------------
NARR = {
    "collision": [
        "IV was stopped at light on {street} Ave when CV failed to stop and struck IV in rear.",
        "Insd states she was merging onto I-{hwy} and other veh changed lanes into her, contact on pass side.",
        "IV backing out of parking space at grocery store, struck light pole. Damage to rear bumper and tailgate.",
        "Insd lost control on wet pavement and slid into guardrail. Front end damage, airbags did not deploy.",
        "T-bone collision at intersection of {street} and {street2}. CV ran red light per insd.",
        "Insd rear-ended vehicle ahead in stop and go traffic. Minor front bumper damage to IV.",
        "Deer ran into roadway on County Rd {hwy}, insd swerved and struck ditch. Undercarriage damage.",
    ],
    "theft": [
        "Insd reports vehicle stolen from driveway overnight. Keys were in the home. No witnesses.",
        "Insd returned to find garage door open and power tools, bicycle and generator missing.",
        "Catalytic converter cut off IV while parked at work lot. Security camera not working per employer.",
        "Break-in at residence while family was out of town. Jewelry, laptop and TV taken.",
        "Veh stolen from apartment lot, recovered 3 days later stripped. Police notified.",
    ],
    "vandalism": [
        "Unknown party keyed both sides of IV and slashed two tires while parked on street.",
        "Rear window of IV smashed overnight, nothing taken. Insd believes neighborhood kids.",
        "Graffiti spray painted on hood and doors of IV in parking garage.",
    ],
    "weather": [
        "Hail storm passed through area, insd reports dents across roof and hood of IV.",
        "High winds brought down large oak limb onto roof. Shingles and gutters damaged, some interior leaking.",
        "Hail damage to roof and siding per insd, several neighbors also filing claims.",
        "Tree fell on IV during thunderstorm while parked in driveway. Windshield and roof crushed.",
        "Tornado warning in area, detached garage partially collapsed, vehicle inside damaged.",
    ],
    "water_damage": [
        "Supply line to upstairs washing machine burst, water came through kitchen ceiling.",
        "Water heater failed in basement overnight, approx 2 inches standing water, carpet and drywall wet.",
        "Frozen pipe burst in exterior wall during cold snap. Water damage to living room floor.",
        "Sump pump failed during heavy rain, finished basement flooded. Furniture and flooring damaged.",
        "Dishwasher leak went unnoticed for several days, subfloor soft and mold visible.",
    ],
    "fire": [
        "Kitchen grease fire spread to cabinets, FD responded. Smoke damage throughout first floor.",
        "Electrical fire started in garage, FD extinguished. Garage and contents a loss, smoke into house.",
        "Dryer vent fire in laundry room. Fire contained to room, heavy smoke odor through home.",
        "Fire started from space heater in bedroom. Insd and family evacuated safely.",
    ],
    "liability_injury": [
        "Clmt states she slipped on icy front walkway at insd residence while delivering package.",
        "IV struck pedestrian in crosswalk at low speed. Pedestrian transported by EMS.",
        "Insd dog bit neighbor on the hand in insd yard. Neighbor went to urgent care.",
        "Guest fell down basement stairs at insd home during party, complaining of back pain.",
        "IV struck CV at intersection, CV driver complaining of neck and shoulder pain at scene.",
    ],
    "workplace_injury": [
        "EE was lifting boxes from pallet and felt sharp pain in lower back. Reported to supervisor same day.",
        "EE slipped on wet floor in break room and fell on left wrist.",
        "EE hand caught in conveyor roller, laceration to two fingers, taken to ER for stitches.",
        "EE fell from ladder approx 6 ft while stocking shelves, landed on right shoulder.",
        "EE reports repetitive strain in both wrists from assembly line work over past months.",
        "Forklift backed into EE in warehouse aisle, contusion to leg and hip.",
    ],
}
INJURY_ADD = [
    " Insd reports neck and back pain, went to ER that evening.",
    " Passenger complained of whiplash and is seeing a chiropractor.",
    " Driver transported by ambulance, possible fractured arm.",
    " Clmt treating with physical therapy for shoulder injury.",
    " EE off work, doctor ordered MRI.",
]
LITIGATION_ADD = [
    " Clmt has retained an attorney, LOR received.",
    " Received letter of representation from atty office.",
    " Clmt stated they have already spoken to a lawyer.",
    " Atty for clmt requesting policy limits.",
]
TOTAL_LOSS_ADD = {
    "auto": [" Appraiser indicates vehicle is likely a total loss.",
             " Vehicle not recovered, treating as total loss.",
             " Repair est exceeds ACV, TL likely."],
    "homeowners": [" Structure deemed uninhabitable, family staying at hotel.",
                   " Contents in affected area appear to be a total loss.",
                   " Adjuster believes dwelling may be a total loss."],
}
FRAUD_ADD = [
    " Insd could not recall exact time of loss.",
    " Insd was vague on details and story changed on second call.",
    " Policy was bound only a few weeks before the loss.",
    " Insd requesting quick cash settlement, reluctant to provide receipts.",
    " No police report filed, insd says police would not come out.",
    " Insd recently increased coverage limits.",
    " Friend was driving at time of loss, not listed on policy.",
]
VAGUE = [
    "Insd called to report a loss, details to follow. Requested callback.",
    "Loss reported via agent, see attached. Need to contact insd.",
    "Insd reports damage, unsure of cause at this time.",
    "Call dropped during FNOL, left VM for insd.",
]
# Descriptions that plausibly belong to more than one category
AMBIGUOUS = {
    "weather": ["Water coming in through ceiling after storm last night.",
                "Damage to vehicle found in morning, possibly from hail or someone hitting it."],
    "water_damage": ["Water coming in through ceiling after storm last night.",
                     "Insd found water on floor near back door after heavy rain."],
    "vandalism": ["Damage to vehicle found in morning, possibly from hail or someone hitting it.",
                  "Window broken on IV, some items may be missing."],
    "theft": ["Window broken on IV, some items may be missing.",
              "Items missing from garage, door found damaged."],
    "collision": ["IV struck CV at intersection, CV driver complaining of neck and shoulder pain at scene.",
                  "Damage to vehicle found in morning, possibly from hail or someone hitting it."],
    "liability_injury": ["Visitor hurt at insd property, details unclear."],
    "workplace_injury": ["EE reports injury, supervisor to send incident report."],
    "fire": ["Smoke damage reported in kitchen, cause unknown."],
}


def _typos(text, rng):
    w = text.split(" ")
    for _ in range(max(1, len(w) // 12)):
        j = rng.randrange(len(w))
        if len(w[j]) > 4:
            k = rng.randrange(1, len(w[j]) - 1)
            w[j] = w[j][:k] + w[j][k + 1:] if rng.random() < 0.5 else w[j][:k] + w[j][k] + w[j][k:]
    return " ".join(w)


FILLER = [
    " Photos requested.", " Recorded statement taken.", " Insd cooperative.",
    " Awaiting estimate.", " Rental requested.", " Mitigation vendor dispatched.",
    " Will f/u w/ insd tomorrow.", "", "", "",
]


@dataclass
class Claim:
    claim_id: str
    policy_number: str
    line_of_business: str
    loss_type: str
    state: str
    city: str
    insured_name: str
    loss_date: str
    report_date: str
    policy_start_date: str
    policy_tenure_months: int
    days_policy_to_loss: int
    days_to_report: int
    insured_age: int
    annual_premium: float
    deductible: int
    coverage_limit: int
    prior_claims_3yr: int
    claim_amount_reported: float
    asset_age_years: int
    incident_hour: int
    is_weekend: int
    police_report_filed: int
    witness_present: int
    injury_reported: int
    attorney_involved: int
    total_loss_indicated: int
    coverage_increase_last_90d: int
    narrative: str
    # --- labels ---
    is_fraud: int = 0
    paid_amount: float = 0.0
    loss_category: str = ""
    extra: dict = field(default_factory=dict)

    def as_row(self) -> dict:
        d = asdict(self)
        d.pop("extra")
        return d


def _sig(x: float) -> float:
    return 1 / (1 + math.exp(-x))


def make_claim(i: int, rng: random.Random, today: date = date(2026, 9, 1),
               force: dict | None = None) -> Claim:
    """Generate one claim.  ``force`` pins specific attributes (used to build
    scenario documents), e.g. {"line_of_business": "auto", "fraud": True}."""
    force = force or {}
    lob = force.get("line_of_business") or rng.choices(
        list(LOB_WEIGHTS), weights=list(LOB_WEIGHTS.values()))[0]
    loss_type = force.get("loss_type") or rng.choice(LOB_LOSS_TYPES[lob])
    state = rng.choice(STATES)
    city = rng.choice(CITIES[state])

    # Latent "is this claim suspicious" propensity drives many features.
    fraud_prop = force.get("fraud_prop", rng.random())
    suspicious = fraud_prop > 0.86 if "fraud" not in force else force["fraud"]

    tenure = max(1, int(rng.expovariate(1 / 48)))
    if suspicious and rng.random() < 0.55:
        tenure = rng.randint(1, 4)
    days_policy_to_loss = min(tenure * 30, int(rng.uniform(0.1, 1.0) * tenure * 30) + 1)
    if suspicious and rng.random() < 0.5:
        days_policy_to_loss = rng.randint(3, 60)
        tenure = max(1, days_policy_to_loss // 30 + 1)

    days_to_report = int(rng.expovariate(1 / 3))
    if suspicious and rng.random() < 0.45:
        days_to_report = rng.randint(14, 75)
    if lob == "workers_comp" and rng.random() < 0.2:
        days_to_report += rng.randint(5, 30)  # WC late reporting is common & innocent

    loss_date = today - timedelta(days=rng.randint(5, 700))
    report_date = loss_date + timedelta(days=days_to_report)
    policy_start = loss_date - timedelta(days=days_policy_to_loss)

    insured_age = int(min(85, max(18, rng.gauss(46, 14))))
    prior = min(6, int(rng.expovariate(1 / 0.6)))
    if suspicious and rng.random() < 0.4:
        prior += rng.randint(1, 3)

    if lob == "auto":
        premium = rng.gauss(1450, 400)
        deductible = rng.choice([250, 500, 500, 1000, 1000])
        limit = rng.choice([50000, 100000, 250000])
        asset_age = rng.randint(0, 18)
    elif lob == "homeowners":
        premium = rng.gauss(1900, 600)
        deductible = rng.choice([500, 1000, 1000, 2500, 5000])
        limit = rng.choice([250000, 350000, 500000])
        asset_age = rng.randint(1, 90)
    else:
        premium = rng.gauss(42000, 15000)  # employer policy
        deductible = 0
        limit = 1000000
        asset_age = rng.randint(0, 35)  # employee tenure-ish proxy
    premium = round(max(400, premium), 2)

    hour = rng.choices(range(24), weights=[1, 1, 1, 1, 1, 2, 4, 6, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 6, 5, 4, 3, 2, 1])[0]
    if suspicious and rng.random() < 0.35:
        hour = rng.choice([0, 1, 2, 3, 4, 23])
    weekend = int(loss_date.weekday() >= 5)

    police = 0
    if loss_type in ("collision", "theft", "vandalism", "liability_injury"):
        police = int(rng.random() < (0.35 if suspicious else 0.8))
    elif loss_type == "fire":
        police = int(rng.random() < 0.3)
    witness = int(rng.random() < (0.15 if suspicious else 0.45))

    injury = int(loss_type in ("liability_injury", "workplace_injury")
                 or (loss_type == "collision" and rng.random() < (0.35 if suspicious else 0.15)))
    attorney = int(injury and rng.random() < (0.55 if suspicious else 0.18))
    total_loss = 0
    if loss_type == "theft" and lob == "auto":
        total_loss = int(rng.random() < 0.6)
    elif loss_type in ("collision", "fire", "weather"):
        total_loss = int(rng.random() < (0.28 if loss_type == "fire" else 0.08))
    cov_increase = int(rng.random() < (0.35 if suspicious else 0.04))

    for k in ("injury_reported", "attorney_involved", "total_loss_indicated",
              "police_report_filed", "witness_present", "coverage_increase_last_90d"):
        if k in force:
            locals_map = {"injury_reported": "injury", "attorney_involved": "attorney",
                          "total_loss_indicated": "total_loss", "police_report_filed": "police",
                          "witness_present": "witness", "coverage_increase_last_90d": "cov_increase"}
            # simple override
            if locals_map[k] == "injury": injury = force[k]
            if locals_map[k] == "attorney": attorney = force[k]
            if locals_map[k] == "total_loss": total_loss = force[k]
            if locals_map[k] == "police": police = force[k]
            if locals_map[k] == "witness": witness = force[k]
            if locals_map[k] == "cov_increase": cov_increase = force[k]

    # ---------------- true cost ----------------
    med, sig = COST_PARAMS[(lob, loss_type)]
    cost = med * math.exp(rng.gauss(0, sig))
    if injury and loss_type not in ("liability_injury", "workplace_injury"):
        cost *= 2.2
    if attorney:
        cost *= 2.6
    if total_loss:
        cost *= 2.4
    if lob == "auto":
        cost *= max(0.45, 1.15 - asset_age * 0.035)
    if lob == "homeowners":
        cost *= 1 + min(asset_age, 80) * 0.004
    cost *= 1 + (insured_age > 60) * 0.12 * (lob == "workers_comp")
    cost = min(cost, limit)
    cost = round(max(150.0, cost), 2)

    reported = cost * math.exp(rng.gauss(0.0, 0.55))  # FNOL estimates are rough
    if suspicious:
        reported *= rng.uniform(1.4, 2.8)
    reported = round(min(reported, limit * 1.2), 2)

    # --------------- fraud label ---------------
    z = (-5.1
         + 1.9 * (days_policy_to_loss < 60) + 0.9 * (tenure < 6)
         + 1.1 * (days_to_report > 14) + 0.45 * min(prior, 5)
         + 1.3 * math.log(max(reported, 1) / max(cost, 1)) * 2
         + 1.2 * cov_increase + 0.8 * (police == 0 and loss_type in ("theft", "collision", "vandalism"))
         + 0.6 * (hour in (0, 1, 2, 3, 4, 23)) + 0.7 * attorney * (days_to_report < 3)
         - 0.5 * witness)
    p_fraud = _sig(z)
    is_fraud = int(rng.random() < p_fraud) if "fraud" not in force else int(bool(force["fraud"]))

    # --------------- narrative ---------------
    street, street2 = rng.sample(STREETS, 2)
    text = rng.choice(NARR[loss_type]).format(street=street, street2=street2,
                                              hwy=rng.choice([55, 57, 64, 70, 74, 80, 88, 90, 94]))
    if injury and loss_type not in ("liability_injury", "workplace_injury"):
        text += rng.choice(INJURY_ADD)
    elif injury and rng.random() < 0.5:
        text += rng.choice(INJURY_ADD)
    if attorney:
        text += rng.choice(LITIGATION_ADD)
    if total_loss:
        text += rng.choice(TOTAL_LOSS_ADD.get(lob, TOTAL_LOSS_ADD["homeowners"]))
    if is_fraud and rng.random() < 0.6:
        text += rng.choice(FRAUD_ADD)
    elif rng.random() < 0.05:  # innocent claims sometimes look odd too
        text += rng.choice(FRAUD_ADD)
    text += rng.choice(FILLER) + rng.choice(FILLER)
    # Realism: busy adjusters, vague callers, typos, and genuinely ambiguous losses
    r = rng.random()
    if r < 0.06:
        text = text.split(".")[0] + "."
    elif r < 0.12:
        text = rng.choice(VAGUE) + rng.choice(FILLER)
    elif r < 0.17:
        text = rng.choice(AMBIGUOUS.get(loss_type, VAGUE)) + rng.choice(FILLER)
    if rng.random() < 0.15:
        text = _typos(text, rng)

    name = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
    prefix = {"auto": "PA", "homeowners": "HO", "workers_comp": "WC"}[lob]
    return Claim(
        claim_id=f"CLM-{loss_date.year}-{100000 + i}",
        policy_number=f"{prefix}{rng.randint(1000000, 9999999)}",
        line_of_business=lob, loss_type=loss_type, state=state, city=city, insured_name=name,
        loss_date=loss_date.isoformat(), report_date=report_date.isoformat(),
        policy_start_date=policy_start.isoformat(), policy_tenure_months=tenure,
        days_policy_to_loss=days_policy_to_loss, days_to_report=days_to_report,
        insured_age=insured_age, annual_premium=premium, deductible=deductible,
        coverage_limit=limit, prior_claims_3yr=prior, claim_amount_reported=reported,
        asset_age_years=asset_age, incident_hour=hour, is_weekend=weekend,
        police_report_filed=police, witness_present=witness, injury_reported=injury,
        attorney_involved=attorney, total_loss_indicated=total_loss,
        coverage_increase_last_90d=cov_increase, narrative=text.strip(),
        is_fraud=is_fraud, paid_amount=cost if not is_fraud else round(cost * rng.uniform(0, 0.4), 2),
        loss_category=loss_type,
        extra={"street": street, "vehicle": rng.choice(VEHICLES),
               "employer": rng.choice(EMPLOYERS), "p_fraud": p_fraud,
               "true_cost": cost},
    )
