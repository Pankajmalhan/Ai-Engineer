"""Multi-turn demo against the real model: a follow-up that only makes sense with memory,
then the same follow-up on a fresh thread to show the contrast. Needs OPENAI_API_KEY.
Set LANGSMITH_TRACING=true and LANGSMITH_API_KEY to also get a trace per turn.

    uv run python scripts/demo_multiturn.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from langgraph.checkpoint.memory import MemorySaver

from app.graph import ask, build_graph
from app.llm import build_llm

load_dotenv()

graph = build_graph(build_llm(), checkpointer=MemorySaver())

print("== thread 'alice' (memory on) ==")
for q in [
    "What is the rate limit on the Pro tier?",
    "And what happens when I exceed that?",  # 'that' only resolves via memory
    "Repeat the number from your first answer.",  # references the previous answer
]:
    print(f"you> {q}\nbot> {ask(graph, q, 'alice').content}\n")

print("== thread 'bob' (fresh thread, same follow-up) ==")
q = "Repeat the number from your first answer."
print(f"you> {q}\nbot> {ask(graph, q, 'bob').content}")
