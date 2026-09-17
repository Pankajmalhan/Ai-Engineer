"""Cheap, network-free tests for the RAGAS-dataset -> DeepEval LLMTestCase conversion
itself -- runs on every pytest invocation, no OPENAI_API_KEY required, since it doesn't
touch the pipeline's generation step or any DeepEval metric/judge call.
"""

from app.dataset import EvalSample
from app.deepeval_cases import sample_to_test_case
from app.pipeline import PipelineResult


class _FakePipeline:
    """Stands in for RAGPipeline so this test doesn't need OPENAI_API_KEY."""

    def answer(self, question: str) -> PipelineResult:
        return PipelineResult(
            user_input=question,
            response="a fake generated answer",
            retrieved_contexts=["a fake retrieved chunk"],
        )


def test_sample_to_test_case_maps_ragas_fields_to_deepeval_fields():
    sample = EvalSample(question="q1", reference="ref1", source_doc_id="doc1")

    test_case = sample_to_test_case(sample, _FakePipeline())

    assert test_case.input == "q1"
    assert test_case.actual_output == "a fake generated answer"
    assert test_case.retrieval_context == ["a fake retrieved chunk"]
    assert test_case.expected_output == "ref1"
