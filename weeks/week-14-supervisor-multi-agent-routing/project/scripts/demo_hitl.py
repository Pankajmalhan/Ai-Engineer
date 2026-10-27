"""Walk through both interrupts in a terminal: clarification, then tool-call approval.

    uv run python scripts/demo_hitl.py                    # offline keyword classifier
    uv run python scripts/demo_hitl.py --classifier llm   # real model
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv  # noqa: E402
from langgraph.checkpoint.memory import InMemorySaver  # noqa: E402

from app.classifiers import HeuristicClassifier, LLMClassifier  # noqa: E402
from app.graph import ask, build_graph, resume  # noqa: E402


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

    graph = build_graph(classifier, checkpointer=InMemorySaver(), require_approval=True)
    print("Type a question (ctrl-c to quit). The graph will pause to ask you things.\n")
    thread = "demo"
    while True:
        turn = ask(graph, input("you> "), thread)
        while turn.interrupted:
            payload = turn.interrupt
            if payload["type"] == "clarification":
                print(f"[supervisor] {payload['question']}")
                turn = resume(graph, input("you> "), thread)
            else:  # approve_tool_call
                print(f"[{payload['agent']}] wants to call {payload['tool']}({payload['args']})")
                turn = resume(graph, input("approve? [y/N] ").strip().lower() == "y", thread)
        print(f"{turn.answer}\n")


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        print()
