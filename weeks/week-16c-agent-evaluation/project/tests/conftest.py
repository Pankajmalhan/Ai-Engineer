import os

import pytest

os.environ.setdefault("DEEPEVAL_TELEMETRY_OPT_OUT", "YES")

from agent_eval.trajectory import ToolCall, Trajectory  # noqa: E402

requires_openai = pytest.mark.skipif(
    not os.environ.get("OPENAI_API_KEY"),
    reason="OPENAI_API_KEY not set -- the LLM-judged agent metrics need a judge model",
)


def traj(id="t01", report="", *, calls=(), handoffs=(), files=None, **kw) -> Trajectory:
    """Terse trajectory builder. ``calls`` = tool names or (name, args) pairs."""
    tool_calls = [ToolCall(name=c) if isinstance(c, str) else ToolCall(name=c[0], args=c[1]) for c in calls]
    return Trajectory(id=id, user_input=kw.pop("user_input", "q"), tool_calls=tool_calls, handoffs=list(handoffs),
                      final_output=report, files=files or {}, **kw)
