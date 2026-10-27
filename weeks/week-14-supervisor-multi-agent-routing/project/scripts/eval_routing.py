"""Run the 10-query routing eval.

    uv run python scripts/eval_routing.py                 # offline keyword baseline
    uv run python scripts/eval_routing.py --classifier llm   # real model (needs OPENAI_API_KEY)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv  # noqa: E402

from app.classifiers import HeuristicClassifier, LLMClassifier  # noqa: E402
from app.routing_eval import run_eval, summarize  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--classifier", choices=["heuristic", "llm"], default="heuristic")
    args = parser.parse_args()
    load_dotenv()

    if args.classifier == "llm":
        from app.llm import build_llm

        classifier = LLMClassifier(build_llm())
    else:
        classifier = HeuristicClassifier()

    results = run_eval(classifier)
    print(f"{'query':<72} {'expect':<7} {'1st':<7} {'conf':<5} {'asked':<6} {'final':<7} ok")
    for r in results:
        print(
            f"{r.case.query[:70]:<72} {r.case.expected:<7} {r.first_pass:<7} {r.first_confidence:<5.2f} "
            f"{'yes' if r.asked else 'no':<6} {r.routed_to:<7} {'✓' if r.correct else '✗'}"
        )
    print()
    for name, value in summarize(results).items():
        print(f"{name}: {value:.0%}")


if __name__ == "__main__":
    main()
