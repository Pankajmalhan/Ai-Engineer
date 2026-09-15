import os

# --- OpenAI ----------------------------------------------------------------------------
# The roadmap task names GPT-4o explicitly; this defaults to the mini variant to keep a
# full 50-sample x 6-metric run cheap (Faithfulness alone issues multiple judge calls per
# sample). Override with OPENAI_MODEL=gpt-4o to match the task literally.
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_EMBEDDING_MODEL = os.environ.get("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")

# --- Retrieval ---------------------------------------------------------------------------
RETRIEVAL_TOP_K = int(os.environ.get("RETRIEVAL_TOP_K", "3"))

# --- Dataset -------------------------------------------------------------------------------
HAND_LABELED_COUNT = 10
SYNTHETIC_COUNT = 40
TOTAL_SAMPLE_COUNT = HAND_LABELED_COUNT + SYNTHETIC_COUNT  # 50, per the task

# --- W&B -----------------------------------------------------------------------------------
WANDB_PROJECT = os.environ.get("WANDB_PROJECT", "week5-ragas-evaluation")
WANDB_MODE = os.environ.get("WANDB_MODE", "offline")
