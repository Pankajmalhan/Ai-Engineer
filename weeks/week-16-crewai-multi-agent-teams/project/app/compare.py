"""Run the 20 queries through both pipelines and compare answer quality and latency.

    uv run python -m app.compare                       # gpt-4o-mini (needs OPENAI_API_KEY in .env)
    uv run python -m app.compare --model gpt-4o        # another OpenAI model
    uv run python -m app.compare --manager             # also run the hierarchical (manager) crew
    uv run python -m app.compare --flow                # also run the CrewAI Flow
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol

from app.queries import QUERIES, Query
from app.scoring import Score, score
from app.tracing import Tracing
from app.types import PipelineResult


class Pipeline(Protocol):
    framework: str

    def run(self, question: str) -> PipelineResult: ...


@dataclass
class Row:
    result: PipelineResult
    score: Score
    query: Query


def run_comparison(pipelines: list[Pipeline], queries: list[Query] | None = None, warmup: bool = True, tracing: Tracing | None = None) -> dict[str, list[Row]]:
    """Each query goes through every pipeline, one after the other (never concurrently, so latencies
    are not contaminated by the other pipeline). One untimed warm-up query per pipeline first, so
    import/first-call costs don't land on query 1."""
    queries = queries if queries is not None else QUERIES
    tracing = tracing or Tracing(enabled=False)
    if warmup:
        for p in pipelines:
            p.run("How long are request logs retained?")
    rows: dict[str, list[Row]] = {p.framework: [] for p in pipelines}
    for q in queries:
        for p in pipelines:
            with tracing.query_span(p.framework, q.id):
                result = p.run(q.question)
            rows[p.framework].append(Row(result, score(result, q), q))
    tracing.flush()
    return rows


def _mean(values: list[float]) -> float | None:
    return statistics.fmean(values) if values else None


def _pct(values: list[float], p: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round(p * (len(ordered) - 1)))]


def summarize(rows: list[Row]) -> dict:
    answerable = [r for r in rows if r.query.answerable]
    unanswerable = [r for r in rows if not r.query.answerable]
    latencies = [r.result.latency_s for r in rows if not r.result.error]
    tokens = [r.result.total_tokens for r in rows if r.result.total_tokens]
    return {
        "queries": len(rows),
        "errors": sum(r.score.error for r in rows),
        "answerable_correct": sum(r.score.correct for r in answerable) / len(answerable) if answerable else None,
        "mean_fact_recall": _mean([r.score.fact_recall for r in answerable]),
        "abstained_on_unanswerable": sum(r.score.correct for r in unanswerable) / len(unanswerable) if unanswerable else None,
        "retrieval_recall": _mean([r.score.retrieval_recall for r in answerable if r.score.retrieval_recall is not None]),
        "grader_kept_recall": _mean([r.score.kept_recall for r in answerable if r.score.kept_recall is not None]),
        "grader_kept_precision": _mean([r.score.kept_precision for r in answerable if r.score.kept_precision is not None]),
        "latency_mean_s": _mean(latencies),
        "latency_p50_s": _pct(latencies, 0.5),
        "latency_p95_s": _pct(latencies, 0.95),
        "llm_calls_mean": _mean([r.result.llm_calls for r in rows if not r.result.error]),
        "tokens_mean": _mean(tokens),
    }


def _fmt(value, kind: str = "num") -> str:
    if value is None:
        return "n/a"
    if kind == "pct":
        return f"{value:.0%}"
    if kind == "s":
        return f"{value:.3f}s"
    if kind == "int":
        return f"{int(value)}"
    return f"{value:.1f}"


METRIC_ROWS = [
    ("answerable queries fully correct", "answerable_correct", "pct"),
    ("mean fact recall (answerable)", "mean_fact_recall", "pct"),
    ("abstained on unanswerable (3)", "abstained_on_unanswerable", "pct"),
    ("retriever recall of expected docs", "retrieval_recall", "pct"),
    ("grader: expected docs kept (recall)", "grader_kept_recall", "pct"),
    ("grader: kept docs that were expected (precision)", "grader_kept_precision", "pct"),
    ("errors", "errors", "int"),
    ("latency mean", "latency_mean_s", "s"),
    ("latency p50", "latency_p50_s", "s"),
    ("latency p95", "latency_p95_s", "s"),
    ("LLM calls per query (mean)", "llm_calls_mean", "num"),
    ("tokens per query (mean)", "tokens_mean", "num"),
]


def render_markdown(rows_by_fw: dict[str, list[Row]], backend_description: str) -> str:
    names = list(rows_by_fw)
    summaries = {fw: summarize(rows) for fw, rows in rows_by_fw.items()}
    lines = [f"# CrewAI vs LangGraph -- 20 queries", "", f"Backend: {backend_description}", ""]
    lines += ["| metric | " + " | ".join(names) + " |", "|---|" + "---|" * len(names)]
    for label, key, kind in METRIC_ROWS:
        lines.append(f"| {label} | " + " | ".join(_fmt(summaries[fw][key], kind) for fw in names) + " |")

    lines += ["", "## Per query", "", "| id | kind | " + " | ".join(f"{fw} correct / s / calls" for fw in names) + " |", "|---|---|" + "---|" * len(names)]
    for i, query in enumerate(QUERIES):
        cells = []
        for fw in names:
            row = rows_by_fw[fw][i] if i < len(rows_by_fw[fw]) else None
            cells.append("-" if row is None else ("ERROR" if row.score.error else f"{'yes' if row.score.correct else 'NO'} / {row.result.latency_s:.2f} / {row.result.llm_calls}"))
        lines.append(f"| {query.id} | {query.kind} | " + " | ".join(cells) + " |")

    disagree = [QUERIES[i].id for i in range(len(rows_by_fw[names[0]])) if len({rows_by_fw[fw][i].score.correct for fw in names}) > 1]
    lines += ["", f"Queries where the frameworks disagree on correctness: {', '.join(disagree) or 'none'}", ""]
    lines += ["_Facts are scored by substring match against an answer key (see app/queries.py): a coarse proxy, so read differences of a query or two as noise._", ""]
    return "\n".join(lines)


def main() -> None:
    from dotenv import load_dotenv
    from crewai import LLM
    from langchain_openai import ChatOpenAI

    from app.crew_flow_pipeline import CrewFlowPipeline
    from app.crew_manager_pipeline import CrewManagerPipeline
    from app.crew_pipeline import CrewPipeline
    from app.graph_pipeline import GraphPipeline
    from app.tracing import tracing_requested

    load_dotenv()
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="gpt-4o-mini")
    parser.add_argument("--manager", action="store_true", help="also run the hierarchical crew (a manager agent routes the work)")
    parser.add_argument("--flow", action="store_true", help="also run the CrewAI Flow (Python routes, small crews do the LLM work)")
    parser.add_argument("--out-dir", default="results")
    parser.add_argument("--no-trace", action="store_true", help="do not send traces to Langfuse even if keys are set")
    args = parser.parse_args()

    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("error: OPENAI_API_KEY is not set (put it in .env -- see .env.example)")

    tracing = Tracing(enabled=tracing_requested() and not args.no_trace)
    description = f"OpenAI {args.model} (temperature 0) for both frameworks"
    # a NEW CrewAI LLM per agent (see build_crew); one ChatOpenAI is fine for LangGraph
    pipelines = [
        CrewPipeline(lambda: LLM(model=f"openai/{args.model}", temperature=0)),
        GraphPipeline(ChatOpenAI(model=args.model, temperature=0), extra_callbacks=tracing.langgraph_callbacks()),
    ]
    if args.manager:
        pipelines.insert(1, CrewManagerPipeline(lambda: LLM(model=f"openai/{args.model}", temperature=0)))
    if args.flow:
        pipelines.insert(1, CrewFlowPipeline(lambda: LLM(model=f"openai/{args.model}", temperature=0)))
    print(f"{description} | tracing: {'langfuse' if tracing.enabled else 'off'}")

    rows = run_comparison(pipelines, tracing=tracing)
    report = render_markdown(rows, description)
    print(report)

    out = Path(args.out_dir)
    out.mkdir(exist_ok=True)
    stem = f"comparison-{args.model}"
    (out / f"{stem}.md").write_text(report)
    (out / f"{stem}.json").write_text(json.dumps({fw: [{**asdict(r.result), "score": asdict(r.score), "id": r.query.id} for r in rs] for fw, rs in rows.items()}, indent=2))
    print(f"wrote {out / (stem + '.md')} and .json")


if __name__ == "__main__":
    main()
