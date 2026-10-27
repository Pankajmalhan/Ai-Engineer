"""Interactive chat over the graph. ``uv run python -m app.cli``. Memory lives in-process
(MemorySaver), so it lasts for the session; /new starts a fresh thread."""

from __future__ import annotations

import uuid

from dotenv import load_dotenv
from langgraph.checkpoint.memory import MemorySaver

from app.graph import ask, build_graph
from app.llm import build_llm


def main() -> None:
    load_dotenv()
    graph = build_graph(build_llm(), checkpointer=MemorySaver())
    thread_id = str(uuid.uuid4())
    print("Northwind support chat. /new = new thread, /quit = exit.")
    while True:
        try:
            question = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not question:
            continue
        if question == "/quit":
            break
        if question == "/new":
            thread_id = str(uuid.uuid4())
            print(f"(new thread {thread_id})")
            continue
        print(f"bot> {ask(graph, question, thread_id).content}")


if __name__ == "__main__":
    main()
