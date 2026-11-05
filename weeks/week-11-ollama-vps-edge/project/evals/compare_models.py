"""Runs the golden set through the pipeline once per provider and prints a side-by-side
table: retrieval hit rate (same for both -- retrieval is BM25, not the LLM), RAGAS
faithfulness (judged by OpenAI for both), latency, and tokens/sec.

    uv run python -m evals.compare_models --providers openai ollama --out results.json
    uv run python -m evals.compare_models --providers ollama --skip-faithfulness   # no judge cost

    # several models on the same server in one run: provider[:model] (the model may itself
    # contain colons, e.g. ollama:qwen2.5:14b-instruct). Pull them first: scripts/pull_model.sh
    uv run python -m evals.compare_models --questions extended \
        --providers openai ollama:llama3.2:3b ollama:qwen2.5:7b-instruct ollama:qwen2.5:14b-instruct

Faithfulness costs one OpenAI judge call per golden per provider. Latency is wall-clock
per request as this machine sees it -- for Ollama that includes the network hop to the
VPS and Nginx, which is the number a real client would experience.
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
from dataclasses import asdict, dataclass, field
from typing import Callable

from dotenv import load_dotenv

from app.dataset import EXTENDED_GOLDENS, GOLDENS, EvalSample
from app.llm import load_config
from app.pipeline import RAGPipeline, PipelineResult

Scorer = Callable[[str, str, list[str]], float]


@dataclass
class CaseResult:
    question: str
    answer: str
    retrieval_hit: bool
    faithfulness: float | None
    latency_s: float
    output_tokens: int


@dataclass
class ProviderReport:
    provider: str
    model: str
    cases: list[CaseResult] = field(default_factory=list)

    @property
    def retrieval_hit_rate(self) -> float:
        return sum(c.retrieval_hit for c in self.cases) / len(self.cases)

    @property
    def mean_faithfulness(self) -> float | None:
        scores = [c.faithfulness for c in self.cases if c.faithfulness is not None]
        return statistics.mean(scores) if scores else None

    @property
    def p50_latency_s(self) -> float:
        return statistics.median(c.latency_s for c in self.cases)

    @property
    def max_latency_s(self) -> float:
        return max(c.latency_s for c in self.cases)

    @property
    def tokens_per_second(self) -> float:
        total_time = sum(c.latency_s for c in self.cases)
        return sum(c.output_tokens for c in self.cases) / total_time if total_time else 0.0


def run_provider(
    provider: str,
    goldens: list[EvalSample],
    pipeline_factory: Callable[[str], RAGPipeline],
    scorer: Scorer | None,
) -> ProviderReport:
    pipeline = pipeline_factory(provider)
    config = pipeline.llm_config
    report = ProviderReport(provider=config.provider, model=config.model)
    for sample in goldens:
        started = time.perf_counter()
        result: PipelineResult = pipeline.answer(sample.question)
        latency = time.perf_counter() - started
        report.cases.append(
            CaseResult(
                question=sample.question,
                answer=result.answer,
                retrieval_hit=sample.source_doc_id in result.retrieved_doc_ids,
                faithfulness=scorer(sample.question, result.answer, result.retrieved_contexts)
                if scorer
                else None,
                latency_s=latency,
                output_tokens=result.output_tokens,
            )
        )
    return report


def format_table(reports: list[ProviderReport]) -> str:
    def fmt(value, spec):
        return "n/a" if value is None else format(value, spec)

    header = f"{'provider':<10}{'model':<20}{'retr_hit':>9}{'faithful':>10}{'p50 s':>8}{'max s':>8}{'tok/s':>8}"
    lines = [header, "-" * len(header)]
    for r in reports:
        lines.append(
            f"{r.provider:<10}{r.model:<20}{r.retrieval_hit_rate:>9.2f}"
            f"{fmt(r.mean_faithfulness, '>10.3f')}{r.p50_latency_s:>8.2f}"
            f"{r.max_latency_s:>8.2f}{r.tokens_per_second:>8.1f}"
        )
    return "\n".join(lines)


def parse_spec(spec: str) -> tuple[str, str | None]:
    """'ollama:qwen2.5:14b-instruct' -> ('ollama', 'qwen2.5:14b-instruct'); 'openai' -> ('openai', None)."""
    provider, _, model = spec.partition(":")
    return provider, (model or None)


def _default_pipeline_factory(spec: str) -> RAGPipeline:
    provider, model = parse_spec(spec)
    return RAGPipeline(llm_config=load_config(provider, model=model))


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--providers", nargs="+", default=["openai", "ollama"], help="provider or provider:model specs")
    parser.add_argument(
        "--questions",
        choices=["base", "extended"],
        default="base",
        help="base = 8 goldens; extended = 24 (adds paraphrases) for a steadier faithfulness mean",
    )
    parser.add_argument("--out", help="write full per-case results as JSON")
    parser.add_argument("--skip-faithfulness", action="store_true")
    args = parser.parse_args(argv)

    scorer: Scorer | None = None
    if not args.skip_faithfulness:
        from app.metrics import score_faithfulness

        scorer = score_faithfulness

    goldens = EXTENDED_GOLDENS if args.questions == "extended" else GOLDENS
    reports = [run_provider(p, goldens, _default_pipeline_factory, scorer) for p in args.providers]
    print(format_table(reports))
    if args.out:
        with open(args.out, "w") as f:
            json.dump([asdict(r) for r in reports], f, indent=2)
        print(f"\nper-case results -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
