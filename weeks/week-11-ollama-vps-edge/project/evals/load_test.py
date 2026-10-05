"""Concurrency load test: how does each backend behave when many requests arrive at once?

    uv run python -m evals.load_test --providers openai ollama
    uv run python -m evals.load_test --providers ollama:qwen2.5:14b-instruct --concurrency 1 4 8 16 \\
        --requests-per-level 48 --out load-gpu.json

For each concurrency level C, C worker threads issue requests back to back until
`--requests-per-level` have completed (a closed loop: a worker sends its next request the
moment its previous one returns). Per level it reports:

  p50 / p95 / max   per-request latency, INCLUDING any time spent queued server-side
  req/s             completed requests / wall time  -> throughput
  tok/s             output tokens / wall time       -> aggregate generation throughput
  err               requests that raised (rate limits, timeouts, 5xx)

What to look for: latency staying flat while throughput climbs means there is spare
capacity. Latency climbing in step with C while throughput stops growing means you have hit
the ceiling -- for Ollama that is OLLAMA_NUM_PARALLEL slots (extra requests queue); for
OpenAI it is your account's rate limit. Also watch `err`: with the default --max-retries 0 a
503 from Nginx's limit_req (or a 429 from OpenAI) is counted as an error rather than being
retried into extra latency.
Uses the same RAG pipeline as the quality comparison, so these are end-to-end numbers.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from typing import Callable

from dotenv import load_dotenv

from app.dataset import EXTENDED_GOLDENS
from evals.compare_models import _default_pipeline_factory


def percentile(values: list[float], pct: float) -> float:
    """Linear-interpolated percentile (pct in 0..100); 0.0 for an empty list."""
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = (len(ordered) - 1) * pct / 100.0
    low, high = math.floor(rank), math.ceil(rank)
    return ordered[low] + (ordered[high] - ordered[low]) * (rank - low)


@dataclass
class LevelResult:
    concurrency: int
    wall_s: float = 0.0
    latencies: list[float] = field(default_factory=list)
    output_tokens: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> int:
        return len(self.latencies)

    @property
    def p50(self) -> float:
        return percentile(self.latencies, 50)

    @property
    def p95(self) -> float:
        return percentile(self.latencies, 95)

    @property
    def max_latency(self) -> float:
        return max(self.latencies, default=0.0)

    @property
    def requests_per_second(self) -> float:
        return self.ok / self.wall_s if self.wall_s else 0.0

    @property
    def tokens_per_second(self) -> float:
        return self.output_tokens / self.wall_s if self.wall_s else 0.0


def run_level(
    answer: Callable[[str], object],
    questions: list[str],
    concurrency: int,
    total_requests: int,
) -> LevelResult:
    """`answer(question)` must return an object with `.output_tokens` (a PipelineResult)."""
    result = LevelResult(concurrency=concurrency)

    def one(i: int) -> tuple[float, int, str | None]:
        started = time.perf_counter()
        try:
            out = answer(questions[i % len(questions)])
            return time.perf_counter() - started, getattr(out, "output_tokens", 0), None
        except Exception as exc:  # a failed request is data, not a reason to abort the run
            return time.perf_counter() - started, 0, f"{type(exc).__name__}: {exc}"

    wall_start = time.perf_counter()
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        outcomes = list(pool.map(one, range(total_requests)))
    result.wall_s = time.perf_counter() - wall_start

    for latency, tokens, error in outcomes:
        if error is None:
            result.latencies.append(latency)
            result.output_tokens += tokens
        else:
            result.errors.append(error)
    return result


def format_table(label: str, levels: list[LevelResult]) -> str:
    header = f"{'conc':>5}{'ok':>5}{'err':>5}{'p50 s':>8}{'p95 s':>8}{'max s':>8}{'req/s':>8}{'tok/s':>8}"
    lines = [f"== {label}", header, "-" * len(header)]
    for lv in levels:
        lines.append(
            f"{lv.concurrency:>5}{lv.ok:>5}{len(lv.errors):>5}{lv.p50:>8.2f}{lv.p95:>8.2f}"
            f"{lv.max_latency:>8.2f}{lv.requests_per_second:>8.2f}{lv.tokens_per_second:>8.1f}"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--providers", nargs="+", default=["openai", "ollama"], help="provider or provider:model specs")
    parser.add_argument("--concurrency", nargs="+", type=int, default=[1, 2, 4, 8, 16])
    parser.add_argument("--requests-per-level", type=int, default=48, help="minimum; raised to 2x the concurrency if smaller")
    parser.add_argument("--warmup", type=int, default=3, help="untimed requests first (loads the model, opens connections)")
    parser.add_argument(
        "--max-retries",
        type=int,
        default=0,
        help="SDK retries per request. 0 (default) makes rate limits / 503s show up as errors instead of "
        "silently turning into latency; use 2 to mimic a production client",
    )
    parser.add_argument("--out", help="write per-level results as JSON")
    args = parser.parse_args(argv)
    os.environ["LLM_MAX_RETRIES"] = str(args.max_retries)

    questions = [g.question for g in EXTENDED_GOLDENS]
    report: dict[str, list[dict]] = {}
    for spec in args.providers:
        pipeline = _default_pipeline_factory(spec)
        label = f"{pipeline.llm_config.provider}:{pipeline.llm_config.model}"
        for i in range(args.warmup):
            pipeline.answer(questions[i % len(questions)])

        levels = []
        for c in args.concurrency:
            levels.append(run_level(pipeline.answer, questions, c, max(args.requests_per_level, c * 2)))
        print(format_table(label, levels))
        for lv in levels:
            if lv.errors:
                print(f"   conc={lv.concurrency}: {len(lv.errors)} errors, e.g. {lv.errors[0][:140]}")
        print()
        report[label] = [asdict(lv) | {"p50": lv.p50, "p95": lv.p95, "rps": lv.requests_per_second, "tps": lv.tokens_per_second} for lv in levels]

    if args.out:
        with open(args.out, "w") as f:
            json.dump(report, f, indent=2)
        print(f"per-level results -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
