"""Hand-crafted test scenarios. Each one tells a small story the customer can recognize,
and states the routing we *expect* the system to produce.

Used by:
  generate_documents.py  -> sample_docs/fnol/*.pdf   (FNOL forms for Textract)
                          -> sample_docs/claims/*.json (JSON API payloads)
  scripts/smoke_test.py  -> checks actual routing vs. expected_route
"""

SCENARIOS = [
    # ------------------------------------------------------------------ AUTO
    dict(id="A01", title="Parking-lot fender bender", expected_route="FAST_TRACK",
         line_of_business="auto", loss_type="collision", insured_name="Linda Hughes", insured_age=52,
         city="Naperville", state="IL", loss_date="2026-08-14", report_date="2026-08-14",
         policy_start_date="2019-03-01", loss_time="12:40", amount=1850, deductible=500, premium=1320,
         limit=100000, prior_claims=0, asset_year=2020, vehicle="2020 Honda CR-V", police=0, witness=1,
         injury=0, attorney=0, total_loss=0, cov_increase=0,
         narrative="Insd backing out of space at grocery store lot, struck bollard. Damage to rear bumper "
                   "and liftgate. No other vehicles involved. Photos received. Insd cooperative."),
    dict(id="A02", title="Rear-ended at a light, neck injury, attorney", expected_route="COMPLEX_SENIOR_ADJUSTER",
         line_of_business="auto", loss_type="collision", insured_name="Marcus Delgado", insured_age=38,
         city="Joliet", state="IL", loss_date="2026-07-02", report_date="2026-07-03",
         policy_start_date="2021-06-15", loss_time="17:55", amount=12500, deductible=500, premium=1610,
         limit=250000, prior_claims=0, asset_year=2018, vehicle="2018 Toyota Camry", police=1, witness=1,
         injury=1, attorney=1, total_loss=0, cov_increase=0,
         narrative="IV stopped at red light on Larkin Ave when CV failed to stop and struck IV in rear at "
                   "approx 35 mph. Insd transported by ambulance w/ neck and back pain, now treating w/ "
                   "chiropractor. Received LOR from atty office on 7/10. Police report on file."),
    dict(id="A03", title="Vehicle stolen 3 weeks after policy bound", expected_route="SIU_REFERRAL",
         line_of_business="auto", loss_type="theft", insured_name="Derek Voss", insured_age=29,
         city="Rockford", state="IL", loss_date="2026-06-21", report_date="2026-07-19",
         policy_start_date="2026-05-30", loss_time="02:30", amount=41000, deductible=500, premium=1480,
         limit=50000, prior_claims=3, asset_year=2016, vehicle="2016 Dodge Ram 1500", police=0, witness=0,
         injury=0, attorney=0, total_loss=1, cov_increase=1,
         narrative="Insd reports vehicle stolen from street overnight. Insd could not recall exact time "
                   "of loss and story changed on second call. No police report filed, insd says police "
                   "would not come out. Recently added comprehensive coverage. Insd requesting quick "
                   "cash settlement, reluctant to provide purchase receipts for aftermarket parts."),
    dict(id="A04", title="Hail damage, neighbors also filing", expected_route="FAST_TRACK",
         line_of_business="auto", loss_type="weather", insured_name="Grace Lindqvist", insured_age=61,
         city="Davenport", state="IA", loss_date="2026-05-18", report_date="2026-05-19",
         policy_start_date="2015-09-10", loss_time="16:10", amount=4200, deductible=1000, premium=1210,
         limit=100000, prior_claims=1, asset_year=2021, vehicle="2021 Subaru Outback", police=0, witness=0,
         injury=0, attorney=0, total_loss=0, cov_increase=0,
         narrative="Hail storm passed through area, insd reports dents across roof, hood and trunk lid. "
                   "Several neighbors also filing claims. Awaiting PDR estimate."),
    dict(id="A05", title="Keyed car, two slashed tires", expected_route="FAST_TRACK",
         line_of_business="auto", loss_type="vandalism", insured_name="Priya Patel", insured_age=34,
         city="Madison", state="WI", loss_date="2026-08-30", report_date="2026-08-31",
         policy_start_date="2022-01-20", loss_time="22:00", amount=1400, deductible=250, premium=1390,
         limit=100000, prior_claims=0, asset_year=2019, vehicle="2019 Hyundai Elantra", police=1, witness=0,
         injury=0, attorney=0, total_loss=0, cov_increase=0,
         narrative="Unknown party keyed both sides of IV and slashed two tires while parked on street "
                   "outside insd apartment. Police report filed. Photos received."),
    dict(id="A06", title="Deer strike, likely total loss", expected_route="STANDARD_ADJUSTER",
         line_of_business="auto", loss_type="collision", insured_name="Tom Kowalski", insured_age=57,
         city="Green Bay", state="WI", loss_date="2026-04-11", report_date="2026-04-11",
         policy_start_date="2010-11-01", loss_time="21:15", amount=9800, deductible=500, premium=1180,
         limit=100000, prior_claims=0, asset_year=2012, vehicle="2012 Chevrolet Silverado", police=1, witness=0,
         injury=0, attorney=0, total_loss=1, cov_increase=0,
         narrative="Deer ran into roadway on County Rd 32, insd struck deer and went into ditch. Front "
                   "end and radiator destroyed, airbags deployed. Appraiser indicates vehicle is likely "
                   "a total loss given age. Insd not injured."),
    dict(id="A07", title="Late-night single-car crash, friend driving", expected_route="SIU_REFERRAL",
         line_of_business="auto", loss_type="collision", insured_name="Kyle Brandt", insured_age=24,
         city="Toledo", state="OH", loss_date="2026-08-02", report_date="2026-08-24",
         policy_start_date="2026-06-25", loss_time="03:10", amount=27500, deductible=500, premium=2150,
         limit=50000, prior_claims=2, asset_year=2017, vehicle="2017 Nissan Altima", police=0, witness=0,
         injury=1, attorney=1, total_loss=1, cov_increase=1,
         narrative="Friend was driving at time of loss, not listed on policy. Vehicle left roadway and "
                   "struck tree. No police report. Driver now claiming back injury and has already "
                   "spoken to a lawyer. Insd vague on details."),
    # ------------------------------------------------------------ HOMEOWNERS
    dict(id="H01", title="Washing machine supply line burst", expected_route="STANDARD_ADJUSTER",
         line_of_business="homeowners", loss_type="water_damage", insured_name="Karen Whitaker", insured_age=47,
         city="Carmel", state="IN", loss_date="2026-08-09", report_date="2026-08-09",
         policy_start_date="2017-04-12", loss_time="09:20", amount=14500, deductible=1000, premium=2050,
         limit=350000, prior_claims=0, asset_year=1998, vehicle="", police=0, witness=0,
         injury=0, attorney=0, total_loss=0, cov_increase=0,
         narrative="Supply line to upstairs washing machine burst, water came through kitchen ceiling. "
                   "Mitigation vendor dispatched, drying equipment in place. Kitchen cabinets and "
                   "flooring affected."),
    dict(id="H02", title="Kitchen fire, family displaced", expected_route="COMPLEX_SENIOR_ADJUSTER",
         line_of_business="homeowners", loss_type="fire", insured_name="Samuel Okafor", insured_age=44,
         city="Lexington", state="KY", loss_date="2026-07-19", report_date="2026-07-19",
         policy_start_date="2014-02-01", loss_time="18:45", amount=120000, deductible=1000, premium=2400,
         limit=500000, prior_claims=0, asset_year=1965, vehicle="", police=0, witness=1,
         injury=0, attorney=0, total_loss=1, cov_increase=0,
         narrative="Kitchen grease fire spread to cabinets and attic, FD responded. Heavy smoke damage "
                   "throughout first and second floor. Structure deemed uninhabitable, family staying at "
                   "hotel. ALE needed."),
    dict(id="H03", title="Wind damage to roof after storm", expected_route="STANDARD_ADJUSTER",
         line_of_business="homeowners", loss_type="weather", insured_name="Hector Morales", insured_age=66,
         city="Columbia", state="MO", loss_date="2026-06-03", report_date="2026-06-04",
         policy_start_date="2008-05-20", loss_time="20:30", amount=9600, deductible=1000, premium=1780,
         limit=350000, prior_claims=1, asset_year=1984, vehicle="", police=0, witness=0,
         injury=0, attorney=0, total_loss=0, cov_increase=0,
         narrative="High winds brought down large oak limb onto roof. Shingles and gutters damaged, "
                   "some interior leaking in back bedroom. Roofer tarped roof."),
    dict(id="H04", title="Burglary right after coverage increase", expected_route="SIU_REFERRAL",
         line_of_business="homeowners", loss_type="theft", insured_name="Victor Harrington", insured_age=41,
         city="Chattanooga", state="TN", loss_date="2026-07-26", report_date="2026-08-20",
         policy_start_date="2026-06-10", loss_time="01:00", amount=48000, deductible=500, premium=1650,
         limit=250000, prior_claims=2, asset_year=2004, vehicle="", police=0, witness=0,
         injury=0, attorney=0, total_loss=0, cov_increase=1,
         narrative="Insd reports break-in while family was out of town. Jewelry, watches, two laptops "
                   "and TVs taken. Insd recently increased coverage limits and added jewelry rider. "
                   "No police report filed. Insd reluctant to provide receipts."),
    dict(id="H05", title="Delivery driver slipped on icy walkway, attorney", expected_route="COMPLEX_SENIOR_ADJUSTER",
         line_of_business="homeowners", loss_type="liability_injury", insured_name="Nancy Everett", insured_age=72,
         city="Duluth", state="MN", loss_date="2026-01-28", report_date="2026-02-02",
         policy_start_date="2003-10-01", loss_time="11:05", amount=35000, deductible=1000, premium=1520,
         limit=300000, prior_claims=0, asset_year=1972, vehicle="", police=0, witness=1,
         injury=1, attorney=1, total_loss=0, cov_increase=0,
         narrative="Clmt states she slipped on icy front walkway at insd residence while delivering "
                   "package. Clmt fractured wrist, had surgery. Atty for clmt sent LOR and is requesting "
                   "policy limits."),
    dict(id="H06", title="Sump pump failure, finished basement", expected_route="STANDARD_ADJUSTER",
         line_of_business="homeowners", loss_type="water_damage", insured_name="Jennifer Nguyen", insured_age=39,
         city="Cedar Rapids", state="IA", loss_date="2026-05-07", report_date="2026-05-08",
         policy_start_date="2020-07-15", loss_time="04:30", amount=11200, deductible=1000, premium=1690,
         limit=350000, prior_claims=0, asset_year=2006, vehicle="", police=0, witness=0,
         injury=0, attorney=0, total_loss=0, cov_increase=0,
         narrative="Sump pump failed during heavy rain, finished basement flooded approx 3 inches. "
                   "Carpet, drywall and furniture damaged. Verify sump endorsement on policy."),
    # ------------------------------------------------------- WORKERS' COMP
    dict(id="W01", title="Lifting strain, reported same day", expected_route="STANDARD_ADJUSTER",
         line_of_business="workers_comp", loss_type="workplace_injury", insured_name="Prairie Logistics LLC",
         claimant="Luis Ramirez", insured_age=33,
         city="Peoria", state="IL", loss_date="2026-08-18", report_date="2026-08-18",
         policy_start_date="2019-01-01", loss_time="10:30", amount=3500, deductible=0, premium=48000,
         limit=1000000, prior_claims=1, asset_year=2021, vehicle="", police=0, witness=1,
         injury=1, attorney=0, total_loss=0, cov_increase=0,
         narrative="EE was lifting boxes from pallet and felt sharp pain in lower back. Reported to "
                   "supervisor same day, seen at occupational clinic, light duty 1 week."),
    dict(id="W02", title="Hand caught in conveyor", expected_route="STANDARD_ADJUSTER",
         line_of_business="workers_comp", loss_type="workplace_injury", insured_name="Midwest Packaging Co.",
         claimant="Olga Novak", insured_age=45,
         city="Fort Wayne", state="IN", loss_date="2026-07-08", report_date="2026-07-09",
         policy_start_date="2016-01-01", loss_time="14:15", amount=9000, deductible=0, premium=62000,
         limit=1000000, prior_claims=2, asset_year=2012, vehicle="", police=0, witness=1,
         injury=1, attorney=0, total_loss=0, cov_increase=0,
         narrative="EE hand caught in conveyor roller, laceration to two fingers, taken to ER for "
                   "stitches. Guard on roller was missing per supervisor. Off work 2 weeks."),
    dict(id="W03", title="Ladder fall, shoulder surgery, attorney", expected_route="COMPLEX_SENIOR_ADJUSTER",
         line_of_business="workers_comp", loss_type="workplace_injury", insured_name="Riverbend Construction",
         claimant="Tyrone Jackson", insured_age=58,
         city="Akron", state="OH", loss_date="2026-03-14", report_date="2026-03-20",
         policy_start_date="2012-01-01", loss_time="08:40", amount=60000, deductible=0, premium=91000,
         limit=1000000, prior_claims=3, asset_year=2001, vehicle="", police=0, witness=1,
         injury=1, attorney=1, total_loss=0, cov_increase=0,
         narrative="EE fell from ladder approx 8 ft while framing, landed on right shoulder. Torn rotator "
                   "cuff, surgery scheduled. EE has retained an attorney, LOR received."),
    dict(id="W04", title="Repetitive strain reported weeks later", expected_route="STANDARD_ADJUSTER",
         line_of_business="workers_comp", loss_type="workplace_injury", insured_name="Lakeshore Fabrication",
         claimant="Heather Bishop", insured_age=36,
         city="Kalamazoo", state="MI", loss_date="2026-06-01", report_date="2026-07-06",
         policy_start_date="2018-01-01", loss_time="15:00", amount=7000, deductible=0, premium=39000,
         limit=1000000, prior_claims=0, asset_year=2020, vehicle="", police=0, witness=0,
         injury=1, attorney=0, total_loss=0, cov_increase=0,
         narrative="EE reports repetitive strain in both wrists from assembly line work over past "
                   "months. Symptoms worsened, saw PCP who recommended splints and ergonomic review."),
]

LOSS_TYPE_LABELS = {
    "collision": "Collision", "theft": "Theft / Burglary", "vandalism": "Vandalism / Malicious Mischief",
    "weather": "Wind / Hail / Storm", "water_damage": "Water Damage", "fire": "Fire / Smoke",
    "liability_injury": "Liability - Bodily Injury", "workplace_injury": "Workplace Injury",
}
LOB_LABELS = {"auto": "Personal Auto", "homeowners": "Homeowners", "workers_comp": "Workers' Compensation"}
