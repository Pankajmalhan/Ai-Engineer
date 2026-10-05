from app.pipeline import RAGPipeline


def test_answer_returns_contexts_and_doc_ids(pipeline: RAGPipeline):
    result = pipeline.answer("What's the refund window for annual plans?")
    assert result.retrieved_contexts
    assert len(result.retrieved_contexts) == len(result.retrieved_doc_ids)
    assert "refunds" in result.retrieved_doc_ids


def test_answer_carries_through_stubbed_generation(pipeline: RAGPipeline):
    result = pipeline.answer("What's the refund window for annual plans?")
    assert result.answer.startswith("stub answer for:")
    assert result.input_tokens == 42
    assert result.output_tokens == 7
