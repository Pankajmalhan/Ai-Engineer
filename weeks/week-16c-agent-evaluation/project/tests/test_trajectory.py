from agent_eval.trajectory import Trajectory, parse_jsonl_stream, read_jsonl, write_jsonl
from tests.conftest import traj


def test_report_puts_saved_files_before_the_final_message():
    t = traj(report="done", files={"/audit.md": "THE REPORT"})
    assert t.report == "THE REPORT\n\ndone"
    assert traj(report="only chat").report == "only chat"


def test_jsonl_round_trip_preserves_everything(tmp_path):
    original = [traj("a", "x", calls=[("search_code", {"k": 3})], handoffs=["code_agent"], llm_calls=4, total_tokens=None, meta={"arch": "deep"}),
                traj("b", "y", error="boom")]
    path = tmp_path / "runs.jsonl"
    write_jsonl(path, original)
    assert read_jsonl(path) == original


def test_stream_parser_skips_library_noise_and_bad_lines():
    good = traj("ok", "fine").model_dump_json()
    noisy = f"warming up...\n{good}\n{{not json}}\n[progress] 50%\n"
    parsed = list(parse_jsonl_stream(noisy))
    assert [t.id for t in parsed] == ["ok"]


def test_tool_names_keep_call_order_and_duplicates():
    assert traj(calls=["a", "b", "a"]).tool_names() == ["a", "b", "a"]


def test_a_minimal_record_is_valid():
    t = Trajectory(id="x", user_input="q")
    assert t.tool_calls == [] and t.report == "" and t.total_tokens is None
