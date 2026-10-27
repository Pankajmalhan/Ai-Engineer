"""Run the REAL Week 14 supervisor graph over the labelled routing queries; print one Trajectory per line.

Executed inside the Week 14 project's own environment (it has langgraph; this project's package is not
installed there), so it speaks the Trajectory JSON contract by hand instead of importing agent_eval:

    uv run --project <week-14>/project python bridges/w14_route.py \
        --w14-root <week-14>/project --dataset data/routing_30.json [--classifier heuristic|llm]

Faithfulness notes (what this does and does not do to Week 14's code):
* the graph, classifier, retrievers and interrupt/resume flow are Week 14's, unmodified;
* when the supervisor asks a question and the dataset has no scripted clarification, the human "replies"
  with a content-free "no more detail" -- Week 14's clarify node then re-classifies once and routes its
  best guess. That run is recorded with asked=True so an unwanted question is visible, not hidden.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--w14-root", required=True, type=Path)
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--classifier", choices=["heuristic", "llm"], default="heuristic")
    args = parser.parse_args()

    sys.path.insert(0, str(args.w14_root))
    from langgraph.checkpoint.memory import InMemorySaver

    from app.classifiers import HeuristicClassifier, LLMClassifier
    from app.graph import TOP_K, ask, build_graph, default_retrievers, resume

    if args.classifier == "llm":
        from dotenv import load_dotenv

        load_dotenv(args.w14_root / ".env")
        from app.llm import build_llm

        classifier = LLMClassifier(build_llm())
    else:
        classifier = HeuristicClassifier()
    retriever_names = {cat: fn.__name__ for cat, fn in default_retrievers().items()}

    for item in json.loads(args.dataset.read_text()):
        graph = build_graph(classifier, checkpointer=InMemorySaver())
        thread = item["id"]
        turn = ask(graph, item["query"], thread)
        asked, first = turn.interrupted, dict(turn.route)
        if asked:
            turn = resume(graph, item.get("clarification") or "no more detail", thread)
        if not asked:
            first = dict(turn.route)
        category = (turn.agent or "").removesuffix("_agent")
        print(json.dumps({
            "id": item["id"],
            "user_input": item["query"],
            "tool_calls": [{"name": retriever_names[category], "args": {"query": item["query"], "k": TOP_K}}] if category in retriever_names else [],
            "handoffs": [turn.agent] if turn.agent else [],
            "final_output": turn.answer or "",
            "meta": {
                "expected": item["expected"], "routed_to": category, "subset": item["subset"],
                "ambiguous": item["ambiguous"], "asked": asked,
                "first_pass": first.get("category"), "first_confidence": first.get("confidence"),
                "classifier": args.classifier, "system": "week-14-supervisor",
            },
        }))


if __name__ == "__main__":
    main()
