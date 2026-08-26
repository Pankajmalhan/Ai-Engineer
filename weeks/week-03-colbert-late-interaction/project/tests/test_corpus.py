"""app.corpus's fetch/cache logic and the multi-hop query set -- pure,
no real network call (a fake cache file stands in for a live fetch)."""

import json

from app import corpus


def test_load_corpus_reads_from_cache_without_network(tmp_path, monkeypatch):
    fake_cache = {title: f"fake content for {title}" for title in corpus.MULTIHOP_TITLES[:3]}
    cache_path = tmp_path / "wikipedia_cache.json"
    cache_path.write_text(json.dumps(fake_cache))

    monkeypatch.setattr(corpus, "DATA_DIR", tmp_path)
    monkeypatch.setattr(corpus, "CACHE_PATH", cache_path)
    monkeypatch.setattr(corpus, "MULTIHOP_TITLES", corpus.MULTIHOP_TITLES[:3])
    monkeypatch.setattr(corpus, "DISTRACTOR_TITLES", [])

    def _network_call_not_allowed(title):
        raise AssertionError(f"should not fetch {title!r} -- it's already cached")

    monkeypatch.setattr(corpus, "_fetch_article", _network_call_not_allowed)

    titles, texts, ids = corpus.load_corpus(article_limit=3)

    assert titles == corpus.MULTIHOP_TITLES
    assert texts == [fake_cache[t] for t in titles]
    assert ids == titles


def test_load_corpus_fetches_and_caches_missing_titles(tmp_path, monkeypatch):
    cache_path = tmp_path / "wikipedia_cache.json"
    monkeypatch.setattr(corpus, "DATA_DIR", tmp_path)
    monkeypatch.setattr(corpus, "CACHE_PATH", cache_path)
    monkeypatch.setattr(corpus, "MULTIHOP_TITLES", ["Fake Title"])
    monkeypatch.setattr(corpus, "DISTRACTOR_TITLES", [])
    monkeypatch.setattr(corpus, "_fetch_article", lambda title: f"fetched: {title}")

    titles, texts, ids = corpus.load_corpus(article_limit=1)

    assert titles == ["Fake Title"]
    assert texts == ["fetched: Fake Title"]
    # the fetch result must have been persisted, not just returned
    assert json.loads(cache_path.read_text()) == {"Fake Title": "fetched: Fake Title"}


def test_load_corpus_skips_titles_with_no_article(tmp_path, monkeypatch):
    monkeypatch.setattr(corpus, "DATA_DIR", tmp_path)
    monkeypatch.setattr(corpus, "CACHE_PATH", tmp_path / "wikipedia_cache.json")
    monkeypatch.setattr(corpus, "MULTIHOP_TITLES", ["Real Title", "Missing Title"])
    monkeypatch.setattr(corpus, "DISTRACTOR_TITLES", [])
    monkeypatch.setattr(
        corpus, "_fetch_article", lambda title: None if title == "Missing Title" else "content"
    )

    titles, texts, ids = corpus.load_corpus(article_limit=2)

    assert titles == ["Real Title"]


def test_article_limit_smaller_than_multihop_cluster_still_keeps_every_multihop_title(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(corpus, "DATA_DIR", tmp_path)
    monkeypatch.setattr(corpus, "CACHE_PATH", tmp_path / "wikipedia_cache.json")
    monkeypatch.setattr(corpus, "_fetch_article", lambda title: f"content for {title}")

    # article_limit deliberately smaller than len(MULTIHOP_TITLES) -- the
    # limit should only ever trim DISTRACTOR_TITLES, never the multi-hop
    # cluster the MULTIHOP_QUERIES test bed depends on.
    small_limit = len(corpus.MULTIHOP_TITLES) - 5
    titles, _texts, _ids = corpus.load_corpus(article_limit=small_limit)

    assert set(corpus.MULTIHOP_TITLES).issubset(set(titles))


def test_multihop_queries_reference_real_multihop_titles():
    multihop_title_set = set(corpus.MULTIHOP_TITLES)
    for q in corpus.MULTIHOP_QUERIES:
        assert q["query"]
        assert q["relevant_titles"], f"no relevant_titles for query: {q['query']}"
        assert set(q["relevant_titles"]).issubset(multihop_title_set), (
            f"query {q['query']!r} references a title not in MULTIHOP_TITLES"
        )
