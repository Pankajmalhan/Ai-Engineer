"""Wires the router, the pgvector-backed hybrid retriever, and Corrective RAG into
one path.

    query -> router.route()
             CONVERSATIONAL -> answer directly, no retrieval, no CRAG
             FACTUAL         -> hybrid_search(collection="docs") -> CorrectiveRAG
             CODE            -> hybrid_search(collection="code", bm25-weighted) -> CorrectiveRAG
"""

from __future__ import annotations

from dataclasses import dataclass

from app.answerer import Answerer, ExtractiveAnswerer
from app.crag import CorrectiveRAG, CragResult
from app.data import CODE_COLLECTION, DOCS_COLLECTION, seed_demo_data
from app.grader import Grader, HeuristicGrader
from app.query_rewriter import HeuristicRewriter, QueryRewriter
from app.refiner import HeuristicRefiner, Refiner
from app.retrieval import hybrid_search
from app.router import RouteDecision, Router, SemanticRouter, Strategy
from app.vectorstore import PGVectorStore
from app.web_search import LocalFallbackSearch, WebSearch

CONVERSATIONAL_NOTE = (
    "(conversational query -- no retrieval needed; would be answered directly by "
    "the base LLM's chat behavior, not by this pipeline's CRAG path)"
)


@dataclass
class PipelineResult:
    strategy: Strategy
    route: RouteDecision
    crag_result: CragResult | None  # None for CONVERSATIONAL
    answer: str


class QueryPipeline:
    def __init__(
        self,
        router: Router | None = None,
        store: PGVectorStore | None = None,
        grader: Grader | None = None,
        refiner: Refiner | None = None,
        rewriter: QueryRewriter | None = None,
        web_search: WebSearch | None = None,
        answerer: Answerer | None = None,
        seed: bool = True,
    ):
        self.router = router or SemanticRouter()
        self.store = store or PGVectorStore()
        if seed:
            seed_demo_data(self.store)
        self.grader = grader or HeuristicGrader()
        self.refiner = refiner or HeuristicRefiner()
        self.rewriter = rewriter or HeuristicRewriter()
        self.web_search = web_search or LocalFallbackSearch()
        self.answerer = answerer or ExtractiveAnswerer()

    def handle(self, query: str) -> PipelineResult:
        route = self.router.route(query)

        if route.strategy == Strategy.CONVERSATIONAL:
            return PipelineResult(
                strategy=route.strategy, route=route, crag_result=None, answer=CONVERSATIONAL_NOTE
            )

        if route.strategy == Strategy.CODE:
            # Code queries hinge on exact identifiers/error strings matching
            # lexically more than on semantic similarity -- weight BM25 over dense.
            collection, bm25_weight, dense_weight = CODE_COLLECTION, 2.0, 1.0
        else:
            collection, bm25_weight, dense_weight = DOCS_COLLECTION, 1.0, 1.0

        retrieve_fn = lambda q: hybrid_search(  # noqa: E731
            q, self.store, collection, bm25_weight=bm25_weight, dense_weight=dense_weight
        )

        crag = CorrectiveRAG(
            retrieve_fn, self.grader, self.refiner, self.rewriter, self.web_search, self.answerer
        )
        result = crag.run(query)
        return PipelineResult(strategy=route.strategy, route=route, crag_result=result, answer=result.answer)
