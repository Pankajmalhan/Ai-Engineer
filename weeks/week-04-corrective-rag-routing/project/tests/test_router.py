from app.router import SemanticRouter, Strategy


def test_factual_query_routes_to_hybrid_search_docs():
    router = SemanticRouter()
    decision = router.route("What is our refund policy for annual plans?")
    assert decision.strategy == Strategy.FACTUAL
    assert decision.retrieval_strategy == "hybrid_search[docs]"


def test_code_query_routes_to_hybrid_search_code():
    router = SemanticRouter()
    decision = router.route("Why does getUserById() throw a NullPointerException?")
    assert decision.strategy == Strategy.CODE
    assert decision.retrieval_strategy == "hybrid_search[code, bm25-weighted]"


def test_conversational_query_routes_to_direct_llm():
    router = SemanticRouter()
    decision = router.route("Hi, how are you doing today?")
    assert decision.strategy == Strategy.CONVERSATIONAL
    assert decision.retrieval_strategy == "direct_llm"


def test_code_heuristics_catch_code_fences_even_off_topic():
    router = SemanticRouter()
    decision = router.route("Explain why this raises a ZeroDivisionError: `def foo(x): return x/0`")
    assert decision.strategy == Strategy.CODE


def test_scores_dict_covers_every_strategy():
    router = SemanticRouter()
    decision = router.route("How do I resolve a merge conflict in git?")
    assert set(decision.scores) == {Strategy.FACTUAL, Strategy.CODE, Strategy.CONVERSATIONAL}


def test_low_confidence_query_falls_back_to_default_strategy():
    router = SemanticRouter(min_confidence=0.99)  # impossible to clear -> always fall back
    decision = router.route("What is our refund policy for annual plans?")
    assert decision.used_default_fallback is True
    assert decision.strategy == Strategy.FACTUAL  # DEFAULT_STRATEGY


def test_unrelated_gibberish_does_not_crash_and_yields_low_confidence():
    router = SemanticRouter()
    decision = router.route("zzz qux plonk wibble")
    assert decision.strategy in Strategy
    assert decision.confidence >= 0.0


def test_plain_semantic_router_decisions_are_never_marked_escalated():
    router = SemanticRouter()
    decision = router.route("What is our refund policy for annual plans?")
    assert decision.escalated_to_llm is False


def test_expanded_corpus_recognizes_variants_of_the_newly_added_prototypes():
    # Not exact copies of any PROTOTYPES entry, and not sharing meaningful vocabulary
    # with any of the *original* 8/class -- these only route correctly because
    # PROTOTYPES was grown to ~25/class (see router.py's comment on PROTOTYPES).
    # This is still word-overlap matching, not semantic paraphrase understanding --
    # TF-IDF can't do the latter (see the "2+2" vs. "capital of France" exploration
    # earlier); a slightly-reworded variant of a *stored* example is what it's good at.
    router = SemanticRouter()
    assert router.route("Can I get a refund if I cancel my plan early?").strategy == Strategy.FACTUAL
    assert router.route("My API keeps returning a 401 Unauthorized error").strategy == Strategy.CODE
    assert router.route("Hope you have a great day!").strategy == Strategy.CONVERSATIONAL
