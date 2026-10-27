"""Re-record trajectories by running the other weeks' agents through their bridges.

    uv run python scripts/record.py w14                       # Week 14 supervisor, keyword baseline (no API key)
    uv run python scripts/record.py w14 --classifier llm      # Week 14 supervisor with the LLM classifier (OPENAI_API_KEY)
    uv run python scripts/record.py w16b --offline            # scripted t08 only: shows the trajectory shape, says nothing about quality
    uv run python scripts/record.py w16b --trials 3           # real model, tasks_10 x {supervisor, deep} x 3 trials
    uv run python scripts/record.py w16b --tasks hard_5 --trials 4
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent_eval.bridge import ROOT, W14_PROJECT, W16B_PROJECT, run_bridge  # noqa: E402
from agent_eval.datasets import RUNS  # noqa: E402
from agent_eval.trajectory import write_jsonl  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="system", required=True)
    w14 = sub.add_parser("w14")
    w14.add_argument("--classifier", choices=["heuristic", "llm"], default="heuristic")
    w16b = sub.add_parser("w16b")
    w16b.add_argument("--tasks", choices=["tasks_10", "hard_5"], default="tasks_10")
    w16b.add_argument("--arch", choices=["supervisor", "deep", "both"], default="both")
    w16b.add_argument("--trials", type=int, default=1)
    w16b.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    RUNS.mkdir(exist_ok=True)

    if args.system == "w14":
        out = RUNS / f"w14_{args.classifier}.jsonl"
        trajs = run_bridge(W14_PROJECT, "w14_route.py", ["--w14-root", str(W14_PROJECT), "--dataset", str(ROOT / "data" / "routing_30.json"), "--classifier", args.classifier])
    else:
        out = RUNS / (f"w16b_offline_t08.jsonl" if args.offline else f"w16b_{args.tasks}.jsonl")
        extra = ["--offline"] if args.offline else []
        trajs = run_bridge(W16B_PROJECT, "w16b_run.py", ["--w16b-root", str(W16B_PROJECT), "--tasks", str(ROOT / "data" / f"{args.tasks}.json"),
                                                        "--arch", args.arch, "--trials", str(args.trials), *extra], timeout=3600)
    write_jsonl(out, trajs)
    print(f"wrote {len(trajs)} trajectories to {out}")


if __name__ == "__main__":
    main()
