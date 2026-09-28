# Sample documents

All data is fictitious. Each scenario exists as a PDF FNOL form (`fnol/`) and as a JSON API payload (`claims/`).

| ID | Scenario | Line | Expected routing | PDF |
|---|---|---|---|---|
| A01 | Parking-lot fender bender | Personal Auto | `FAST_TRACK` | `A01_parking_lot_fender_bender.pdf` |
| A02 | Rear-ended at a light, neck injury, attorney | Personal Auto | `COMPLEX_SENIOR_ADJUSTER` | `A02_rear_ended_at_a_light_neck_injury_attorn.pdf` |
| A03 | Vehicle stolen 3 weeks after policy bound | Personal Auto | `SIU_REFERRAL` | `A03_vehicle_stolen_3_weeks_after_policy_boun.pdf` |
| A04 | Hail damage, neighbors also filing | Personal Auto | `FAST_TRACK` | `A04_hail_damage_neighbors_also_filing.pdf` |
| A05 | Keyed car, two slashed tires | Personal Auto | `FAST_TRACK` | `A05_keyed_car_two_slashed_tires.pdf` |
| A06 | Deer strike, likely total loss | Personal Auto | `STANDARD_ADJUSTER` | `A06_deer_strike_likely_total_loss.pdf` |
| A07 | Late-night single-car crash, friend driving | Personal Auto | `SIU_REFERRAL` | `A07_late_night_single_car_crash_friend_drivi.pdf` |
| H01 | Washing machine supply line burst | Homeowners | `STANDARD_ADJUSTER` | `H01_washing_machine_supply_line_burst.pdf` |
| H02 | Kitchen fire, family displaced | Homeowners | `COMPLEX_SENIOR_ADJUSTER` | `H02_kitchen_fire_family_displaced.pdf` |
| H03 | Wind damage to roof after storm | Homeowners | `STANDARD_ADJUSTER` | `H03_wind_damage_to_roof_after_storm.pdf` |
| H04 | Burglary right after coverage increase | Homeowners | `SIU_REFERRAL` | `H04_burglary_right_after_coverage_increase.pdf` |
| H05 | Delivery driver slipped on icy walkway, attorney | Homeowners | `COMPLEX_SENIOR_ADJUSTER` | `H05_delivery_driver_slipped_on_icy_walkway_a.pdf` |
| H06 | Sump pump failure, finished basement | Homeowners | `STANDARD_ADJUSTER` | `H06_sump_pump_failure_finished_basement.pdf` |
| W01 | Lifting strain, reported same day | Workers' Compensation | `STANDARD_ADJUSTER` | `W01_lifting_strain_reported_same_day.pdf` |
| W02 | Hand caught in conveyor | Workers' Compensation | `STANDARD_ADJUSTER` | `W02_hand_caught_in_conveyor.pdf` |
| W03 | Ladder fall, shoulder surgery, attorney | Workers' Compensation | `COMPLEX_SENIOR_ADJUSTER` | `W03_ladder_fall_shoulder_surgery_attorney.pdf` |
| W04 | Repetitive strain reported weeks later | Workers' Compensation | `STANDARD_ADJUSTER` | `W04_repetitive_strain_reported_weeks_later.pdf` |

`SCAN_*.pdf` are image-only "fax" copies of A03 and H01, to show Textract OCR.

`batch/holdout_claims.csv` has 200 random claims the models never saw, with the true fraud label and incurred cost for comparison.
