"""BM25 retrieval over the fixed corpus -- deliberately local/no-API so the retrieval
half of the pipeline costs nothing to run repeatedly; only generation and RAGAS's LLM
judge calls hit OpenAI.
"""

from __future__ import annotations

import re

from rank_bm25 import BM25Okapi

from app.corpus import CORPUS, Document


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


class BM25Retriever:
    def __init__(self, documents: list[Document] | None = None):
        self.documents = documents if documents is not None else CORPUS
        self._bm25 = BM25Okapi([_tokenize(d.text) for d in self.documents])

    def retrieve(self, query: str, k: int) -> list[str]:
        scores = self._bm25.get_scores(_tokenize(query))
        ranked = sorted(range(len(self.documents)), key=lambda i: scores[i], reverse=True)
        return [self.documents[i].text for i in ranked[:k]]
