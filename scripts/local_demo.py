"""Run the full POC (web console + API + all three models) on a laptop, with no AWS account.

  python scripts/local_demo.py            ->  http://localhost:8080   (API key: anything)

SageMaker is replaced by the same model code running in-process, Textract by a local PDF
text extractor (so image-only "SCAN_" faxes need the real AWS deployment), S3/DynamoDB by
in-memory fakes. Requires: models trained into build/model/* (see README).
"""
import json
import os
import sys
import tempfile
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))
import local_harness as h  # noqa: E402

UPLOADS = tempfile.mkdtemp(prefix="claims-uploads-")
ROUTES = [("/documents/", "/triage", "/documents/{document_id}/triage", "document_id"),
          ("/claims/", "", "/claims/{triage_id}", "triage_id")]


class FakeSageMaker:
    def describe_endpoint(self, EndpointName):
        return {"EndpointStatus": "InService"}


class Handler(SimpleHTTPRequestHandler):
    def translate_path(self, path):
        p = urlparse(path).path.lstrip("/") or "index.html"
        for base in ("web", "sample_docs"):
            full = os.path.join(ROOT, base, p)
            if os.path.exists(full):
                return full
        return os.path.join(ROOT, "web", p)

    def log_message(self, fmt, *a):
        sys.stderr.write("  " + fmt % a + "\n")

    def _send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/config.json":
            return self._send(200, {"apiUrl": "/api"})
        if u.path.startswith("/api/"):
            return self._api("GET", u)
        return super().do_GET()

    def do_POST(self):
        return self._api("POST", urlparse(self.path))

    def do_PUT(self):
        key = urlparse(self.path).path[len("/upload/"):]
        data = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        dest = os.path.join(UPLOADS, key.replace("/", "_"))
        open(dest, "wb").write(data)
        h.FakeS3.store[key] = dest
        self._send(200, b"", "text/plain")

    def _api(self, method, u):
        path = u.path[len("/api"):]
        resource, params = path, {}
        for prefix, suffix, res, name in ROUTES:
            if path.startswith(prefix) and path.endswith(suffix) and len(path) > len(prefix) + len(suffix):
                resource, params = res, {name: path[len(prefix): len(path) - len(suffix) or None]}
        body = self.rfile.read(int(self.headers.get("Content-Length", 0) or 0)).decode() if method == "POST" else None
        qs = {k: v[0] for k, v in parse_qs(u.query).items()}
        r = h.app.handler({"httpMethod": method, "resource": resource, "pathParameters": params,
                           "queryStringParameters": qs, "body": body})
        self._send(r["statusCode"], r["body"].encode())


def main():
    h.setup()
    h.FakeS3.generate_presigned_url = lambda self, op, Params, ExpiresIn: "/upload/" + Params["Key"]
    h.app.CLIENTS["sagemaker"] = FakeSageMaker()
    port = int(os.environ.get("PORT", "8080"))
    print(f"Claims Triage POC running locally at http://localhost:{port}  (any API key works)")
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()


if __name__ == "__main__":
    main()
