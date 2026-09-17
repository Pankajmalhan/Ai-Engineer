import os

# --- OpenAI ----------------------------------------------------------------------------
# Two separate model knobs: one for the pipeline's own generation, one for DeepEval's
# judge. The roadmap task names GPT-4o explicitly as the judge; this defaults both to
# the mini variant to keep a push-triggered CI gate cheap and fast (Faithfulness alone
# issues multiple judge calls per test case, x3 metrics x however many goldens, on every
# push). Set DEEPEVAL_MODEL=gpt-4o to match the task literally.
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
DEEPEVAL_MODEL = os.environ.get("DEEPEVAL_MODEL", "gpt-4o-mini")

# --- Retrieval ---------------------------------------------------------------------------
RETRIEVAL_TOP_K = int(os.environ.get("RETRIEVAL_TOP_K", "3"))

# Deliberately breaks retrieval by returning the LEAST relevant chunks instead of the
# most relevant ones -- the "push a deliberately bad change" step from this week's task.
# Toggle locally (BREAK_RETRIEVAL=1 uv run pytest) to watch the eval gate catch it, or
# flip it in a throwaway branch/commit to watch the GitHub Actions workflow fail.
BREAK_RETRIEVAL = os.environ.get("BREAK_RETRIEVAL", "0") == "1"

# --- Eval thresholds -----------------------------------------------------------------------
# The exact numbers this week's task specifies -- kept here, not hardcoded in the test
# file, so tuning a threshold is a one-line config change, not a test-code edit.
FAITHFULNESS_THRESHOLD = float(os.environ.get("FAITHFULNESS_THRESHOLD", "0.8"))
ANSWER_RELEVANCY_THRESHOLD = float(os.environ.get("ANSWER_RELEVANCY_THRESHOLD", "0.75"))
CONTEXT_RECALL_THRESHOLD = float(os.environ.get("CONTEXT_RECALL_THRESHOLD", "0.7"))

# --- W&B -----------------------------------------------------------------------------------
WANDB_PROJECT = os.environ.get("WANDB_PROJECT", "week6-deepeval-ci-gates")
WANDB_MODE = os.environ.get("WANDB_MODE", "offline")
