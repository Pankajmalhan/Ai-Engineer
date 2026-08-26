import os

COLBERT_CHECKPOINT = os.environ.get("COLBERT_CHECKPOINT", "colbert-ir/colbertv2.0")
INDEX_NAME = os.environ.get("INDEX_NAME", "week3_wikipedia")

# Bi-encoder used as the single-vector baseline `app/compare.py` measures
# ColBERT against. Same family/size class as Week 1's embedding model so
# the comparison isn't confounded by "bigger model wins."
BIENCODER_MODEL = os.environ.get("BIENCODER_MODEL", "BAAI/bge-small-en-v1.5")

# How many passages each side returns per query.
TOP_K = int(os.environ.get("TOP_K", "5"))
