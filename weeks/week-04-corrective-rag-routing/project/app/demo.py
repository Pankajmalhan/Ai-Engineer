"""Run the whole week-4 pipeline against a handful of sample queries.

    docker compose up -d      # start Postgres + pgvector, once
    uv run python -m app.demo

Uses HeuristicGrader/HeuristicRefiner/HeuristicRewriter/ExtractiveAnswerer +
LocalFallbackSearch by default (no API keys needed) against a real pgvector store. If
ANTHROPIC_API_KEY is set, also re-runs the same queries with the real LLMGrader wired
in, so you can compare the heuristic and LLM-as-judge grading decisions directly.

Also runs CascadingRouter (Tier 1 TF-IDF + Tier 2 LLM escalation, see app/router.py)
against a couple of genuinely ambiguous queries, and reports its escalation rate --
with ANTHROPIC_API_KEY set, watch it actually escalate and write to
router_escalations.jsonl in this directory.
"""

from __future__ import annotations

from app.config import ANTHROPIC_API_KEY
from app.grader import LLMGrader
from app.pipeline import QueryPipeline
from app.router import CascadingRouter, LLMRouteClassifier
from app.vectorstore import is_available

SAMPLE_QUERIES = [
    "What is our refund policy for annual plans?",
    "Why does getUserById() throw a NullPointerException?",
    "Hi, how are you doing today?",
    "What is the wingspan of an albatross?",  # out of domain -> CRAG Incorrect/Ambiguous
]

# A couple of genuinely ambiguous queries, specifically to exercise CascadingRouter's
# escalation path in run_router_cascade_demo() below -- SAMPLE_QUERIES above are all
# ones SemanticRouter is confident about on its own, which wouldn't demonstrate anything.
AMBIGUOUS_QUERIES = [
    "what is 2+2?",
    "zzz qux plonk wibble",
]


def _run(pipeline: QueryPipeline, label: str) -> None:
    print(f"=== {label} ===")
    for query in SAMPLE_QUERIES:
        result = pipeline.handle(query)
        print(f"\nquery: {query!r}")
        print(f"  route: {result.strategy.value} (confidence={result.route.confidence:.2f}, "
              f"fallback_default={result.route.used_default_fallback})")
        if result.crag_result is not None:
            cr = result.crag_result
            print(f"  action: {cr.action.value} (max_relevance={cr.max_relevance:.2f}, "
                  f"mean_relevance={cr.mean_relevance:.2f})")
            if cr.rewritten_query:
                print(f"  rewritten query for web search: {cr.rewritten_query!r}")
            print(f"  refined context: {cr.context}")
        print(f"  answer: {result.answer}")


def run_pipeline_demo() -> None:
    if not is_available():
        print("Postgres/pgvector isn't reachable. Run `docker compose up -d` in this "
              "directory first, then re-run the demo.")
        return

    _run(QueryPipeline(), "Router + CRAG pipeline (HeuristicGrader, offline)")

    if not ANTHROPIC_API_KEY:
        print("\nANTHROPIC_API_KEY not set -- skipping the LLMGrader run. Set it to "
              "see the real LLM-as-judge grader drive the same queries.")
        return

    _run(QueryPipeline(grader=LLMGrader()), "Router + CRAG pipeline (LLMGrader, real LLM)")


def run_router_cascade_demo() -> None:
    print("\n=== CascadingRouter: Tier 1 (TF-IDF) + Tier 2 (LLM escalation) ===")

    llm_classifier = LLMRouteClassifier() if ANTHROPIC_API_KEY else None
    log_path = "router_escalations.jsonl"
    router = CascadingRouter(llm_classifier=llm_classifier, log_path=log_path)

    for query in SAMPLE_QUERIES + AMBIGUOUS_QUERIES:
        decision = router.route(query)
        print(f"\nquery: {query!r}")
        print(f"  strategy: {decision.strategy.value}  confidence: {decision.confidence:.2f}"
              f"  tier1_fallback: {decision.used_default_fallback}"
              f"  escalated_to_llm: {decision.escalated_to_llm}")

    print(f"\nescalation_rate over these {router.total_routed} queries: {router.escalation_rate:.0%}")
    if llm_classifier is None:
        print("ANTHROPIC_API_KEY not set -- no llm_classifier configured, so every "
              "Tier 1 fallback above just used SemanticRouter's own default strategy "
              "instead of actually escalating. Set the key to see real escalation "
              f"and a populated {log_path}.")
    elif router.total_escalated:
        print(f"{router.total_escalated} escalation(s) logged to {log_path} -- review "
              f"them and fold good ones into PROTOTYPES to shrink this rate over time.")


if __name__ == "__main__":
    run_pipeline_demo()
    run_router_cascade_demo()
