"""Benchmarks cold vs warm latency across this week's deployed targets.

Cloud Run doesn't expose a "force a cold start" button, and waiting out the real
scale-to-zero idle timeout (~15 min per instance) would make this benchmark take
hours for a handful of samples. The standard workaround, used here: force a fresh
*revision* by touching a harmless env var before each cold sample. A new revision
means new container instances -- the very first request that lands on it is
guaranteed cold, exactly as if the previous instance had been scaled to zero and a
brand new one started. Every request after that first one hits an already-warm
instance, which is the warm sample.

Usage:
    uv run python benchmarks/benchmark.py --target function --service northwind-rag-fn \\
        --url https://northwind-rag-fn-xxx.run.app --rounds 8
"""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from dataclasses import asdict, dataclass

import requests

QUESTION = {"question": "What is the rate limit on the Pro tier?"}


@dataclass
class Sample:
    target: str
    kind: str  # "cold" or "warm"
    latency_ms: float


def _force_new_revision(service: str, region: str, project: str) -> None:
    subprocess.run(
        [
            "gcloud", "run", "services", "update", service,
            "--region", region, "--project", project,
            "--update-env-vars", f"BENCH_RUN={int(time.time())}",
            "--quiet",
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _timed_post(url: str, timeout: float) -> float:
    start = time.perf_counter()
    response = requests.post(url, json=QUESTION, timeout=timeout)
    elapsed_ms = (time.perf_counter() - start) * 1000
    response.raise_for_status()
    return elapsed_ms


def run_benchmark(
    target: str,
    url: str,
    service: str | None,
    region: str,
    project: str,
    rounds: int,
    warm_requests_per_round: int,
    force_cold: bool,
) -> list[Sample]:
    samples: list[Sample] = []
    endpoint = url.rstrip("/") + "/chat" if not url.rstrip("/").endswith("/chat") else url

    for round_num in range(rounds):
        if force_cold:
            assert service, "--service is required when forcing cold starts"
            _force_new_revision(service, region, project)
            # Poll /health-equivalent GET until the new revision is routable at all
            # (this call itself may retry through LB/DNS propagation, not the app).
            for _ in range(30):
                try:
                    requests.get(url, timeout=5)
                    break
                except requests.RequestException:
                    time.sleep(2)

        cold_ms = _timed_post(endpoint, timeout=60)
        samples.append(Sample(target=target, kind="cold", latency_ms=cold_ms))
        print(f"[{target}] round {round_num + 1}/{rounds} cold: {cold_ms:.0f}ms")

        for i in range(warm_requests_per_round):
            warm_ms = _timed_post(endpoint, timeout=30)
            samples.append(Sample(target=target, kind="warm", latency_ms=warm_ms))
            print(f"[{target}] round {round_num + 1}/{rounds} warm[{i}]: {warm_ms:.0f}ms")

    return samples


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return float("nan")
    ordered = sorted(values)
    idx = min(int(len(ordered) * pct), len(ordered) - 1)
    return ordered[idx]


def summarize(samples: list[Sample]) -> dict:
    by_kind: dict[str, list[float]] = {"cold": [], "warm": []}
    for s in samples:
        by_kind[s.kind].append(s.latency_ms)
    return {
        kind: {
            "n": len(values),
            "p50": round(percentile(values, 0.50), 1),
            "p95": round(percentile(values, 0.95), 1),
            "p99": round(percentile(values, 0.99), 1),
        }
        for kind, values in by_kind.items()
        if values
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", required=True, help="Label for this run, e.g. 'function-min0'")
    parser.add_argument("--url", required=True, help="Base URL of the deployed endpoint")
    parser.add_argument("--service", help="Cloud Run service name, required if --force-cold")
    parser.add_argument("--region", default="us-central1")
    parser.add_argument("--project", required=True)
    parser.add_argument("--rounds", type=int, default=8)
    parser.add_argument("--warm-requests-per-round", type=int, default=5)
    parser.add_argument("--force-cold", action="store_true", default=True)
    parser.add_argument("--no-force-cold", dest="force_cold", action="store_false")
    parser.add_argument("--out", default="benchmarks/results.jsonl")
    args = parser.parse_args()

    samples = run_benchmark(
        target=args.target,
        url=args.url,
        service=args.service,
        region=args.region,
        project=args.project,
        rounds=args.rounds,
        warm_requests_per_round=args.warm_requests_per_round,
        force_cold=args.force_cold,
    )

    with open(args.out, "a") as f:
        for s in samples:
            f.write(json.dumps(asdict(s)) + "\n")

    print(f"\n=== {args.target} summary ===")
    print(json.dumps(summarize(samples), indent=2))


if __name__ == "__main__":
    main()
