"""Near-duplicate detection via MinHash LSH (datasketch): approximate Jaccard
similarity over word-level shingles, without the O(n^2) cost of comparing every
document pair directly -- LSH buckets similar MinHash signatures together so a query
only checks a small candidate set, not the whole corpus.
"""

from __future__ import annotations

import re

from datasketch import MinHash, MinHashLSH

from app.config import DEDUP_JACCARD_THRESHOLD, MINHASH_NUM_PERM, MINHASH_SHINGLE_SIZE
from app.models import DuplicatePair, ProcessedDocument

_WORD_RE = re.compile(r"\w+")


def _shingles(text: str, k: int) -> set[str]:
    words = _WORD_RE.findall(text.lower())
    if len(words) < k:
        return {" ".join(words)} if words else set()
    return {" ".join(words[i : i + k]) for i in range(len(words) - k + 1)}


def _minhash(text: str, num_perm: int, shingle_size: int) -> MinHash:
    mh = MinHash(num_perm=num_perm)
    for shingle in _shingles(text, shingle_size):
        mh.update(shingle.encode("utf-8"))
    return mh


def find_near_duplicates(
    documents: list[ProcessedDocument],
    threshold: float = DEDUP_JACCARD_THRESHOLD,
    num_perm: int = MINHASH_NUM_PERM,
    shingle_size: int = MINHASH_SHINGLE_SIZE,
) -> tuple[list[ProcessedDocument], list[DuplicatePair]]:
    """Drops all but the first-seen copy of each near-duplicate cluster (Jaccard >=
    threshold against an already-kept document). Order-preserving: whichever document
    appears first in `documents` is the one kept. Returns (unique_documents,
    duplicate_pairs) for logging/inspection.
    """
    lsh = MinHashLSH(threshold=threshold, num_perm=num_perm)
    minhashes: dict[str, MinHash] = {}
    kept: list[ProcessedDocument] = []
    dropped_pairs: list[DuplicatePair] = []

    for doc in documents:
        mh = _minhash(doc.text, num_perm, shingle_size)
        candidates = lsh.query(mh)
        if candidates:
            # LSH's candidate set is recall-biased (may include false positives at
            # the band/row parameters datasketch derives from threshold) -- confirm
            # with the MinHash-estimated exact Jaccard before actually dropping.
            best_id, best_score = None, 0.0
            for candidate_id in candidates:
                score = mh.jaccard(minhashes[candidate_id])
                if score > best_score:
                    best_id, best_score = candidate_id, score
            if best_score >= threshold:
                dropped_pairs.append(DuplicatePair(kept_id=best_id, dropped_id=doc.id, jaccard=best_score))
                continue
        lsh.insert(doc.id, mh)
        minhashes[doc.id] = mh
        kept.append(doc)

    return kept, dropped_pairs


def dedup_rate(total: int, dropped: int) -> float:
    return dropped / total if total else 0.0
