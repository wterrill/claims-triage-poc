"""Generate sample documents for kicking the tires.

Writes to sample_docs/:
  fnol/<ID>_<slug>.pdf           legacy-style First Notice of Loss forms (one per scenario)
  fnol/SCAN_<ID>_<slug>.pdf      two "faxed/scanned" image-only PDFs (Textract has to OCR them)
  claims/<ID>.json               the same scenarios as JSON API payloads
  batch/holdout_claims.csv       25 unseen random claims for bulk API testing
  README.md                      scenario catalogue with expected routing

All names, policies and the carrier itself are fictitious.
"""
import csv
import json
import os
import random
import re
import sys
from datetime import date

from PIL import Image, ImageDraw, ImageFilter, ImageFont
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from claimgen import make_claim  # noqa: E402
from scenarios import LOB_LABELS, LOSS_TYPE_LABELS, SCENARIOS  # noqa: E402

OUT = os.path.join(os.path.dirname(HERE), "sample_docs")
CARRIER = "LAKESIDE MUTUAL CASUALTY CO."
DISCLAIMER = "SAMPLE DOCUMENT - FICTITIOUS DATA FOR DEMONSTRATION ONLY"


def mdy(iso):
    d = date.fromisoformat(iso)
    return d.strftime("%m/%d/%Y")


def slug(s):
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")[:40]


def form_fields(s, idx):
    """Return (left_col, right_col) lists of (label, value)."""
    lob = s["line_of_business"]
    claim_no = f"CLM-2026-{700100 + idx}"
    pol_prefix = {"auto": "PA", "homeowners": "HO", "workers_comp": "WC"}[lob]
    pol = f"{pol_prefix}{4400000 + idx * 7919}"
    yn = lambda v: "Yes" if v else "No"  # noqa: E731
    left = [("Claim Number", claim_no), ("Policy Number", pol),
            ("Line of Business", LOB_LABELS[lob])]
    if lob == "workers_comp":
        left += [("Employer", s["insured_name"]), ("Employee", s.get("claimant", "")),
                 ("Employee Age", s["insured_age"])]
    else:
        left += [("Named Insured", s["insured_name"]), ("Insured Age", s["insured_age"])]
    left += [("Policy Effective Date", mdy(s["policy_start_date"])),
             ("Date of Loss", mdy(s["loss_date"])), ("Time of Loss", s["loss_time"]),
             ("Date Reported", mdy(s["report_date"])),
             ("Loss Location", f'{s["city"]}, {s["state"]}')]
    right = [("Type of Loss", LOSS_TYPE_LABELS[s["loss_type"]]),
             ("Estimated Amount of Loss", f'${s["amount"]:,.2f}'),
             ("Deductible", f'${s["deductible"]:,.0f}'),
             ("Annual Premium", f'${s["premium"]:,.2f}'),
             ("Coverage Limit", f'${s["limit"]:,.0f}'),
             ("Prior Claims (Last 3 Years)", s["prior_claims"])]
    if lob == "auto":
        right += [("Vehicle", s["vehicle"]), ("Vehicle Year", s["asset_year"])]
    elif lob == "homeowners":
        right += [("Year Built", s["asset_year"])]
    else:
        right += [("Year of Hire", s["asset_year"])]
    right += [("Police Report Filed", yn(s["police"])), ("Witnesses", yn(s["witness"])),
              ("Injuries Reported", yn(s["injury"])), ("Attorney Involved", yn(s["attorney"])),
              ("Coverage Change in Last 90 Days", yn(s["cov_increase"]))]
    return claim_no, pol, left, right


def api_payload(s, claim_no, pol):
    p = {
        "claim_number": claim_no, "policy_number": pol,
        "line_of_business": s["line_of_business"], "loss_type": s["loss_type"],
        "insured_name": s["insured_name"], "insured_age": s["insured_age"],
        "loss_date": s["loss_date"], "loss_time": s["loss_time"], "report_date": s["report_date"],
        "policy_effective_date": s["policy_start_date"],
        "loss_location": {"city": s["city"], "state": s["state"]},
        "estimated_loss_amount": s["amount"], "deductible": s["deductible"],
        "annual_premium": s["premium"], "coverage_limit": s["limit"],
        "prior_claims_3yr": s["prior_claims"], "asset_year": s["asset_year"],
        "police_report_filed": bool(s["police"]), "witnesses": bool(s["witness"]),
        "injuries_reported": bool(s["injury"]), "attorney_involved": bool(s["attorney"]),
        "coverage_change_last_90_days": bool(s["cov_increase"]),
        "description": s["narrative"],
    }
    if s.get("claimant"):
        p["claimant_name"] = s["claimant"]
    return p


def wrap(text, width_chars):
    words, lines, cur = text.split(), [], ""
    for w in words:
        if len(cur) + len(w) + 1 > width_chars:
            lines.append(cur)
            cur = w
        else:
            cur = (cur + " " + w).strip()
    if cur:
        lines.append(cur)
    return lines


def draw_pdf(path, s, claim_no, left, right):
    c = canvas.Canvas(path, pagesize=letter)
    W, H = letter
    c.setTitle(f"FNOL {claim_no}")
    # header
    c.setFillColor(colors.HexColor("#1f3a5f"))
    c.rect(0.5 * inch, H - 1.15 * inch, W - inch, 0.6 * inch, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 15)
    c.drawString(0.65 * inch, H - 0.8 * inch, CARRIER)
    c.setFont("Helvetica", 9)
    c.drawString(0.65 * inch, H - 1.02 * inch, "FIRST NOTICE OF LOSS / CLAIM REPORT")
    c.drawRightString(W - 0.65 * inch, H - 0.8 * inch, "Form FNOL-100 (Rev. 03/2009)")
    c.setFillColor(colors.HexColor("#b00020"))
    c.setFont("Helvetica-Bold", 8)
    c.drawCentredString(W / 2, H - 1.35 * inch, DISCLAIMER)

    # field grid
    c.setFillColor(colors.black)
    y0 = H - 1.7 * inch
    for col, items in ((0.6 * inch, left), (4.3 * inch, right)):
        y = y0
        for label, val in items:
            c.setFont("Helvetica-Bold", 8.5)
            c.drawString(col, y, f"{label}:")
            lw = c.stringWidth(f"{label}: ", "Helvetica-Bold", 8.5)
            c.setFont("Courier", 9.5)
            c.drawString(col + lw, y, str(val))
            c.setStrokeColor(colors.HexColor("#cccccc"))
            c.line(col, y - 4, col + 3.4 * inch, y - 4)
            y -= 0.3 * inch
    y = y0 - max(len(left), len(right)) * 0.3 * inch - 0.25 * inch

    # description
    c.setStrokeColor(colors.black)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(0.6 * inch, y, "DESCRIPTION OF LOSS")
    c.rect(0.55 * inch, y - 2.0 * inch, W - 1.1 * inch, 1.85 * inch, stroke=1, fill=0)
    c.setFont("Courier", 9.5)
    ty = y - 0.35 * inch
    for line in wrap(s["narrative"], 88):
        c.drawString(0.7 * inch, ty, line)
        ty -= 0.2 * inch
    y -= 2.35 * inch
    c.setFont("Helvetica-Bold", 10)
    c.drawString(0.6 * inch, y, "REPORTED BY")
    c.setFont("Helvetica", 9)
    reporter = s.get("claimant") or s["insured_name"]
    c.drawString(0.6 * inch, y - 0.25 * inch, f"Name: {reporter}      Relationship: "
                 f"{'Employee' if s.get('claimant') else 'Named Insured'}      Method: Phone")
    c.drawString(0.6 * inch, y - 0.6 * inch, "Signature: ______________________________      "
                 "Agent Code: 0417")
    c.setFont("Helvetica-Oblique", 7)
    c.drawString(0.6 * inch, 0.5 * inch, f"{DISCLAIMER}.  Scenario {s['id']}.")
    c.save()


def draw_scan(path, s, claim_no, left, right, seed):
    """Render the form as a skewed, noisy grayscale image (a 'faxed' copy) inside a PDF."""
    rng = random.Random(seed)
    Wp, Hp = 1700, 2200  # ~200 dpi letter
    img = Image.new("L", (Wp, Hp), 250)
    d = ImageDraw.Draw(img)
    try:
        fb = ImageFont.truetype("DejaVuSans-Bold.ttf", 30)
        fr = ImageFont.truetype("DejaVuSansMono.ttf", 26)
        fs = ImageFont.truetype("DejaVuSans.ttf", 22)
    except OSError:
        fb = fr = fs = ImageFont.load_default()
    d.text((110, 90), CARRIER + " - FIRST NOTICE OF LOSS", fill=20, font=fb)
    d.text((110, 140), "Form FNOL-100 (Rev. 03/2009)   ** FAX COPY **", fill=40, font=fs)
    d.text((110, 180), DISCLAIMER, fill=40, font=fs)
    y = 260
    for label, val in left + right:
        d.text((110, y), f"{label}: {val}", fill=25, font=fr)
        y += 46
    y += 30
    d.text((110, y), "DESCRIPTION OF LOSS", fill=15, font=fb)
    y += 50
    for line in wrap(s["narrative"], 80):
        d.text((110, y), line, fill=30, font=fr)
        y += 38
    y += 30
    d.text((110, y), f"REPORTED BY  Name: {s.get('claimant') or s['insured_name']}", fill=30, font=fs)
    img = img.rotate(rng.uniform(-1.2, 1.2), fillcolor=250, resample=Image.BICUBIC)
    px = img.load()
    for _ in range(40000):  # speckle noise
        x, yy = rng.randrange(Wp), rng.randrange(Hp)
        px[x, yy] = rng.choice([0, 90, 255])
    img = img.filter(ImageFilter.GaussianBlur(0.6))
    tmp = path.replace(".pdf", ".png")
    img.save(tmp)
    c = canvas.Canvas(path, pagesize=letter)
    c.drawImage(tmp, 0, 0, width=letter[0], height=letter[1])
    c.save()
    os.remove(tmp)


def main():
    for sub in ("fnol", "claims", "batch"):
        os.makedirs(os.path.join(OUT, sub), exist_ok=True)
    rows, index = [], []
    for idx, s in enumerate(SCENARIOS):
        claim_no, pol, left, right = form_fields(s, idx)
        name = f"{s['id']}_{slug(s['title'])}"
        draw_pdf(os.path.join(OUT, "fnol", name + ".pdf"), s, claim_no, left, right)
        if s["id"] in ("A03", "H01"):
            draw_scan(os.path.join(OUT, "fnol", f"SCAN_{name}.pdf"), s, claim_no, left, right, idx)
        json.dump(api_payload(s, claim_no, pol), open(os.path.join(OUT, "claims", f"{s['id']}.json"), "w"), indent=2)
        rows.append((s["id"], s["title"], LOB_LABELS[s["line_of_business"]], s["expected_route"], name + ".pdf"))
        index.append({"id": s["id"], "title": s["title"], "line": LOB_LABELS[s["line_of_business"]],
                      "expected_route": s["expected_route"], "pdf": f"fnol/{name}.pdf",
                      "json": f"claims/{s['id']}.json"})
        if s["id"] in ("A03", "H01"):
            index.append({"id": s["id"] + "-SCAN", "title": s["title"] + " (faxed scan)",
                          "line": LOB_LABELS[s["line_of_business"]], "expected_route": s["expected_route"],
                          "pdf": f"fnol/SCAN_{name}.pdf", "json": None})

    # hold-out batch (different seed from training data)
    rng = random.Random(2026)
    batch = []
    for i in range(200):
        c = make_claim(900000 + i, rng)
        batch.append({
            "claim_number": c.claim_id, "policy_number": c.policy_number,
            "line_of_business": c.line_of_business, "loss_type": c.loss_type,
            "insured_name": c.insured_name, "insured_age": c.insured_age,
            "loss_date": c.loss_date, "loss_time": f"{c.incident_hour:02d}:00", "report_date": c.report_date,
            "policy_effective_date": c.policy_start_date, "estimated_loss_amount": c.claim_amount_reported,
            "deductible": c.deductible, "annual_premium": c.annual_premium, "coverage_limit": c.coverage_limit,
            "prior_claims_3yr": c.prior_claims_3yr, "asset_year": date.fromisoformat(c.loss_date).year - c.asset_age_years,
            "police_report_filed": c.police_report_filed, "witnesses": c.witness_present,
            "injuries_reported": c.injury_reported, "attorney_involved": c.attorney_involved,
            "coverage_change_last_90_days": c.coverage_increase_last_90d, "description": c.narrative,
            "actual_is_fraud": c.is_fraud, "actual_incurred_cost": round(c.extra["true_cost"], 2),
        })
    with open(os.path.join(OUT, "batch", "holdout_claims.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(batch[0]))
        w.writeheader()
        w.writerows(batch)

    json.dump(index, open(os.path.join(OUT, "samples.json"), "w"), indent=1)
    with open(os.path.join(OUT, "README.md"), "w") as f:
        f.write("# Sample documents\n\nAll data is fictitious. Each scenario exists as a PDF FNOL form "
                "(`fnol/`) and as a JSON API payload (`claims/`).\n\n"
                "| ID | Scenario | Line | Expected routing | PDF |\n|---|---|---|---|---|\n")
        for r in rows:
            f.write(f"| {r[0]} | {r[1]} | {r[2]} | `{r[3]}` | `{r[4]}` |\n")
        f.write("\n`SCAN_*.pdf` are image-only \"fax\" copies of A03 and H01, to show Textract OCR.\n\n"
                "`batch/holdout_claims.csv` has 200 random claims the models never saw, with the true "
                "fraud label and incurred cost for comparison.\n")
    print(f"wrote {len(SCENARIOS)} scenarios (+2 scans, +200 batch claims) to {OUT}")


if __name__ == "__main__":
    main()
