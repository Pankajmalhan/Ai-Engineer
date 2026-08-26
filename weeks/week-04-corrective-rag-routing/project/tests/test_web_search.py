import pytest

import app.web_search as web_search_mod
from app.web_search import LocalFallbackSearch, TavilySearch, WebSearchResult


def test_local_fallback_search_ranks_by_term_overlap():
    search = LocalFallbackSearch()
    results = search.search("ColBERT late interaction MaxSim")
    assert results[0].title.startswith("ColBERT")


def test_local_fallback_search_respects_max_results():
    search = LocalFallbackSearch()
    results = search.search("retrieval", max_results=1)
    assert len(results) == 1


def test_local_fallback_search_with_custom_snapshot():
    snapshot = [WebSearchResult(title="A", url="http://a", content="alpha beta")]
    search = LocalFallbackSearch(snapshot=snapshot)
    results = search.search("alpha")
    assert results[0].title == "A"


def test_tavily_search_refuses_to_construct_without_api_key(monkeypatch):
    monkeypatch.setattr(web_search_mod, "TAVILY_API_KEY", None)
    with pytest.raises(RuntimeError, match="TAVILY_API_KEY"):
        TavilySearch()
