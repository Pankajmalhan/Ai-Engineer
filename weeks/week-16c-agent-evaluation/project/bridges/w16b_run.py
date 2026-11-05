"""Run the Week 16b supervisor loop and Deep Agent over the eval tasks; print one Trajectory per line.

Executed inside the Week 16b project's own environment:

    uv run --project <week-16b>/project python bridges/w16b_run.py \
        --w16b-root <week-16b>/project --tasks data/tasks_10.json --arch both --trials 3        # real model
    ... --offline                                                                              # scripted, task t08 only

What it records that Week 16b's own table does not: every tool call IN ORDER with its arguments, sub-agent
calls included (a callback sees inside the sub-agents), who was delegated to, and the saved files.

Honest limits:
* Week 16b's supervisor writer prompt is audit-shaped ("sections Location / Rule violations / ..."). For
  these mixed questions it is replaced with a neutral "answer concisely from the evidence" prompt; nothing
  else in Week 16b's code is changed.
* --offline uses Week 16b's scripted "oracle" models, which only know the t08 audit. Other tasks are skipped
  (stderr says so) -- a scripted model can't answer questions it wasn't written for.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path

NEUTRAL_WRITER_PROMPT = (
    "Answer the user's task concisely in markdown, using only the evidence in the thread. "
    "Quote the exact values (rule ids, numbers, file paths) you rely on. If the evidence does not "
    "contain the answer, say so plainly instead of guessing."
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--w16b-root", required=True, type=Path)
    parser.add_argument("--tasks", required=True, type=Path)
    parser.add_argument("--arch", choices=["supervisor", "deep", "both"], default="both")
    parser.add_argument("--trials", type=int, default=1)
    parser.add_argument("--max-hops", type=int, default=6)
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()

    sys.path.insert(0, str(args.w16b_root))
    from deepagents.backends.utils import file_data_to_string
    from langchain_core.callbacks import BaseCallbackHandler
    from langchain_core.messages import HumanMessage

    import app.supervisor as sup
    from app import offline
    from app.deep import build_deep_agent
    from app.metrics import RunMetrics
    from app.supervisor import LLMPlanner, build_supervisor_graph, initial_state
    from app.task import DEEP_SUFFIX

    sup.WRITER_PROMPT = NEUTRAL_WRITER_PROMPT

    class ToolRecorder(BaseCallbackHandler):
        """Ordered (name, args) of every tool call anywhere in the run, nested sub-agents included."""

        def __init__(self) -> None:
            self.calls: list[dict] = []

        def on_tool_start(self, serialized, input_str, *, inputs=None, name=None, **kwargs):
            tool = name or (serialized or {}).get("name") or "unknown"
            self.calls.append({"name": tool, "args": inputs if isinstance(inputs, dict) else {"input": input_str}})

    if not args.offline:
        from dotenv import load_dotenv

        load_dotenv(args.w16b_root / ".env")
        from app.llm import build_llm

        llm = build_llm()

    def emit(task, arch, trial, **fields) -> None:
        print(json.dumps({"id": task["id"], "user_input": task["user_goal"],
                          "meta": {"arch": arch, "trial": trial, "system": "week-16b", "offline": args.offline}, **fields}))

    def run_supervisor(task, trial) -> None:
        if args.offline:
            planner, writer = offline.default_planner(), offline.oracle_writer()
        else:
            planner, writer = LLMPlanner(llm), llm
        graph = build_supervisor_graph(planner, writer, max_hops=args.max_hops)
        metrics = RunMetrics()
        try:
            out = graph.invoke(initial_state(task["user_goal"]), config={"callbacks": [metrics], "recursion_limit": 100})
        except Exception as exc:
            emit(task, "supervisor", trial, error=f"{type(exc).__name__}: {exc}")
            return
        m = metrics.finish(out["messages"])
        calls = []
        for msg in out["messages"]:
            found = re.match(r"\[(\w+)\] results for (.*):\n", str(msg.content)) if getattr(msg, "name", None) else None
            if found:
                try:
                    query = ast.literal_eval(found.group(2))
                except (ValueError, SyntaxError):
                    query = found.group(2)
                calls.append({"name": found.group(1), "args": {"query": query}})
        emit(task, "supervisor", trial, tool_calls=calls, handoffs=[f"{c}_agent" for c in out["trail"]],
             final_output=str(out["messages"][-1].content), llm_calls=m.llm_calls, total_tokens=m.total_tokens)

    def run_deep(task, trial) -> None:
        if args.offline:
            lead, subs = offline.deep_models()
            agent = build_deep_agent(lead, subagent_models=subs)
        else:
            agent = build_deep_agent(llm)
        metrics, recorder = RunMetrics(), ToolRecorder()
        try:
            out = agent.invoke({"messages": [HumanMessage(content=task["user_goal"] + DEEP_SUFFIX)]},
                               config={"callbacks": [metrics, recorder], "recursion_limit": 100})
        except Exception as exc:
            emit(task, "deep", trial, error=f"{type(exc).__name__}: {exc}")
            return
        m = metrics.finish(out["messages"])
        files = {path: file_data_to_string(data) for path, data in (out.get("files") or {}).items()}
        handoffs = [c["args"].get("subagent_type", "?") for c in recorder.calls if c["name"] == "task"]
        emit(task, "deep", trial, tool_calls=recorder.calls, handoffs=handoffs, files=files,
             final_output=str(out["messages"][-1].content), llm_calls=m.llm_calls, total_tokens=m.total_tokens)

    for task in json.loads(args.tasks.read_text()):
        if args.offline and task["id"] != "t08":
            print(f"[offline] skipping {task['id']}: scripted models only know the t08 audit", file=sys.stderr)
            continue
        for trial in range(args.trials):
            if args.arch in ("supervisor", "both"):
                run_supervisor(task, trial)
            if args.arch in ("deep", "both"):
                run_deep(task, trial)


if __name__ == "__main__":
    main()
