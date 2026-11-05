"""Run the audit through three architectures and print one comparison table.

    uv run python -m app.compare --offline     # scripted models: checks the plumbing, says nothing about quality
    uv run python -m app.compare               # real model (OPENAI_API_KEY): the comparison that matters

Rows:
  supervisor, 1 hop   the Week 14 pattern as written: route once, answer
  supervisor, loop    the same supervisor allowed to hop until it says `finish`
  deep agent          the `deepagents` harness: planning + sub-agents + virtual filesystem
"""

from __future__ import annotations

import argparse

from app import offline
from app.runners import RunResult, run_deep, run_supervisor


def offline_runs(max_hops: int) -> list[RunResult]:
    lead, subs = offline.deep_models()
    return [
        run_supervisor("supervisor, 1 hop", offline.default_planner(), offline.oracle_writer(), max_hops=1),
        run_supervisor(f"supervisor, loop (<={max_hops})", offline.default_planner(), offline.oracle_writer(), max_hops=max_hops),
        run_deep("deep agent", lead, subagent_models=subs),
    ]


def live_runs(max_hops: int) -> list[RunResult]:
    from dotenv import load_dotenv

    from app.llm import build_llm
    from app.supervisor import LLMPlanner

    load_dotenv()
    llm = build_llm()
    return [
        run_supervisor("supervisor, 1 hop", LLMPlanner(llm), llm, max_hops=1),
        run_supervisor(f"supervisor, loop (<={max_hops})", LLMPlanner(llm), llm, max_hops=max_hops),
        run_deep("deep agent", llm),
    ]


def format_table(results: list[RunResult]) -> str:
    header = f"{'architecture':<24} {'facts':>5} {'llm':>4} {'tools':>5} {'tokens':>8} {'thread chars':>12} {'secs':>6}  report"
    lines = [header, "-" * len(header)]
    for r in results:
        m = r.metrics
        tokens = "n/a" if m.total_tokens is None else str(m.total_tokens)
        report = f"ERROR {r.error}" if r.error else r.report_source
        lines.append(
            f"{r.name:<24} {str(r.score):>5} {m.llm_calls:>4} {m.total_tool_calls:>5} {tokens:>8} {m.thread_chars:>12} {m.elapsed_s:>6.1f}  {report}"
        )
    return "\n".join(lines)


def format_details(results: list[RunResult]) -> str:
    out = []
    for r in results:
        out.append(f"\n{r.name}")
        out.append(f"  missing facts : {', '.join(r.score.missing) or '(none)'}")
        out.append(f"  tool calls    : {dict(r.metrics.tool_calls)}")
        out.extend(f"  {note}" for note in r.notes)
    return "\n".join(out)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--offline", action="store_true", help="use scripted models (no API key)")
    parser.add_argument("--max-hops", type=int, default=6, help="hop cap for the looping supervisor")
    args = parser.parse_args()

    results = offline_runs(args.max_hops) if args.offline else live_runs(args.max_hops)
    if args.offline:
        print("OFFLINE: scripted models. Tokens are n/a and scores are by construction -- this checks wiring, not quality.\n")
    print(format_table(results))
    print(format_details(results))


if __name__ == "__main__":
    main()
