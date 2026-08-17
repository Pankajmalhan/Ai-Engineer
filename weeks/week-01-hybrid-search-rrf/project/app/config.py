import os


DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://hybrid:hybrid@localhost:5433/hybrid_search"
)
EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5")
EMBEDDING_DIM = int(os.environ.get("EMBEDDING_DIM", "384"))
RRF_K = int(os.environ.get("RRF_K", "60"))
