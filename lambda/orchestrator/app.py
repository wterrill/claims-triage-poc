"""Claims Triage orchestrator (AWS Lambda behind API Gateway).

Routes
  GET  /health                     endpoint status (+ ?warm=1 to wake serverless endpoints)
  POST /triage                     one claim (JSON) or {"claims":[...]} (max 50)
  POST /documents                  {"filename": "x.pdf"} -> pre-signed S3 upload URL
  POST /documents/{id}/triage      run Textract on the uploaded FNOL, then triage it
  GET  /claims                     recent triage results
  GET  /claims/{triage_id}         one triage result

Flow per claim
  1. Notes model reads the narrative   -> loss category + injury/litigation/total-loss flags
  2. Flags back-fill anything the structured FNOL didn't say
  3. Fraud + severity models run in parallel on the enriched record
  4. Business rules combine all three into a routing decision with plain-English reasons
"""
import json
import logging
import os
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from decimal import Decimal

from claim_mapper import parse_fnol_lines, to_model_record

log = logging.getLogger()
log.setLevel(logging.INFO)

ENDPOINTS = {
    "fraud": os.environ.get("FRAUD_ENDPOINT", "claims-fraud"),
    "severity": os.environ.get("SEVERITY_ENDPOINT", "claims-severity"),
    "notes": os.environ.get("NOTES_ENDPOINT", "claims-notes"),
}
TABLE = os.environ.get("TABLE_NAME", "")
DOC_BUCKET = os.environ.get("DOC_BUCKET", "")
RULES = {
    "fraud_high": float(os.environ.get("FRAUD_HIGH", "0.55")),
    "fraud_medium": float(os.environ.get("FRAUD_MEDIUM", "0.25")),
    "complex_cost": float(os.environ.get("COMPLEX_COST", "40000")),
    "complex_range_high": float(os.environ.get("COMPLEX_RANGE_HIGH", "100000")),
    "fast_track_cost": float(os.environ.get("FAST_TRACK_COST", "5000")),
    "flag_threshold": float(os.environ.get("FLAG_THRESHOLD", "0.5")),       # back-fill a blank form field
    "flag_override": float(os.environ.get("FLAG_OVERRIDE", "0.8")),         # overrule an explicit "No"
}
ROUTES = {
    "SIU_REFERRAL": ("Refer to Special Investigations Unit", "high"),
    "COMPLEX_SENIOR_ADJUSTER": ("Assign to senior / complex-claims adjuster", "high"),
    "STANDARD_ADJUSTER": ("Assign to standard adjuster queue", "normal"),
    "FAST_TRACK": ("Fast-track: straight-through handling", "low"),
}
CORS = {
    "Access-Control-Allow-Origin": os.environ.get("ALLOWED_ORIGIN", "*"),
    "Access-Control-Allow-Headers": "Content-Type,x-api-key",
    "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
}

# AWS clients are created lazily so tests can inject fakes: app.CLIENTS["sagemaker-runtime"] = Fake()
CLIENTS = {}


def client(name):
    if name not in CLIENTS:
        import boto3
        from botocore.config import Config
        cfg = Config(retries={"max_attempts": 2, "mode": "standard"}, read_timeout=25, connect_timeout=5)
        kw = {}
        if name == "s3":
            # Pre-signed URLs must use the regional endpoint + SigV4: the global
            # bucket.s3.amazonaws.com host answers 307 for new buckets outside us-east-1,
            # which breaks browser/CLI uploads.
            region = os.environ.get("AWS_REGION", "us-east-1")
            cfg = cfg.merge(Config(signature_version="s3v4", s3={"addressing_style": "virtual"}))
            kw["endpoint_url"] = f"https://s3.{region}.amazonaws.com"
        CLIENTS[name] = boto3.client(name, config=cfg, **kw)
    return CLIENTS[name]


# --------------------------------------------------------------------------- model calls
def invoke(model, instances):
    t0 = time.time()
    body = json.dumps({"instances": instances})
    last = None
    for attempt in range(3):  # serverless endpoints can be cold; give them a couple of tries
        try:
            r = client("sagemaker-runtime").invoke_endpoint(
                EndpointName=ENDPOINTS[model], ContentType="application/json",
                Accept="application/json", Body=body)
            raw = r["Body"].read()
            preds = json.loads(raw)["predictions"]
            return preds, int((time.time() - t0) * 1000)
        except Exception as e:  # noqa: BLE001
            last = e
            log.warning("invoke %s attempt %d failed: %s", model, attempt + 1, e)
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"{model} endpoint unavailable ({type(last).__name__}). "
                       f"If this is the first call in a while the endpoint may be warming up - retry in ~30s.")


def triage_many(claims, source="api"):
    texts = [{"text": c.get("description") or ""} for c in claims]
    records = [to_model_record(c) for c in claims]

    notes, t_notes = invoke("notes", texts)
    for rec, n, c in zip(records, notes, claims):
        # Back-fill: if the form didn't say, trust what the narrative says
        for flag, field in (("injury", "injury_reported"), ("litigation", "attorney_involved"),
                            ("total_loss", "total_loss_indicated")):
            if rec.get(field) is None:
                rec[field] = int(n["flags"][flag] >= RULES["flag_threshold"])
        if not rec.get("loss_type"):
            rec["loss_type"] = n["loss_category"]

    with ThreadPoolExecutor(2) as ex:
        f_fut = ex.submit(invoke, "fraud", records)
        s_fut = ex.submit(invoke, "severity", records)
        (fraud, t_fraud), (sev, t_sev) = f_fut.result(), s_fut.result()

    now = datetime.now(timezone.utc).isoformat()
    out = []
    for c, rec, n, f, s in zip(claims, records, notes, fraud, sev):
        route, reasons, actions = decide_route(c, rec, f, s, n)
        label, priority = ROUTES[route]
        out.append({
            "triage_id": str(uuid.uuid4()),
            "claim_number": c.get("claim_number"),
            "insured_name": c.get("insured_name"),
            "line_of_business": rec.get("line_of_business"),
            "created_at": now,
            "source": source,
            "route": route, "route_label": label, "priority": priority,
            "reasons": reasons, "next_actions": actions,
            "models": {"fraud": f, "severity": s, "notes": n},
            "model_latency_ms": {"notes": t_notes, "fraud": t_fraud, "severity": t_sev},
            "features_used": rec,
        })
    return out


BINARY = {"is_weekend", "police_report_filed", "witness_present", "injury_reported", "attorney_involved",
          "total_loss_indicated", "coverage_increase_last_90d"}


def fmt_value(field, v):
    if v is None:
        return "-"
    if field in BINARY:
        return "Yes" if float(v) >= 0.5 else "No"
    if field in ("claim_amount_reported", "annual_premium", "deductible"):
        return f"${float(v):,.0f}"
    if field in ("days_to_report", "days_policy_to_loss"):
        return f"{float(v):,.0f} days"
    if field == "policy_tenure_months":
        return f"{float(v):,.0f} month" + ("" if round(float(v)) == 1 else "s")
    if field == "incident_hour":
        return f"{int(float(v)):02d}:00"
    if field == "asset_age_years":
        return f"{float(v):,.0f} yrs"
    return f"{float(v):,.0f}"


def explain(factors):
    for x in factors:
        x["display"] = f"{x['factor']}: {fmt_value(x['field'], x['value'])} (typical {fmt_value(x['field'], x['typical'])})"
    return factors


def decide_route(claim, rec, f, s, n):
    """Transparent, editable business rules on top of the model outputs."""
    reasons, actions = [], []
    score, cost = f["fraud_score"], s["predicted_cost"]
    explain(f["top_factors"])
    flags = n["flags"]
    litig = rec.get("attorney_involved") == 1 or flags["litigation"] >= RULES["flag_override"]
    injury = rec.get("injury_reported") == 1 or flags["injury"] >= RULES["flag_override"]
    total = rec.get("total_loss_indicated") == 1 or flags["total_loss"] >= RULES["flag_override"]
    if litig and rec.get("attorney_involved") == 0:
        reasons.append("Narrative mentions attorney/representation although the form says no attorney")

    stated = (claim.get("loss_type") or "").strip().lower()
    mismatch = (stated and rec.get("loss_type") and n["loss_category"] != rec["loss_type"]
                and n["category_confidence"] >= 0.6)
    if mismatch:
        reasons.append(f"Narrative reads like '{n['loss_category'].replace('_', ' ')}' but loss was "
                       f"reported as '{rec['loss_type'].replace('_', ' ')}'")

    if score >= RULES["fraud_high"]:
        route = "SIU_REFERRAL"
        reasons.insert(0, f"Fraud score {score:.0%} is above the SIU threshold ({RULES['fraud_high']:.0%})")
        reasons += [x["display"] for x in f["top_factors"]]
        actions += ["Hold payment pending SIU review", "Request recorded statement",
                    "Verify ownership / proof of loss documents"]
    elif litig or cost >= RULES["complex_cost"] or s["range_high"] >= RULES["complex_range_high"]:
        route = "COMPLEX_SENIOR_ADJUSTER"
        if litig:
            reasons.append("Attorney representation / litigation risk")
            actions.append("Notify claims counsel; acknowledge letter of representation")
        if cost >= RULES["complex_cost"] or s["range_high"] >= RULES["complex_range_high"]:
            reasons.append(f"Predicted severity ${cost:,.0f} (range ${s['range_low']:,.0f}-${s['range_high']:,.0f})")
        if injury:
            reasons.append("Bodily injury involved")
            actions.append("Obtain medical authorizations")
        if total:
            reasons.append("Likely total loss")
            actions.append("Order total-loss valuation; review additional living expense / rental needs")
        actions.append(f"Set initial reserve at ${s['suggested_reserve']:,.0f}")
    elif (score < RULES["fraud_medium"] and cost < RULES["fast_track_cost"]
          and s["range_high"] < 2 * RULES["fast_track_cost"] and not injury and not total and not mismatch):
        route = "FAST_TRACK"
        reasons.append(f"Low fraud risk ({score:.0%}) and low predicted severity (${cost:,.0f})")
        actions += ["Auto-assign to desk adjuster for photo-based estimate",
                    f"Set reserve at ${s['suggested_reserve']:,.0f}"]
    else:
        route = "STANDARD_ADJUSTER"
        reasons.append(f"Predicted severity ${cost:,.0f}; fraud risk {score:.0%}")
        if injury:
            reasons.append("Injury reported")
        if total:
            reasons.append("Possible total loss")
            actions.append("Order total-loss valuation")
        if score >= RULES["fraud_medium"]:
            reasons.append("Moderate fraud indicators - adjuster should review before payment")
            reasons += [x["display"] for x in f["top_factors"][:2]]
        actions.append(f"Set initial reserve at ${s['suggested_reserve']:,.0f}")
    if mismatch and route in ("STANDARD_ADJUSTER", "FAST_TRACK"):
        actions.append("Confirm cause of loss with insured")
    return route, reasons, actions


# --------------------------------------------------------------------------- documents
def create_upload(body):
    name = os.path.basename(body.get("filename") or "fnol.pdf")
    if not name.lower().endswith((".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".tif")):
        return 400, {"error": "Upload a PDF, PNG, JPG or TIFF FNOL form"}
    doc_id = str(uuid.uuid4())
    key = f"uploads/{doc_id}/{name}"
    ctype = body.get("content_type") or "application/pdf"
    url = client("s3").generate_presigned_url(
        "put_object", Params={"Bucket": DOC_BUCKET, "Key": key, "ContentType": ctype}, ExpiresIn=900)
    return 200, {"document_id": doc_id, "upload_url": url, "s3_key": key, "content_type": ctype,
                 "next": f"PUT the file to upload_url, then POST /documents/{doc_id}/triage"}


def triage_document(doc_id):
    objs = client("s3").list_objects_v2(Bucket=DOC_BUCKET, Prefix=f"uploads/{doc_id}/").get("Contents", [])
    if not objs:
        return 404, {"error": "Document not found - did the upload succeed?"}
    key = objs[0]["Key"]
    t0 = time.time()
    tx = client("textract").detect_document_text(Document={"S3Object": {"Bucket": DOC_BUCKET, "Name": key}})
    lines = [b["Text"] for b in tx["Blocks"] if b["BlockType"] == "LINE"]
    conf = [b["Confidence"] for b in tx["Blocks"] if b["BlockType"] == "LINE"]
    claim = parse_fnol_lines(lines)
    if not claim.get("description") and not claim.get("claim_number"):
        return 422, {"error": "Could not find FNOL fields in this document", "lines_found": len(lines)}
    result = triage_many([claim], source="document")[0]
    result["extraction"] = {
        "s3_key": key, "lines": len(lines), "fields_found": sorted(k for k in claim if k != "description"),
        "avg_confidence": round(sum(conf) / len(conf), 1) if conf else None,
        "textract_ms": int((time.time() - t0) * 1000), "parsed_claim": claim,
    }
    return 200, result


# --------------------------------------------------------------------------- persistence
def _ddb_safe(o):
    return json.loads(json.dumps(o), parse_float=Decimal)


def save(results):
    if not TABLE:
        return
    tbl = client("dynamodb-resource")
    with tbl.batch_writer() as bw:
        for r in results:
            bw.put_item(Item=_ddb_safe({
                "triage_id": r["triage_id"], "created_at": r["created_at"], "pk": "TRIAGE",
                "claim_number": r.get("claim_number") or "", "route": r["route"],
                "fraud_score": r["models"]["fraud"]["fraud_score"],
                "predicted_cost": r["models"]["severity"]["predicted_cost"],
                "insured_name": r.get("insured_name") or "", "source": r["source"],
                "result": json.dumps(r),
            }))


def _table():
    import boto3
    return boto3.resource("dynamodb").Table(TABLE)


def list_claims(limit):
    resp = client("dynamodb-resource").query(
        IndexName="by-created", KeyConditionExpression="pk = :p", ExpressionAttributeValues={":p": "TRIAGE"},
        ScanIndexForward=False, Limit=limit)
    items = [{k: (float(v) if isinstance(v, Decimal) else v) for k, v in i.items() if k != "result"}
             for i in resp.get("Items", [])]
    return 200, {"claims": items}


def get_claim(tid):
    item = client("dynamodb-resource").get_item(Key={"triage_id": tid}).get("Item")
    return (200, json.loads(item["result"])) if item else (404, {"error": "not found"})


def health(warm):
    status = {}
    sm = client("sagemaker")
    for k, name in ENDPOINTS.items():
        try:
            status[k] = sm.describe_endpoint(EndpointName=name)["EndpointStatus"]
        except Exception as e:  # noqa: BLE001
            status[k] = f"error: {type(e).__name__}"
    if warm:
        sample = {"line_of_business": "auto", "loss_type": "collision"}
        with ThreadPoolExecutor(3) as ex:
            futs = {k: ex.submit(invoke, k, [{"text": "warmup"}] if k == "notes" else [sample]) for k in ENDPOINTS}
            for k, fu in futs.items():
                try:
                    status[k + "_latency_ms"] = fu.result()[1]
                except Exception as e:  # noqa: BLE001
                    status[k + "_latency_ms"] = f"warming ({e})"
    return 200, {"status": "ok", "endpoints": status, "rules": RULES}


# --------------------------------------------------------------------------- handler
def resp(code, body):
    return {"statusCode": code, "headers": {"Content-Type": "application/json", **CORS},
            "body": json.dumps(body, default=str)}


def handler(event, context=None):
    if event.get("source") == "aws.events" or event.get("warmup"):
        # Scheduled keep-warm ping so the first demo click isn't a serverless cold start
        return health(True)[1]
    method = event.get("httpMethod", "GET")
    path = event.get("resource") or event.get("path", "/")
    params = event.get("pathParameters") or {}
    qs = event.get("queryStringParameters") or {}
    try:
        body = json.loads(event.get("body") or "{}") if method == "POST" else {}
    except json.JSONDecodeError:
        return resp(400, {"error": "Body must be JSON"})

    if "dynamodb-resource" not in CLIENTS and TABLE:
        CLIENTS["dynamodb-resource"] = _table()
    try:
        if method == "OPTIONS":
            return resp(200, {})
        if path == "/health":
            return resp(*health(qs.get("warm") in ("1", "true")))
        if path == "/triage" and method == "POST":
            claims = body.get("claims") if isinstance(body.get("claims"), list) else [body]
            if not claims or len(claims) > 50:
                return resp(400, {"error": "Send one claim object or {\"claims\": [...]} with 1-50 claims"})
            results = triage_many(claims)
            save(results)
            return resp(200, results[0] if "claims" not in body else {"results": results})
        if path == "/documents" and method == "POST":
            return resp(*create_upload(body))
        if path == "/documents/{document_id}/triage" and method == "POST":
            code, result = triage_document(params.get("document_id"))
            if code == 200:
                save([result])
            return resp(code, result)
        if path == "/claims" and method == "GET":
            return resp(*list_claims(min(int(qs.get("limit", 25)), 100)))
        if path == "/claims/{triage_id}" and method == "GET":
            return resp(*get_claim(params.get("triage_id")))
        return resp(404, {"error": f"No route for {method} {path}"})
    except RuntimeError as e:
        return resp(503, {"error": str(e)})
    except Exception as e:  # noqa: BLE001
        log.exception("unhandled")
        return resp(500, {"error": f"{type(e).__name__}: {e}"})
