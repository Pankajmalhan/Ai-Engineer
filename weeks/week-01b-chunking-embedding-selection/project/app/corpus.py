"""Loads the built corpus (data/corpus.jsonl, see build_corpus.py) and
defines the 20-query evaluation set.

Ground truth for every query below was verified by hand against the actual
downloaded/cloned source -- not guessed. Text queries paraphrase (different
wording, no literal title overlap) a real Sherlock Holmes story's plot; code
queries paraphrase what a real, specific function/class in one of the cloned
repos actually does, checked against its real docstring in build_corpus.py's
source tree before being written here.
"""

import json
from pathlib import Path

CORPUS_PATH = Path(__file__).parent.parent / "data" / "corpus.jsonl"


def load_documents() -> list[dict]:
    with CORPUS_PATH.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f]


# --- text queries: each maps to one of the 10 Sherlock Holmes stories in the
# corpus, paraphrased away from the story's own title/wording. ---
TEXT_QUERIES = [
    (
        "a detective is hired by a European royal to recover a photograph a "
        "clever woman is using to protect herself before his wedding",
        "text:the-adventures-of-sherlock-holmes:I",
    ),
    (
        "a shop owner's assistant takes a strange well-paid job copying an "
        "encyclopedia because of his hair color, which turns out to be a "
        "distraction for a bank robbery",
        "text:the-adventures-of-sherlock-holmes:II",
    ),
    (
        "a young man is the prime suspect in his father's murder near a "
        "pool of water, but the real culprit is someone from the father's "
        "hidden past",
        "text:the-adventures-of-sherlock-holmes:IV",
    ),
    (
        "a client receives a mysterious set of dried seeds in an envelope "
        "shortly before dying, connected to a secret American organization",
        "text:the-adventures-of-sherlock-holmes:V",
    ),
    (
        "a missing husband turns out to be secretly living a double life "
        "as a street beggar in disguise for the money",
        "text:the-adventures-of-sherlock-holmes:VI",
    ),
    (
        "a valuable stolen gemstone is discovered hidden inside a holiday "
        "dinner bird",
        "text:the-adventures-of-sherlock-holmes:VII",
    ),
    (
        "a young woman is terrified she'll be killed before her wedding "
        "just like her sister was, and the murder weapon turns out to be a "
        "venomous snake trained to kill",
        "text:the-adventures-of-sherlock-holmes:VIII",
    ),
    (
        "a newlywed bride disappears right after her own wedding ceremony "
        "because of a marriage she had kept secret from her new husband",
        "text:the-adventures-of-sherlock-holmes:X",
    ),
    (
        "a banker's son is blamed for stealing precious gems from a "
        "valuable crown-like piece of jewelry left with the family as "
        "collateral for a loan",
        "text:the-adventures-of-sherlock-holmes:XI",
    ),
    (
        "a governess takes a well-paid job with bizarre conditions like "
        "cutting her hair short, at a remote countryside house that turns "
        "out to hide a dark secret",
        "text:the-adventures-of-sherlock-holmes:XII",
    ),
]

# --- code queries: each maps to one real file in the cloned repos, paraphrasing
# what that file's central function/class actually does. ---
CODE_QUERIES = [
    (
        "a function that sends an HTTP GET request to a URL and returns "
        "the response",
        "code:requests:src/requests/api.py",
    ),
    (
        "a method on an HTTP response object that parses its body as JSON "
        "and raises an error if it isn't valid JSON",
        "code:requests:src/requests/models.py",
    ),
    (
        "the method that actually prepares and sends an HTTP request while "
        "reusing connection state like cookies across multiple calls",
        "code:requests:src/requests/sessions.py",
    ),
    (
        "a class representing a command-line flag or option that a CLI "
        "command accepts, as opposed to a positional argument",
        "code:click:src/click/core.py",
    ),
    (
        "a decorator that turns a plain Python function into a runnable "
        "command-line command",
        "code:click:src/click/decorators.py",
    ),
    (
        "a method that loads and compiles a template by name so it's ready "
        "to be rendered with variables",
        "code:jinja:src/jinja2/environment.py",
    ),
    (
        "the master process in a pre-fork web server that starts, "
        "monitors, and restarts worker processes",
        "code:gunicorn:gunicorn/arbiter.py",
    ),
    (
        "a function that takes a string of Python source code and returns "
        "it reformatted according to a fixed style",
        "code:black:src/black/__init__.py",
    ),
    (
        "code that signs and stores a user's session data in a browser "
        "cookie so it can be trusted on the next request",
        "code:flask:src/flask/sessions.py",
    ),
    (
        "a system that matches an incoming request's URL path against a "
        "set of registered rules to find which view function should "
        "handle it",
        "code:werkzeug:src/werkzeug/routing/__init__.py",
    ),
]

QUERIES = [
    {"query": q, "relevant_doc_id": doc_id, "category": "text"}
    for q, doc_id in TEXT_QUERIES
] + [
    {"query": q, "relevant_doc_id": doc_id, "category": "code"}
    for q, doc_id in CODE_QUERIES
]
