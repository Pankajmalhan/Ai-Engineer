"""Per-node latency and token counts for the most recent LangSmith traces.

Needs LANGSMITH_API_KEY (and tracing enabled while you ran the demo). Prints, for each
recent root run, every child run of the graph's nodes with its latency and tokens, so you
can see which node dominates time and where tokens go.

    uv run python scripts/trace_report.py [--project default] [--limit 3]
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv


def latency_s(run) -> float:
    if run.start_time and run.end_time:
        return (run.end_time - run.start_time).total_seconds()
    return 0.0


def format_run_line(run) -> str:
    tokens = run.total_tokens or 0
    extra = f"  tokens={tokens} (in={run.prompt_tokens or 0}, out={run.completion_tokens or 0})" if tokens else ""
    return f"  {run.name:<20} {run.run_type:<6} {latency_s(run):6.2f}s{extra}"


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", default=os.environ.get("LANGSMITH_PROJECT", "default"))
    parser.add_argument("--limit", type=int, default=3)
    args = parser.parse_args()

    from langsmith import Client

    client = Client()
    roots = list(client.list_runs(project_name=args.project, is_root=True, limit=args.limit))
    if not roots:
        sys.exit(f"no traces in project {args.project!r} -- run the demo with LANGSMITH_TRACING=true")
    for root in roots:
        print(f"\ntrace {root.id}  total {latency_s(root):.2f}s  tokens={root.total_tokens or 0}")
        children = client.list_runs(project_name=args.project, trace_id=root.trace_id)
        for run in sorted(children, key=lambda r: r.start_time):
            if run.id != root.id:
                print(format_run_line(run))


if __name__ == "__main__":
    main()
