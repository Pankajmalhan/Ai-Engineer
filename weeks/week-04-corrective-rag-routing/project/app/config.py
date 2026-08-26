import os

# --- LLM-as-judge grader backend -------------------------------------------------
# Real grading calls go through Instructor + Anthropic (LLMGrader), same as
# LLMRewriter/LLMRefiner/LLMAnswerer. Unset -> all four refuse to construct and
# callers should fall back to their offline/heuristic counterparts.
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-5-20250929")

# --- Web search fallback -----------------------------------------------------------
# Unset -> app/web_search.py's TavilySearch refuses to construct; callers should
# fall back to LocalFallbackSearch (a small static offline snapshot, not real search).
TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY")

# --- CRAG ----------------------------------------------------------------------------
# Dual thresholds on the *best* retrieved chunk's relevance score, matching the CRAG
# paper's Correct / Incorrect / Ambiguous split (see concept.md's "Deciding and
# acting" section):
#   max_relevance > UPPER        -> Correct    (refine retrieval, skip web search)
#   max_relevance < LOWER        -> Incorrect  (discard retrieval, web search only)
#   LOWER <= max_relevance <= UPPER -> Ambiguous (refine retrieval + web search, combined)
RELEVANCE_UPPER_THRESHOLD = float(os.environ.get("RELEVANCE_UPPER_THRESHOLD", "0.7"))
RELEVANCE_LOWER_THRESHOLD = float(os.environ.get("RELEVANCE_LOWER_THRESHOLD", "0.3"))

# --- Vector store --------------------------------------------------------------------
# Postgres + pgvector, started via `docker compose up -d` (see docker-compose.yml).
DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://week4:week4@localhost:5433/week4_rag"
)

# --- Router ----------------------------------------------------------------------------
# Below this top-class confidence, the router refuses to guess and falls back to the
# safest general-purpose strategy (hybrid search over FACTUAL) rather than picking
# whichever class happened to score highest by a hair.
ROUTER_MIN_CONFIDENCE = float(os.environ.get("ROUTER_MIN_CONFIDENCE", "0.15"))

TOP_K = int(os.environ.get("TOP_K", "3"))
