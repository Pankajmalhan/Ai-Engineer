import os

from dotenv import load_dotenv

# Loaded explicitly (rather than relying on `uv run --env-file`) so
# `cp .env.example .env` + editing COHERE_API_KEY in it just works the same
# way regardless of how the scripts below get invoked.
load_dotenv()

# Separate port/db/volume from Week 1's ParadeDB container so both weeks can
# run side by side without colliding.
DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://rerank:rerank@localhost:5434/rerank_bench"
)
EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5")
EMBEDDING_DIM = int(os.environ.get("EMBEDDING_DIM", "384"))
RRF_K = int(os.environ.get("RRF_K", "60"))

# Stage 1 (bi-encoder / hybrid RRF): how many candidates each of dense and
# sparse search contributes before fusion.
CANDIDATE_POOL_SIZE = 50

# Stage 1 output / Stage 2 (cross-encoder rerank) input: the fused hybrid
# ranking is truncated to this many candidates before any reranker sees them.
# Must be > FINAL_TOP_K or reranking has nothing left to reorder.
RERANK_POOL_SIZE = int(os.environ.get("RERANK_POOL_SIZE", "25"))

# Stage 2 output: final result list size, and what NDCG@10 is measured over.
FINAL_TOP_K = int(os.environ.get("FINAL_TOP_K", "10"))

COHERE_API_KEY = os.environ.get("COHERE_API_KEY")
COHERE_RERANK_MODEL = os.environ.get("COHERE_RERANK_MODEL", "rerank-v3.5")

# Trial keys are capped at 10 calls/minute (see
# https://dashboard.cohere.com/api-keys). Default paces just under that so a
# full benchmark run doesn't burst through the quota and start 429ing
# partway through. Raise this (e.g. to match a production key's limit) once
# you're no longer on a trial key.
COHERE_RATE_LIMIT_PER_MIN = int(os.environ.get("COHERE_RATE_LIMIT_PER_MIN", "9"))

BGE_RERANKER_MODEL = os.environ.get("BGE_RERANKER_MODEL", "BAAI/bge-reranker-base")
