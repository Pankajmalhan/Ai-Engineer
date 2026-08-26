"""Real corpus for this week's benchmark: live Wikipedia articles, fetched
through the MediaWiki API and cached to disk so indexing/search runs don't
need the network every time.

Two clusters, deliberately built to exercise the failure mode this week's
concept.md is about:

- MULTIHOP_TITLES: a tightly interconnected set of articles (Studio Ghibli,
  its founders, its films, its composer) that share a lot of surface-level
  vocabulary ("animated film", "Studio Ghibli", "Miyazaki") but differ on
  the *specific* facts a compositional query needs multiple of at once.
  This is what MULTIHOP_QUERIES targets -- questions that need two or more
  distinct facts satisfied simultaneously, which is exactly where a single
  pooled bi-encoder vector blurs together and ColBERT's per-token MaxSim
  should hold up better (see concept.md's "Why it matters in production").
- DISTRACTOR_TITLES: broad, unrelated topics whose only job is to dilute
  the corpus, same purpose as DISTRACTOR_DOCS in Weeks 1-2 -- with only the
  multi-hop cluster indexed, every query would trivially retrieve from a
  tiny same-topic pool and prove nothing about ranking quality.

Each article is split into many passages at index time (RAGatouille's
`split_documents=True`), so a few hundred articles is enough to reach a
multi-thousand-passage index -- see project/README.md for the actual
passage count measured on this corpus, and how to raise ARTICLE_LIMIT to
scale closer to (or past) the 5,000-passage target in the roadmap task.
"""

import json
import os
from pathlib import Path

import requests

DATA_DIR = Path(__file__).parent.parent / "data"
CACHE_PATH = DATA_DIR / "wikipedia_cache.json"

WIKIPEDIA_API = "https://en.wikipedia.org/w/api.php"
USER_AGENT = "ai-engineer-roadmap-week3/0.1 (choudhary.pankaj@tftus.com)"

# How many articles to actually fetch+index. Kept modest by default so a
# full `uv run python -m app.index` run finishes in minutes on a CPU-only
# laptop rather than tens of minutes -- see README for the measured passage
# count and how to raise this toward the roadmap's 5,000-passage target.
ARTICLE_LIMIT = int(os.environ.get("ARTICLE_LIMIT", "60"))

MULTIHOP_TITLES = [
    "Studio Ghibli",
    "Hayao Miyazaki",
    "Isao Takahata",
    "Spirited Away",
    "My Neighbor Totoro",
    "Princess Mononoke",
    "Grave of the Fireflies",
    "Nausicaä of the Valley of the Wind",
    "Castle in the Sky",
    "Kiki's Delivery Service",
    "Ponyo",
    "The Wind Rises",
    "Toshio Suzuki (producer)",
    "Joe Hisaishi",
    "Nippon Television",
]

DISTRACTOR_TITLES = [
    "Great Barrier Reef",
    "Photosynthesis",
    "Byzantine Empire",
    "String theory",
    "Compound interest",
    "Sourdough",
    "Tour de France",
    "Basalt",
    "Marathon",
    "Octopus",
    "Concert hall",
    "Beekeeping",
    "Chess opening",
    "Sea turtle",
    "Volcanic soil",
    "Espresso",
    "Rowing (sport)",
    "Lighthouse",
    "Fermentation in food processing",
    "Pedestrian bridge",
    "Bird migration",
    "Cast-iron cookware",
    "Vineyard",
    "Observatory",
    "Trans-Siberian Railway",
    "Great Wall of China",
    "Amazon rainforest",
    "Sahara",
    "Great Pyramid of Giza",
    "Louvre",
    "Great Depression",
    "Industrial Revolution",
    "Renaissance",
    "Quantum computing",
    "Machine learning",
    "Blockchain",
    "Solar panel",
    "Electric vehicle",
    "International Space Station",
    "Mount Everest",
    "Antarctica",
    "Coral reef",
    "Rainforest",
    "Volcano",
    "Earthquake",
    "Tsunami",
]

MULTIHOP_QUERIES = [
    {
        "query": "What company did the director of Spirited Away found, and who else co-founded it?",
        "relevant_titles": ["Studio Ghibli", "Hayao Miyazaki", "Isao Takahata"],
        "note": "Needs 'Spirited Away -> Miyazaki' AND 'Miyazaki + Takahata -> founded Studio Ghibli' at once.",
    },
    {
        "query": "Who composed the music for the Studio Ghibli film about a girl who becomes a witch and delivers packages?",
        "relevant_titles": ["Kiki's Delivery Service", "Joe Hisaishi"],
        "note": "Needs the film identified from a paraphrased plot AND its composer, not just 'Ghibli + music'.",
    },
    {
        "query": "Which Studio Ghibli director also made a film about two siblings during the World War II firebombing of Japan?",
        "relevant_titles": ["Grave of the Fireflies", "Isao Takahata"],
        "note": "Distinguishes Takahata from Miyazaki -- both are 'a Ghibli director', only one made this specific film.",
    },
    {
        "query": "What was the Japanese TV network connection for the studio behind My Neighbor Totoro?",
        "relevant_titles": ["Studio Ghibli", "Nippon Television", "My Neighbor Totoro"],
        "note": "Requires chaining film -> studio -> the studio's TV network relationship, not just topic overlap.",
    },
    {
        "query": "Name a Miyazaki film about a flying fortress in the sky and the producer who worked on Ghibli films with him.",
        "relevant_titles": ["Castle in the Sky", "Toshio Suzuki (producer)"],
        "note": "Two independent facts (a specific film's plot + a specific producer) that must both be satisfied.",
    },
]


def _fetch_article(title: str) -> str | None:
    response = requests.get(
        WIKIPEDIA_API,
        params={
            "action": "query",
            "format": "json",
            "titles": title,
            "prop": "extracts",
            "explaintext": True,
        },
        headers={"User-Agent": USER_AGENT},
        timeout=30,
    )
    response.raise_for_status()
    page = next(iter(response.json()["query"]["pages"].values()))
    return page.get("extract") or None


def load_corpus(
    article_limit: int = ARTICLE_LIMIT,
) -> tuple[list[str], list[str], list[str]]:
    """Returns (titles, texts, ids) for MULTIHOP_TITLES followed by as many
    DISTRACTOR_TITLES as fit under article_limit. Cached to disk after the
    first fetch -- subsequent runs (including tests) don't hit the network.
    """
    all_titles = MULTIHOP_TITLES + DISTRACTOR_TITLES[: max(0, article_limit - len(MULTIHOP_TITLES))]

    cache: dict[str, str] = {}
    if CACHE_PATH.exists():
        cache = json.loads(CACHE_PATH.read_text())

    changed = False
    for title in all_titles:
        if title not in cache:
            text = _fetch_article(title)
            if text:
                cache[title] = text
                changed = True

    if changed:
        DATA_DIR.mkdir(exist_ok=True)
        CACHE_PATH.write_text(json.dumps(cache, indent=2))

    titles = [t for t in all_titles if t in cache]
    texts = [cache[t] for t in titles]
    ids = titles  # titles are unique here, so they double as document ids
    return titles, texts, ids
