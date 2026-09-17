"""The actual CI eval gate: runs the pipeline over every golden in app/dataset.py,
converts each to an LLMTestCase, and asserts all three metrics clear this week's
thresholds. assert_test raises AssertionError the moment one metric misses -- which is
exactly what fails `pytest` (and therefore the GitHub Actions job, and therefore the
merge gate; see .github/workflows/ and concept.md).

Run locally:
    uv run pytest tests/test_rag_quality.py -v
    # or, for DeepEval's own CLI runner (adds -x/--repeat/etc, same underlying pytest):
    uv run deepeval test run tests/test_rag_quality.py

Reproduce this week's "deliberately bad change" step:
    BREAK_RETRIEVAL=1 uv run pytest tests/test_rag_quality.py -v
"""

import pytest
from deepeval import assert_test
from deepeval.metrics import AnswerRelevancyMetric, ContextualRecallMetric, FaithfulnessMetric
from deepeval.test_case import LLMTestCase

from app.config import (
    ANSWER_RELEVANCY_THRESHOLD,
    CONTEXT_RECALL_THRESHOLD,
    DEEPEVAL_MODEL,
    FAITHFULNESS_THRESHOLD,
)
from app.deepeval_cases import build_test_cases
from app.llm import openai_available


def _collect_test_cases() -> list:
    """Builds the parametrize list at collection time. When no OPENAI_API_KEY is set,
    building real test cases would itself make OpenAI calls (via RAGPipeline.answer),
    so this returns a single explicitly-skipped placeholder instead -- keeps `pytest -v`
    showing a clear skip reason rather than silently collecting zero tests.
    """
    if not openai_available():
        return [
            pytest.param(
                None,
                id="skipped-no-openai-key",
                marks=pytest.mark.skip(
                    reason="OPENAI_API_KEY not set -- export it to run the RAG pipeline "
                    "and DeepEval's LLM judge"
                ),
            )
        ]
    return [
        pytest.param(tc, id=tc.input[:60]) for tc in build_test_cases()
    ]


@pytest.mark.parametrize("test_case", _collect_test_cases())
def test_rag_quality(test_case: LLMTestCase):
    assert_test(
        test_case,
        [
            FaithfulnessMetric(threshold=FAITHFULNESS_THRESHOLD, model=DEEPEVAL_MODEL),
            AnswerRelevancyMetric(threshold=ANSWER_RELEVANCY_THRESHOLD, model=DEEPEVAL_MODEL),
            ContextualRecallMetric(threshold=CONTEXT_RECALL_THRESHOLD, model=DEEPEVAL_MODEL),
        ],
    )
