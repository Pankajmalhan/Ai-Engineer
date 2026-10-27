"""Proves every deployment target really sends traces to Langfuse -- the roadmap's
"every deployment target sends traces" goal, checked rather than assumed.

For each target it sends N real requests, then polls Langfuse until the traces for that
target's environment show up (ingestion is asynchronous: seconds, not milliseconds) and
reports how many arrived, with their `request_error` scores.

    uv run python scripts/verify_traces.py \\
        --target cloud-run-service=https://<LB-IP>/chat \\
        --target cloud-run-function=https://<gateway-host>/chat \\
        --requests 5

`name` must equal the DEPLOY_TARGET / LANGFUSE_TRACING_ENVIRONMENT the deployment sets
(`cloud-run-service`, `cloud-run-function`, or `local`). Needs LANGFUSE_PUBLIC_KEY /
LANGFUSE_SECRET_KEY / LANGFUSE_BASE_URL for the SAME Langfuse project the deployments write to.
Exit status is non-zero if any target is missing traces.
"""

from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone

QUESTIONS = [
    "What's the refund window for annual plans?",
    "What's the API rate limit on the Pro tier?",
    "How long does my old API key keep working after I rotate it?",
    "How long are request logs kept before deletion?",
    "What uptime percentage does the Pro tier SLA guarantee?",
]


@dataclass
class TargetResult:
    name: str
    url: str
    sent: int
    http_ok: int
    traces: int
    scores: int

    @property
    def passed(self) -> bool:
        return self.http_ok == self.sent and self.traces >= self.http_ok > 0


def parse_target(spec: str) -> tuple[str, str]:
    name, sep, url = spec.partition("=")
    if not sep or not name or not url.startswith(("http://", "https://")):
        raise argparse.ArgumentTypeError(f"--target must look like name=https://host/path, got {spec!r}")
    return name, url


def send_requests(post, url: str, count: int) -> int:
    """`post(url, json)` -> object with .status_code. Returns how many came back 2xx."""
    ok = 0
    for i in range(count):
        try:
            response = post(url, json={"question": QUESTIONS[i % len(QUESTIONS)]})
            ok += 200 <= response.status_code < 300
        except Exception as exc:  # network error: counted as a failed request
            print(f"   request to {url} failed: {type(exc).__name__}: {exc}", file=sys.stderr)
    return ok


def count_arrivals(client, name: str, since: datetime, *, expected: int, timeout_s: float, poll_s: float, sleep=time.sleep, clock=time.monotonic) -> tuple[int, int]:
    """Polls Langfuse for traces and `request_error` scores of environment `name` since `since`
    until `expected` traces are seen or the timeout passes. Returns (traces, scores)."""
    deadline = clock() + timeout_s
    traces = scores = 0
    while True:
        traces = client.api.trace.list(environment=name, from_timestamp=since, limit=100).meta.total_items
        scores = client.api.scores.get_many(
            name="request_error", environment=name, from_timestamp=since, limit=1
        ).meta.total_items
        if traces >= expected and scores >= expected:
            break
        if clock() >= deadline:
            break
        sleep(poll_s)
    return traces, scores


def verify_target(client, post, name: str, url: str, requests_per_target: int, *, timeout_s: float = 90, poll_s: float = 5, **kw) -> TargetResult:
    since = datetime.now(timezone.utc)
    ok = send_requests(post, url, requests_per_target)
    traces, scores = count_arrivals(client, name, since, expected=ok, timeout_s=timeout_s, poll_s=poll_s, **kw)
    return TargetResult(name=name, url=url, sent=requests_per_target, http_ok=ok, traces=traces, scores=scores)


def format_results(results: list[TargetResult]) -> str:
    header = f"{'target':<22}{'sent':>5}{'2xx':>5}{'traces':>8}{'scores':>8}  result"
    rows = [header, "-" * len(header)]
    for r in results:
        rows.append(f"{r.name:<22}{r.sent:>5}{r.http_ok:>5}{r.traces:>8}{r.scores:>8}  {'PASS' if r.passed else 'FAIL'}")
    return "\n".join(rows)


def main(argv: list[str] | None = None) -> int:
    import httpx
    from dotenv import load_dotenv
    from langfuse import Langfuse

    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--target", action="append", type=parse_target, required=True, help="name=url, repeatable")
    parser.add_argument("--requests", type=int, default=5, help="requests per target")
    parser.add_argument("--timeout", type=float, default=90, help="seconds to wait for traces to arrive")
    args = parser.parse_args(argv)

    client = Langfuse()
    with httpx.Client(timeout=60) as http:
        results = [verify_target(client, http.post, name, url, args.requests, timeout_s=args.timeout) for name, url in args.target]
    print(format_results(results))
    for r in results:
        if not r.passed:
            print(f"\n{r.name}: no/missing traces. Check: LANGFUSE_* secrets reach the deployment, "
                  f"LANGFUSE_BASE_URL is reachable from it, DEPLOY_TARGET/LANGFUSE_TRACING_ENVIRONMENT=={r.name}, "
                  "and the keys belong to this Langfuse project.", file=sys.stderr)
    return 0 if all(r.passed for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
