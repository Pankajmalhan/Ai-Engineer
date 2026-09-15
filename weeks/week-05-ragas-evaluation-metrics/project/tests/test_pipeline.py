from app.pipeline import RAGPipeline
from tests.conftest import requires_openai


@requires_openai
def test_pipeline_answer_retrieves_relevant_context_and_generates_a_response():
    pipeline = RAGPipeline()
    result = pipeline.answer("How many days do I have to request a refund on an annual plan?")

    assert result.response.strip()
    assert any("refund" in c.lower() for c in result.retrieved_contexts)
    assert "30" in result.response
