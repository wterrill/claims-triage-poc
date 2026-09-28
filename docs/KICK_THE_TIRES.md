# Kick the tires: a 20-minute guided tour

You'll need the **console URL** and the **API key** we sent you. All data is fictitious.

## 1. Open the console (2 min)
Paste the API key into the box at the top right. The status light should turn green ("Models in service"). If it's yellow, click **Wake models** and wait about 30 seconds: the models scale to zero when nobody is using them.

## 2. Process a paper form (5 min)
On **Upload FNOL document**, click **Run** next to these samples and compare the decisions:

| Try | What to notice |
|---|---|
| **A01** Parking-lot fender bender | Fast-track: low fraud risk, low severity |
| **A03** Vehicle stolen 3 weeks after policy bound | SIU referral, with the reasons: claimed amount, prior claims, recent coverage increase |
| **A03-SCAN** the same claim as a crooked, speckled fax | Textract still reads it and the decision matches |
| **H02** Kitchen fire | Complex adjuster: predicted cost is well above $100K, and the narrative flags a total loss |
| **W03** Ladder fall with attorney | Complex adjuster because of litigation risk |

Open **Document extraction → Parsed claim** to see exactly what was read from the form.

## 3. Use your own form (3 min)
Drag any PDF or photo of an FNOL form onto the upload box. Forms that use labels like *Date of Loss:*, *Policy Number:* and *Description of Loss* work best. Anything the form doesn't provide is left blank and filled in from the narrative where possible.

## 4. Play "what if" with the API (5 min)
On **Submit claim (API)**, load **A01** (fraud 1%, fast-track). Then edit the JSON and resubmit after each step:

1. Set `policy_effective_date` to `2026-07-31` (two weeks before the loss) and `report_date` to `2026-09-10` (reported late). Fraud rises to about 14%. Two odd facts on their own aren't enough to raise a flag.
2. Also set `estimated_loss_amount` to `9500`. Fraud rises to about 50%, and the claim moves to a **standard adjuster** with "moderate fraud indicators".
3. Also set `prior_claims_3yr` to `3`. Fraud rises to about 75% and the claim becomes an **SIU referral**, with the reasons listed.

Start again from A01 and append *"Driver transported by ambulance, possible fractured arm."* to `description`. The narrative model raises the injury flag (about 87%) and the claim is no longer fast-tracked, even though the form says "no injuries". Set `attorney_involved` to `true` and it moves to the **complex** queue.

This is the same request your core systems would send.

## 5. Review the audit trail (2 min)
**History** lists every decision. Click one to see the full record: model scores, reasons and latency.

## What this POC is (and isn't)
- **It is** a working pattern: SageMaker-hosted models behind a secured API, chained together with business rules you can read.
- **It isn't** trained on your data. With a few years of your closed claims (even an export from a legacy system), the same pipeline retrains and redeploys with one command.
- Questions we'd like your view on: Which routing thresholds match your SIU and complex-claims appetite? Which systems would call this API (FNOL intake, claims admin, agent portal)?
