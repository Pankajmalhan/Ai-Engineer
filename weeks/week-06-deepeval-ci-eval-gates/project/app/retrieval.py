"""BM25 retrieval over the fixed corpus -- local/no-API, same as Week 5, so the
retrieval half of the pipeline costs nothing to run repeatedly on every push.
"""

from __future__ import annotations

import re

from rank_bm25 import BM25Okapi

from app.config import BREAK_RETRIEVAL
from app.corpus import CORPUS, Document


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


class BM25Retriever:
    def __init__(self, documents: list[Document] | None = None, break_retrieval: bool = BREAK_RETRIEVAL):
        self.documents = documents if documents is not None else CORPUS
        self._bm25 = BM25Okapi([_tokenize(d.text) for d in self.documents])
        # This week's "deliberately bad change": when on, retrieval returns the LEAST
        # relevant chunks instead of the most relevant ones -- a stand-in for a real
        # regression (wrong index, broken reranker, swapped embedding model, ...) that
        # the eval gate should catch. See app/config.py's BREAK_RETRIEVAL.
        self._break_retrieval = break_retrieval

    def retrieve(self, query: str, k: int) -> list[str]:
        scores = self._bm25.get_scores(_tokenize(query))
        ranked = sorted(
            range(len(self.documents)), key=lambda i: scores[i], reverse=not self._break_retrieval
        )
        return [self.documents[i].text for i in ranked[:k]]
