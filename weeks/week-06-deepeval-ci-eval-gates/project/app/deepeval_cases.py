"""Converts app/dataset.py's goldens into deepeval.test_case.LLMTestCase objects, by
actually running RAGPipeline for each question. This is the "convert the RAGAS dataset
into DeepEval test cases" step from this week's task.

Field mapping (RAGAS name -> DeepEval name -> where it comes from):
    user_input        -> input              -> EvalSample.question
    response           -> actual_output      -> RAGPipeline.answer()'s generated text
    retrieved_contexts -> retrieval_context   -> RAGPipeline.answer()'s retrieved chunks
    reference          -> expected_output    -> EvalSample.reference

Only question/reference are stored in the dataset (app/dataset.py) -- retrieval_context
and actual_output are produced at test time by actually running the pipeline, same
reasoning as Week 5's dataset docstring: keeps the golden set a fixed regression
fixture independent of pipeline changes.
"""

from __future__ import annotations

from deepeval.test_case import LLMTestCase

from app.dataset import EvalSample, GOLDENS
from app.pipeline import RAGPipeline


def sample_to_test_case(sample: EvalSample, pipeline: RAGPipeline) -> LLMTestCase:
    result = pipeline.answer(sample.question)
    return LLMTestCase(
        input=result.user_input,
        actual_output=result.response,
        retrieval_context=result.retrieved_contexts,
        expected_output=sample.reference,
    )


def build_test_cases(pipeline: RAGPipeline | None = None) -> list[LLMTestCase]:
    pipeline = pipeline or RAGPipeline()
    return [sample_to_test_case(sample, pipeline) for sample in GOLDENS]
