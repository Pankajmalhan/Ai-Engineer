"""Integration tests against a live ParadeDB instance -- start it first with
`docker compose up -d` (see project/README.md). These are the tests that
actually demonstrate the two failure modes from concept.md, not just assert
the fusion math."""

from llama_index.core.schema import QueryBundle

from app import db
from app.embeddings import embed_query
from app.retriever import HybridRRFRetriever

SEMANTIC_QUERY = "app won't start after reboot"
SEMANTIC_TARGET_TITLE = "desktop-client-boot-failure"

EXACT_QUERY = "ERRCONNTIMEOUT502"
EXACT_TARGET_TITLE = "ticket-88231-conn-timeout"


def test_dense_finds_the_semantic_paraphrase_match(conn, title_to_id):
    target_id = title_to_id[SEMANTIC_TARGET_TITLE]
    vec = embed_query(SEMANTIC_QUERY)

    rows = db.dense_search(conn, vec, 10)

    assert target_id in [row[0] for row in rows]


def test_sparse_misses_the_semantic_paraphrase_match(conn, title_to_id):
    """This is the vocabulary-mismatch failure from concept.md: the query and the
    document share zero literal tokens, so BM25 has nothing to score."""
    target_id = title_to_id[SEMANTIC_TARGET_TITLE]

    rows = db.sparse_search(conn, SEMANTIC_QUERY, 10)

    assert target_id not in [row[0] for row in rows]


def test_sparse_finds_the_exact_token_match(conn, title_to_id):
    target_id = title_to_id[EXACT_TARGET_TITLE]

    rows = db.sparse_search(conn, EXACT_QUERY, 10)

    assert target_id in [row[0] for row in rows]


def test_hybrid_recovers_the_exact_token_match(conn, title_to_id):
    target_id = title_to_id[EXACT_TARGET_TITLE]
    retriever = HybridRRFRetriever(conn, top_k=10)

    nodes = retriever.retrieve(QueryBundle(query_str=EXACT_QUERY))

    assert target_id in [int(n.node.id_) for n in nodes]


def test_hybrid_still_finds_the_semantic_paraphrase_match(conn, title_to_id):
    """Fusing in a sparse ranked list shouldn't cost dense retrieval anything it
    already had -- hybrid must not regress a query dense-only already won."""
    target_id = title_to_id[SEMANTIC_TARGET_TITLE]
    retriever = HybridRRFRetriever(conn, top_k=10)

    nodes = retriever.retrieve(QueryBundle(query_str=SEMANTIC_QUERY))

    assert target_id in [int(n.node.id_) for n in nodes]
