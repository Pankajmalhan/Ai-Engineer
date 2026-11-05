import sys
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from trace_report import format_run_line, latency_s


def _run(name, run_type, seconds, total=None, prompt=None, completion=None):
    start = datetime(2026, 1, 1)
    return SimpleNamespace(
        name=name, run_type=run_type, start_time=start, end_time=start + timedelta(seconds=seconds),
        total_tokens=total, prompt_tokens=prompt, completion_tokens=completion,
    )


def test_latency_is_end_minus_start():
    assert latency_s(_run("n", "chain", 1.5)) == 1.5


def test_llm_run_line_shows_tokens_and_chain_line_does_not():
    llm_line = format_run_line(_run("ChatOpenAI", "llm", 0.8, 120, 100, 20))
    assert "tokens=120 (in=100, out=20)" in llm_line
    assert "tokens" not in format_run_line(_run("retrieve_context", "chain", 0.01))
