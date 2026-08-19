"""Integration tests against a live ParadeDB instance -- start it first with
`docker compose up -d` (see project/README.md). These check Stage 1
(retriever.hybrid_candidates) end to end, and that Stage 2 (BGEReranker) can
actually reorder a real Stage 1 pool rather than just pass it through."""

from app.rerankers import BGEReranker
from app.retriever import hybrid_candidates

EXACT_QUERY = "ERRCONNTIMEOUT502"
EXACT_TARGET_TITLE = "ticket-88231-conn-timeout"


def test_hybrid_candidates_returns_a_ranked_pool_containing_the_known_match(
    conn, title_to_id
):
    target_id = title_to_id[EXACT_TARGET_TITLE]

    candidates = hybrid_candidates(conn, EXACT_QUERY, pool_size=25)

    assert len(candidates) == 25
    assert target_id in [doc_id for doc_id, _title, _content in candidates]


def test_bge_reranker_can_reorder_a_real_stage1_pool(conn, title_to_id):
    target_id = title_to_id[EXACT_TARGET_TITLE]
    candidates = hybrid_candidates(conn, EXACT_QUERY, pool_size=25)
    reranker = BGEReranker()

    results = reranker.rerank(EXACT_QUERY, candidates, top_n=10)

    assert target_id in [r.doc_id for r in results]
