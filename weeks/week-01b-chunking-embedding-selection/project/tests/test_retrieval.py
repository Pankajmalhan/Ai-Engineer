"""End-to-end: build a tiny index and confirm a query actually finds its
matching document -- the thing all the benchmark scripts ultimately do at
scale. Uses bge-small (smallest, already-cached model) to stay fast."""

from app.retrieval import build_index, search

MODEL = "BAAI/bge-small-en-v1.5"

DOCS = [
    {
        "id": "doc:cats",
        "doc_type": "text",
        "content": (
            "Cats are independent animals that spend much of the day "
            "sleeping. Domestic cats retain many hunting instincts from "
            "their wild ancestors, including stalking and pouncing on "
            "small moving objects."
        ),
    },
    {
        "id": "doc:http",
        "doc_type": "code",
        "content": (
            "def send_get_request(url):\n"
            "    '''Sends an HTTP GET request and returns the response body.'''\n"
            "    response = http_client.get(url)\n"
            "    return response.text\n"
        ),
    },
]


def test_search_retrieves_the_matching_document_for_fixed_size():
    index = build_index(DOCS, "fixed_size", MODEL)
    results = search(index, ["why do cats stalk small moving things"], MODEL, k=5)
    assert "doc:cats" in results[0]
    assert "doc:http" not in results[0][:1]  # the top hit specifically should be the cat doc


def test_search_retrieves_the_matching_document_for_late_chunking():
    index = build_index(DOCS, "late_chunking", MODEL)
    assert all(v is not None for v in index.vectors.tolist())
    results = search(index, ["a function that makes a GET request over HTTP"], MODEL, k=5)
    assert "doc:http" in results[0]


def test_relevant_chunk_count_matches_doc():
    index = build_index(DOCS, "fixed_size", MODEL)
    assert index.relevant_chunk_count("doc:cats") == sum(
        1 for c in index.chunks if c.doc_id == "doc:cats"
    )
    assert index.relevant_chunk_count("doc:nonexistent") == 0
