"""Run the Lambda orchestrator end-to-end on a laptop, with no AWS account.

SageMaker endpoints are replaced by the real model code (ml/src/*_model.py) loaded from
build/model/*, Textract by a local PDF text extractor, S3/DynamoDB by in-memory fakes.

  python ml/src/fraud_model.py --model-dir build/model/fraud   (etc. - or `make models`)
  python tests/local_harness.py
"""
import glob
import io
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "lambda", "orchestrator"), os.path.join(ROOT, "ml", "src"),
                os.path.join(ROOT, "data")]

import app  # noqa: E402
import fraud_model  # noqa: E402
import notes_model  # noqa: E402
import severity_model  # noqa: E402

MODELS = {
    "claims-fraud": (fraud_model, os.path.join(ROOT, "build/model/fraud")),
    "claims-severity": (severity_model, os.path.join(ROOT, "build/model/severity")),
    "claims-notes": (notes_model, os.path.join(ROOT, "build/model/notes")),
}


class FakeRuntime:
    def __init__(self):
        self.loaded = {k: (m, m.model_fn(d)) for k, (m, d) in MODELS.items()}

    def invoke_endpoint(self, EndpointName, Body, ContentType, **_):
        mod, art = self.loaded[EndpointName]
        out, _ = mod.output_fn(mod.predict_fn(mod.input_fn(Body, ContentType), art))
        return {"Body": io.BytesIO(out.encode())}


class FakeS3:
    store = {}

    def generate_presigned_url(self, op, Params, ExpiresIn):
        return f"https://fake-s3/{Params['Key']}"

    def list_objects_v2(self, Bucket, Prefix):
        return {"Contents": [{"Key": k} for k in self.store if k.startswith(Prefix)]}


class FakeTextract:
    def detect_document_text(self, Document):
        from pypdf import PdfReader
        path = FakeS3.store[Document["S3Object"]["Name"]]
        text = PdfReader(path).pages[0].extract_text() or ""
        return {"Blocks": [{"BlockType": "LINE", "Text": t, "Confidence": 99.0}
                           for t in text.splitlines() if t.strip()]}


class FakeTable:
    items = {}

    def batch_writer(self):
        tbl = self

        class BW:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                pass

            def put_item(self, Item):
                tbl.items[Item["triage_id"]] = Item
        return BW()

    def get_item(self, Key):
        return {"Item": self.items.get(Key["triage_id"])} if Key["triage_id"] in self.items else {}

    def query(self, **kw):
        return {"Items": sorted(self.items.values(), key=lambda i: i["created_at"], reverse=True)[: kw["Limit"]]}


def setup():
    app.CLIENTS.update({"sagemaker-runtime": FakeRuntime(), "s3": FakeS3(), "textract": FakeTextract(),
                        "dynamodb-resource": FakeTable()})
    app.TABLE = "local"
    app.DOC_BUCKET = "local"


def call(method, resource, body=None, path_params=None, qs=None):
    r = app.handler({"httpMethod": method, "resource": resource, "body": json.dumps(body) if body else None,
                     "pathParameters": path_params, "queryStringParameters": qs})
    return r["statusCode"], json.loads(r["body"])


def main():
    setup()
    from scenarios import SCENARIOS
    expected = {s["id"]: (s["expected_route"], s["title"]) for s in SCENARIOS}
    ok = total = 0
    print(f"{'ID':4} {'via':5} {'expected':24} {'actual':24} {'fraud':>6} {'pred $':>9}  category")
    for sid, (exp, title) in expected.items():
        # JSON API path
        code, r = call("POST", "/triage", json.load(open(os.path.join(ROOT, "sample_docs/claims", f"{sid}.json"))))
        assert code == 200, r
        # Document path (upload -> triage)
        pdf = glob.glob(os.path.join(ROOT, "sample_docs/fnol", f"{sid}_*.pdf"))[0]
        code, up = call("POST", "/documents", {"filename": os.path.basename(pdf)})
        FakeS3.store[up["s3_key"]] = pdf
        code, d = call("POST", "/documents/{document_id}/triage", path_params={"document_id": up["document_id"]})
        assert code == 200, d
        for via, res in (("json", r), ("pdf", d)):
            total += 1
            ok += res["route"] == exp
            m = res["models"]
            print(f"{sid:4} {via:5} {exp:24} {res['route']:24} {m['fraud']['fraud_score']:6.2f} "
                  f"{m['severity']['predicted_cost']:9,.0f}  {m['notes']['loss_category']}"
                  f"{'' if res['route'] == exp else '   <-- ' + title}")
    print(f"\nRouting matched expectation on {ok}/{total} runs")

    # batch endpoint on hold-out claims
    import csv
    rows = list(csv.DictReader(open(os.path.join(ROOT, "sample_docs/batch/holdout_claims.csv"))))
    results = []
    for i in range(0, len(rows), 50):  # API accepts up to 50 claims per call
        code, b = call("POST", "/triage", {"claims": rows[i:i + 50]})
        assert code == 200, b
        results += b["results"]
    b = {"results": results}
    routes = {}
    for res in b["results"]:
        routes[res["route"]] = routes.get(res["route"], 0) + 1
    caught = sum(1 for row, res in zip(rows, b["results"]) if row["actual_is_fraud"] == "1" and res["route"] == "SIU_REFERRAL")
    frauds = sum(row["actual_is_fraud"] == "1" for row in rows)
    flagged = sum(res["route"] == "SIU_REFERRAL" for res in results)
    print(f"Batch of {len(rows)} hold-out claims -> {routes}")
    print(f"  SIU referrals: {flagged}, of which true fraud: {caught} "
          f"(precision {caught / max(flagged, 1):.0%}); caught {caught}/{frauds} frauds (recall {caught / max(frauds, 1):.0%})")
    import statistics
    errs = [abs(res["models"]["severity"]["predicted_cost"] - float(row["actual_incurred_cost"])) / float(row["actual_incurred_cost"])
            for row, res in zip(rows, results)]
    print(f"  Severity: median absolute error {statistics.median(errs):.0%} of actual cost")

    code, lst = call("GET", "/claims", qs={"limit": "5"})
    code, one = call("GET", "/claims/{triage_id}", path_params={"triage_id": lst["claims"][0]["triage_id"]})
    print(f"GET /claims returned {len(lst['claims'])}; GET /claims/id -> {one['route']}")
    return ok, total


if __name__ == "__main__":
    main()
