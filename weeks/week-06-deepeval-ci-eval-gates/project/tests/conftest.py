"""`requires_openai`: skips cleanly if OPENAI_API_KEY isn't set -- same pattern Week 5
and Week 1c use. Tests behind this marker make real (small, deliberately minimal)
OpenAI + DeepEval-judge API calls and cost real money.
"""

import pytest

from app.llm import openai_available

requires_openai = pytest.mark.skipif(
    not openai_available(),
    reason="OPENAI_API_KEY not set -- export it to run the pipeline and DeepEval's LLM judge",
)
