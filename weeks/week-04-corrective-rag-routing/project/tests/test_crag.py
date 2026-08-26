from app.crag import CorrectiveRAG, CragAction
from app.grader import RelevanceScore
from app.models import RetrievedChunk
from app.refiner import HeuristicRefiner
from app.web_search import WebSearchResult


class FixedScoreGrader:
    """Deterministic grader for testing CRAG's branching, independent of any real
    scoring logic -- grades every chunk with a score keyed by its text."""

    def __init__(self, scores_by_text: dict[str, float]):
        self.scores_by_text = scores_by_text

    def grade(self, query: str, chunk: str) -> RelevanceScore:
        return RelevanceScore(relevance=self.scores_by_text.get(chunk, 0.0), reasoning="fixed")


class FakeRewriter:
    def __init__(self):
        self.calls = []

    def rewrite(self, query: str) -> str:
        self.calls.append(query)
        return f"rewritten:{query}"


class FakeRefiner:
    def __init__(self):
        self.calls = []

    def refine(self, query: str, texts: list[str]) -> list[str]:
        self.calls.append((query, list(texts)))
        return [f"refined:{t}" for t in texts]


class FakeAnswerer:
    def __init__(self):
        self.calls = []

    def answer(self, query: str, context: list[str]) -> str:
        self.calls.append((query, list(context)))
        return f"answer for {query} from {len(context)} bullets"


class FakeWebSearch:
    def __init__(self):
        self.calls = []

    def search(self, query: str, max_results: int = 3):
        self.calls.append(query)
        return [WebSearchResult(title="fallback", url="http://example.com", content="web result")]


def _retrieve_fn(chunks):
    return lambda query: chunks


def _crag(chunks, scores_by_text, **kwargs):
    grader = FixedScoreGrader(scores_by_text)
    refiner = kwargs.pop("refiner", None) or FakeRefiner()
    rewriter = kwargs.pop("rewriter", None) or FakeRewriter()
    web_search = kwargs.pop("web_search", None) or FakeWebSearch()
    answerer = kwargs.pop("answerer", None) or FakeAnswerer()
    crag = CorrectiveRAG(_retrieve_fn(chunks), grader, refiner, rewriter, web_search, answerer, **kwargs)
    return crag, refiner, rewriter, web_search, answerer


def test_high_max_relevance_is_correct_and_skips_web_search():
    chunks = [RetrievedChunk(id="1", text="great chunk", score=1.0)]
    crag, refiner, rewriter, web_search, answerer = _crag(chunks, {"great chunk": 0.9})

    result = crag.run("some query")

    assert result.action == CragAction.CORRECT
    assert result.max_relevance == 0.9
    assert web_search.calls == []
    assert rewriter.calls == []
    assert refiner.calls == [("some query", ["great chunk"])]
    assert result.context == ["refined:great chunk"]
    assert answerer.calls == [("some query", ["refined:great chunk"])]
    assert result.answer == "answer for some query from 1 bullets"


def test_low_max_relevance_is_incorrect_and_rewrites_query_for_web_search():
    chunks = [RetrievedChunk(id="1", text="irrelevant chunk", score=0.9)]
    crag, refiner, rewriter, web_search, answerer = _crag(chunks, {"irrelevant chunk": 0.1})

    result = crag.run("some query")

    assert result.action == CragAction.INCORRECT
    assert rewriter.calls == ["some query"]
    assert web_search.calls == ["rewritten:some query"]  # rewritten, not raw
    assert result.rewritten_query == "rewritten:some query"
    assert refiner.calls == [("some query", ["web result"])]  # retrieval discarded entirely
    assert result.context == ["refined:web result"]


def test_mid_max_relevance_is_ambiguous_and_combines_retrieval_and_web():
    chunks = [RetrievedChunk(id="1", text="okay chunk", score=0.9)]
    crag, refiner, rewriter, web_search, answerer = _crag(chunks, {"okay chunk": 0.5})

    result = crag.run("some query")

    assert result.action == CragAction.AMBIGUOUS
    assert web_search.calls == ["rewritten:some query"]
    assert refiner.calls == [("some query", ["okay chunk", "web result"])]  # both combined


def test_boundary_scores_are_correct_not_ambiguous():
    # max_relevance > upper_threshold (strictly) is Correct; exactly at the
    # threshold falls into Ambiguous.
    chunks = [RetrievedChunk(id="1", text="c", score=1.0)]
    crag, *_ = _crag(chunks, {"c": 0.71}, upper_threshold=0.7, lower_threshold=0.3)
    assert crag.run("q").action == CragAction.CORRECT

    crag, *_ = _crag(chunks, {"c": 0.7}, upper_threshold=0.7, lower_threshold=0.3)
    assert crag.run("q").action == CragAction.AMBIGUOUS

    crag, *_ = _crag(chunks, {"c": 0.3}, upper_threshold=0.7, lower_threshold=0.3)
    assert crag.run("q").action == CragAction.AMBIGUOUS

    crag, *_ = _crag(chunks, {"c": 0.29}, upper_threshold=0.7, lower_threshold=0.3)
    assert crag.run("q").action == CragAction.INCORRECT


def test_no_retrieved_chunks_is_incorrect_and_escalates():
    crag, refiner, rewriter, web_search, answerer = _crag([], {})
    result = crag.run("q")
    assert result.action == CragAction.INCORRECT
    assert result.max_relevance == 0.0
    assert web_search.calls == ["rewritten:q"]


def test_end_to_end_with_real_heuristic_refiner():
    """Same scenario as the high-relevance test, but with the real HeuristicRefiner
    instead of a spy, to check the pieces actually compose correctly."""
    chunks = [
        RetrievedChunk(id="1", text="Our refund policy allows full refunds within 30 days.", score=1.0),
    ]
    grader = FixedScoreGrader({"Our refund policy allows full refunds within 30 days.": 0.9})
    crag = CorrectiveRAG(
        _retrieve_fn(chunks), grader, HeuristicRefiner(), FakeRewriter(), FakeWebSearch(), FakeAnswerer(),
    )
    result = crag.run("What is our refund policy?")
    assert result.action == CragAction.CORRECT
    assert any("refund" in c.lower() for c in result.context)
