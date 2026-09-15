"""`requires_openai`: skips cleanly if OPENAI_API_KEY isn't set -- same
skip-don't-fail pattern week 1c uses for Postgres/Presidio. Tests behind this marker
make real (small, deliberately minimal-sample) OpenAI API calls and cost real money.
"""

import pytest

from app.llm import openai_available

requires_openai = pytest.mark.skipif(
    not openai_available(),
    reason="OPENAI_API_KEY not set -- export it to run tests that call OpenAI/RAGAS's LLM judge",
)
