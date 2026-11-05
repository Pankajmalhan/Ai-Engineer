import time

from app.compare import Row, render_markdown, run_comparison, summarize
from app.queries import QUERIES
from app.scoring import score
from app.tracing import Tracing, tracing_requested
from app.types import PipelineResult


class FixedPipeline:
    """A stub pipeline: lets us test the comparison maths without any framework."""

    def __init__(self, framework, answer, latency=0.0):
        self.framework, self.answer, self.latency = framework, answer, latency

    def run(self, question):
        time.sleep(self.latency)
        return PipelineResult(self.framework, question, self.answer, retrieved_ids=["uptime-sla"], kept_ids=["uptime-sla"], latency_s=self.latency, llm_calls=2)


def test_warmup_query_is_not_counted():
    rows = run_comparison([FixedPipeline("a", "x")], queries=QUERIES[:3], warmup=True)
    assert len(rows["a"]) == 3


def test_summary_math_on_known_inputs():
    good = FixedPipeline("g", "10% and 4 business hours")
    rows = run_comparison([good], queries=[QUERIES[0]], warmup=False)["g"]
    s = summarize(rows)
    assert s["answerable_correct"] == 1.0 and s["mean_fact_recall"] == 1.0 and s["errors"] == 0
    assert s["llm_calls_mean"] == 2


def test_disagreement_is_reported_when_one_framework_is_worse():
    rows = run_comparison([FixedPipeline("good", "10% and 4 business hours"), FixedPipeline("bad", "no idea")], queries=QUERIES[:2], warmup=False)
    report = render_markdown(rows, "stub")
    assert "| good | bad |" in report.replace("| metric | ", "| ") or "good" in report and "bad" in report
    assert "q01" in report.split("disagree on correctness:")[1].splitlines()[0]


def test_latency_is_measured_per_pipeline_not_shared():
    slow, fast = FixedPipeline("slow", "x", latency=0.05), FixedPipeline("fast", "x", latency=0.0)
    rows = run_comparison([slow, fast], queries=QUERIES[:2], warmup=False)
    assert summarize(rows["slow"])["latency_mean_s"] >= 0.05 > summarize(rows["fast"])["latency_mean_s"]


# ---- tracing is strictly optional ------------------------------------------------------------
def test_tracing_requested_needs_both_langfuse_keys():
    assert not tracing_requested({})
    assert not tracing_requested({"LANGFUSE_PUBLIC_KEY": "pk"})
    assert tracing_requested({"LANGFUSE_PUBLIC_KEY": "pk", "LANGFUSE_SECRET_KEY": "sk"})


def test_disabled_tracing_is_a_no_op():
    t = Tracing(enabled=False)
    assert not t.enabled and t.langgraph_callbacks() == []
    with t.query_span("crewai", "q01"):
        pass
    t.flush()


def test_tracing_setup_failure_degrades_to_disabled_instead_of_breaking_the_run(monkeypatch, capsys):
    import langfuse

    def boom():
        raise RuntimeError("bad credentials")

    monkeypatch.setattr(langfuse, "get_client", boom)
    t = Tracing(enabled=True)
    assert not t.enabled
    assert "[tracing] disabled" in capsys.readouterr().err
