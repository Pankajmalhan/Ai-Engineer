"""Runs ONE traced request with the REAL Langfuse SDK against a local capture server and prints
what hit the wire as JSON. A separate process per scenario because OpenTelemetry's tracer
provider is process-global: it binds to the first exporter URL and cannot be re-pointed, so two
scenarios in one pytest process would send the second one's spans to the first one's (closed)
server. Used by tests/test_tracing_real_sdk.py (identical file in Weeks 9 and 10).

    python tests/real_sdk_scenario.py ok|fail
"""

import gzip
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

here = Path(__file__).resolve().parent
root = here.parent
sys.path.insert(0, str(root if (root / "app").exists() else root / "function"))  # Week 9: app/  Week 10: function/app/

captured = []


class Capture(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        if self.headers.get("Content-Encoding") == "gzip":
            body = gzip.decompress(body)
        captured.append((self.path, body))
        ingestion = "ingestion" in self.path
        self.send_response(207 if ingestion else 200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"successes": [], "errors": []}).encode() if ingestion else b"{}")

    do_GET = do_POST


server = HTTPServer(("127.0.0.1", 0), Capture)
threading.Thread(target=server.serve_forever, daemon=True).start()
os.environ.update(
    LANGFUSE_PUBLIC_KEY="pk-lf-test",
    LANGFUSE_SECRET_KEY="sk-lf-test",
    LANGFUSE_BASE_URL=f"http://127.0.0.1:{server.server_port}",
    LANGFUSE_TRACING_ENVIRONMENT="cloud-run-function",
    DEPLOY_TARGET="cloud-run-function",
)

from app import tracing  # noqa: E402
from app.llm import GenerationResult  # noqa: E402
from app.pipeline import RAGPipeline  # noqa: E402
from app.retrieval import BM25Retriever  # noqa: E402

mode = sys.argv[1]
if mode == "ok":
    tracing.generate_answer = lambda q, c: GenerationResult("30 days.", 40, 5)
else:

    def boom(q, c):
        raise TimeoutError("openai timed out")

    tracing.generate_answer = boom

raised = None
answer = None
try:
    answer = tracing.traced_answer(RAGPipeline(retriever=BM25Retriever()), "What's the refund window for annual plans?").answer
except Exception as exc:
    raised = type(exc).__name__

wire = b"".join(body for _, body in captured)
scores = {}
for path, body in captured:
    if "ingestion" in path:
        for event in json.loads(body).get("batch", []):
            b = event.get("body", {})
            if "name" in b and "value" in b:
                scores[b["name"]] = {k: b.get(k) for k in ("value", "dataType", "environment")}

print(
    json.dumps(
        {
            "answer": answer,
            "raised": raised,
            "paths": sorted({p for p, _ in captured}),
            "scores": scores,
            "wire_contains": {
                n: n.encode() in wire
                for n in ("rag-request", "retrieval", "generation", "cloud-run-function", "deploy_target", "openai timed out")
            },
        }
    )
)
