from app.dataset import EvalSample
from app.evaluate import _build_dataset, run_evaluation
from app.pipeline import PipelineResult
from tests.conftest import requires_openai

_FAKE_RESULTS = [
    PipelineResult(user_input="q1", response="a1", retrieved_contexts=["ctx1"]),
    PipelineResult(user_input="q2", response="a2", retrieved_contexts=["ctx2"]),
]
_FAKE_SAMPLES = [
    EvalSample(question="q1", reference="ref1", source_doc_id="doc1", label="hand"),
    EvalSample(question="q2", reference="ref2", source_doc_id="doc2", label="hand"),
]


def test_build_dataset_legacy_api_shape():
    dataset = _build_dataset(_FAKE_RESULTS, _FAKE_SAMPLES)
    assert len(dataset) == 2
    assert dataset["ground_truth"] == ["ref1", "ref2"]


@requires_openai
def test_run_evaluation_on_two_hand_labeled_samples_returns_all_metric_scores():
    from app.dataset import HAND_LABELED

    # Only 2 samples -- this hits OpenAI + RAGAS's LLM judge for real; kept minimal
    # deliberately. The full 50-sample run is a manual `uv run python runner.py
    # INCLUDE_SYNTHETIC=1` invocation, not part of the automated test suite.
    summary = run_evaluation(HAND_LABELED[:2])

    assert summary.sample_count == 2
    assert len(summary.scores) == 6
    assert summary.weakest_metric in summary.scores
