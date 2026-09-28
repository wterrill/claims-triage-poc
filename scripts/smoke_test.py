"""End-to-end test against the DEPLOYED API (standard library only - no pip installs needed).

  python scripts/smoke_test.py                       # reads build/outputs.json + fetches the key
  python scripts/smoke_test.py --api-url https://.../v1/ --api-key XXXX

Runs every sample scenario through both the JSON API and the PDF/Textract path (including
the two image-only fax scans), a 50-claim batch, and the history endpoints.
"""
import argparse
import csv
import glob
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "data"))
from scenarios import SCENARIOS  # noqa: E402


class Api:
    def __init__(self, url, key):
        self.url, self.key = url.rstrip("/"), key

    def call(self, method, path, body=None):
        req = urllib.request.Request(self.url + path, method=method,
                                     data=json.dumps(body).encode() if body is not None else None,
                                     headers={"x-api-key": self.key, "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")

    def upload_and_triage(self, path):
        code, up = self.call("POST", "/documents", {"filename": os.path.basename(path),
                                                   "content_type": "application/pdf"})
        assert code == 200, up
        req = urllib.request.Request(up["upload_url"], method="PUT", data=open(path, "rb").read(),
                                     headers={"Content-Type": up["content_type"]})
        urllib.request.urlopen(req, timeout=60).read()
        return self.call("POST", f"/documents/{up['document_id']}/triage")


def from_outputs():
    out = json.load(open(os.path.join(ROOT, "build", "outputs.json")))["ClaimsTriageApp"]
    key = subprocess.check_output(out["GetApiKeyCommand"].split(), text=True).strip()
    return out["ApiUrl"], key


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--api-url")
    ap.add_argument("--api-key")
    a = ap.parse_args()
    url, key = (a.api_url, a.api_key) if a.api_url else from_outputs()
    api = Api(url, key)

    print("Waking the three serverless endpoints (first call after idle can take ~30-60s)...")
    for i in range(12):
        code, h = api.call("GET", "/health?warm=1")
        lat = {k: v for k, v in h.get("endpoints", {}).items() if k.endswith("latency_ms")}
        if code == 200 and lat and all(isinstance(v, int) for v in lat.values()):
            print("  ready:", lat)
            break
        time.sleep(10)

    ok = total = 0
    print(f"\n{'ID':9} {'via':5} {'expected':24} {'actual':24} {'fraud':>6} {'pred $':>9}")
    for s in SCENARIOS:
        runs = [("json", lambda s=s: api.call("POST", "/triage", json.load(open(os.path.join(ROOT, "sample_docs/claims", s["id"] + ".json")))))]
        for pdf in sorted(glob.glob(os.path.join(ROOT, "sample_docs/fnol", f"*{s['id']}_*.pdf"))):
            runs.append(("scan" if "SCAN_" in pdf else "pdf", lambda pdf=pdf: api.upload_and_triage(pdf)))
        for via, fn in runs:
            code, r = fn()
            total += 1
            if code != 200:
                print(f"{s['id']:9} {via:5} ERROR {code}: {r}")
                continue
            ok += r["route"] == s["expected_route"]
            print(f"{s['id']:9} {via:5} {s['expected_route']:24} {r['route']:24} "
                  f"{r['models']['fraud']['fraud_score']:6.2f} {r['models']['severity']['predicted_cost']:9,.0f}"
                  + ("" if r["route"] == s["expected_route"] else "   <-- differs"))
    print(f"\nRouting matched expectation on {ok}/{total} runs")

    rows = list(csv.DictReader(open(os.path.join(ROOT, "sample_docs/batch/holdout_claims.csv"))))[:50]
    t0 = time.time()
    code, b = api.call("POST", "/triage", {"claims": rows})
    if code == 200:
        routes = {}
        for r in b["results"]:
            routes[r["route"]] = routes.get(r["route"], 0) + 1
        print(f"Batch of {len(rows)} claims in {time.time() - t0:.1f}s -> {routes}")
    else:
        print("Batch failed:", code, b)
    code, lst = api.call("GET", "/claims?limit=5")
    print(f"History: GET /claims -> {code}, {len(lst.get('claims', []))} items")
    sys.exit(0 if ok == total else 1)


if __name__ == "__main__":
    main()
