"""Score recorded runs. Deterministic metrics always run; LLM-judged ones only with --judge (needs OPENAI_API_KEY).

    uv run python scripts/evaluate.py routing                      # handoff accuracy + RAGAS/DeepEval tool-call metrics on data/runs/w14_heuristic.jsonl
    uv run python scripts/evaluate.py routing --runs data/runs/w14_llm.jsonl --langfuse
    uv run python scripts/evaluate.py compare --runs data/runs/w16b_tasks_10.jsonl --tasks tasks_10
    uv run python scripts/evaluate.py compare --runs data/runs/w16b_hard_5.jsonl --tasks hard_5
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent_eval.compare import format_summary, summarize  # noqa: E402
from agent_eval.datasets import RUNS, load_routing, load_tasks  # noqa: E402
from agent_eval.gate import routing_gate  # noqa: E402
from agent_eval.trajectory import read_jsonl  # noqa: E402


def routing(args) -> int:
    from agent_eval.deepeval_metrics import tool_correctness
    from agent_eval.ragas_metrics import score_tool_calls_sync

    trajs = read_jsonl(args.runs)
    items = {i.id: i for i in load_routing()}
    report, gates = routing_gate(trajs)
    print(report.format())
    print("\nmisroutes:")
    for r in report.misroutes:
        print(f"  {r.id}: expected {r.expected}, routed {r.routed_to} (first guess {r.first_pass} @ {r.first_confidence:.2f}, asked={r.asked})")

    pairs = [(t, items[t.id].reference_tool_calls) for t in trajs]
    ragas = score_tool_calls_sync(pairs)
    de = tool_correctness(pairs)
    print(f"\nRAGAS ToolCallAccuracy {ragas.mean_accuracy:.3f} | RAGAS ToolCallF1 {ragas.mean_f1:.3f} | DeepEval ToolCorrectness {sum(de) / len(de):.3f}")
    print("\n".join(str(g) for g in gates))

    if args.judge:
        import asyncio

        from agent_eval.ragas_metrics import build_ragas_judge, score_goal_accuracy

        goals = asyncio.run(score_goal_accuracy([(t, items[t.id].reference) for t in trajs], build_ragas_judge()))
        print(f"RAGAS AgentGoalAccuracy {sum(goals) / len(goals):.3f}  (LLM-judged)")
    if args.langfuse:
        from agent_eval.langfuse_log import langfuse_configured, log_routing_run

        if not langfuse_configured():
            print("langfuse: LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY not set -- skipped")
        else:
            result = log_routing_run(list(items.values()), trajs, run_name=args.runs.stem)
            print(result.format())
    return 0 if all(g.passed for g in gates) else 1


def compare(args) -> int:
    trajs = read_jsonl(args.runs)
    print(format_summary(summarize(trajs, load_tasks(args.tasks))))
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("routing")
    r.add_argument("--runs", type=Path, default=RUNS / "w14_heuristic.jsonl")
    r.add_argument("--judge", action="store_true")
    r.add_argument("--langfuse", action="store_true")
    c = sub.add_parser("compare")
    c.add_argument("--runs", type=Path, required=True)
    c.add_argument("--tasks", choices=["tasks_10", "hard_5"], default="tasks_10")
    args = parser.parse_args()
    sys.exit(routing(args) if args.cmd == "routing" else compare(args))


if __name__ == "__main__":
    main()
