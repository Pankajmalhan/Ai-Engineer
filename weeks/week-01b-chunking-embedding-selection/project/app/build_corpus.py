"""One-time corpus builder: turns the raw fetched sources (cloned repos +
downloaded Gutenberg books, see README) into data/corpus.jsonl.

This is NOT run automatically by the benchmark scripts -- it's a build step,
run once, checked in as data/corpus.jsonl so the rest of the project doesn't
need network access or the source repos/books lying around. Re-run it only
if you want to regenerate the corpus from scratch (see SRC_DIR below).

Two halves, roughly matched in count:
  - "code" docs: real .py files from a handful of small, well-known open
    source repos (requests, click, gunicorn, jinja), non-test, syntactically
    valid, capped per repo so no single repo dominates.
  - "text" docs: real chapters/stories from public-domain Gutenberg books,
    split on each book's actual heading convention (they're not uniform --
    see BOOKS below).
"""

import ast
import json
import re
from pathlib import Path

SRC_DIR = Path(
    "/private/tmp/claude-503/-Users-pankaj-admin-Documents-workspace-personal-ai-engineer"
    "/c498610a-3c91-4747-8ab1-d70d5763cac2/scratchpad/corpus-src"
)
OUT_PATH = Path(__file__).parent.parent / "data" / "corpus.jsonl"

# --- code half --------------------------------------------------------

REPOS = {
    "requests": 90,
    "click": 90,
    "jinja": 60,
    "gunicorn": 90,
    "flask": 90,
    "werkzeug": 90,
    "black": 90,
}
MIN_CODE_CHARS = 300
EXCLUDE_PATH_PARTS = {"test", "tests", "docs", "examples", "__pycache__"}


def collect_code_docs() -> list[dict]:
    docs = []
    for repo, cap in REPOS.items():
        repo_dir = SRC_DIR / "repos" / repo
        if not repo_dir.exists():
            continue
        py_files = sorted(repo_dir.rglob("*.py"))
        taken = 0
        for path in py_files:
            if taken >= cap:
                break
            parts = {p.lower() for p in path.parts}
            if parts & EXCLUDE_PATH_PARTS:
                continue
            try:
                content = path.read_text(encoding="utf-8", errors="strict")
            except (UnicodeDecodeError, OSError):
                continue
            if len(content) < MIN_CODE_CHARS:
                continue
            try:
                ast.parse(content)
            except SyntaxError:
                continue
            rel = path.relative_to(repo_dir).as_posix()
            docs.append(
                {
                    "id": f"code:{repo}:{rel}",
                    "doc_type": "code",
                    "source": repo,
                    "title": f"{repo}/{rel}",
                    "content": content,
                }
            )
            taken += 1
    return docs


# --- text half ---------------------------------------------------------

START_RE = re.compile(r"\*\*\* START OF THE PROJECT GUTENBERG EBOOK.*?\*\*\*", re.I)
END_RE = re.compile(r"\*\*\* END OF THE PROJECT GUTENBERG EBOOK.*?\*\*\*", re.I)

# Each book's heading convention differs; "mode" tells the splitter where to
# find the chapter's title text (Gutenberg plaintext isn't standardized).
BOOKS = [
    {
        "file": "sherlock-holmes.txt",
        "source": "the-adventures-of-sherlock-holmes",
        "header_re": re.compile(r"^([IVXLCDM]+)\.\s+([A-Z][A-Z .,'\-]{3,})$"),
        "mode": "inline",
    },
    {
        "file": "alice-in-wonderland.txt",
        "source": "alices-adventures-in-wonderland",
        "header_re": re.compile(r"^CHAPTER ([IVXLCDM]+)\.$"),
        "mode": "next_line",
    },
    {
        "file": "wizard-of-oz.txt",
        "source": "the-wonderful-wizard-of-oz",
        "header_re": re.compile(r"^Chapter ([IVXLCDM]+)$"),
        "mode": "next_line",
    },
    {
        "file": "treasure-island.txt",
        "source": "treasure-island",
        "header_re": re.compile(r"^([IVXLCDM]+)$"),
        "mode": "next_line",
    },
    {
        "file": "anne-of-green-gables.txt",
        "source": "anne-of-green-gables",
        "header_re": re.compile(r"^CHAPTER ([IVXLCDM]+)\.\s+(.+)$"),
        "mode": "inline",
    },
    {
        "file": "pride-and-prejudice.txt",
        "source": "pride-and-prejudice",
        "header_re": re.compile(r"^CHAPTER ([IVXLCDM]+)\.?\]?$"),
        "mode": "numbered_only",
    },
    {
        "file": "frankenstein.txt",
        "source": "frankenstein",
        "header_re": re.compile(r"^Chapter (\d+)$"),
        "mode": "numbered_only",
    },
    {
        "file": "secret-garden.txt",
        "source": "the-secret-garden",
        "header_re": re.compile(r"^CHAPTER ([IVXLCDM]+)\.$"),
        "mode": "next_line",
    },
    {
        "file": "peter-pan.txt",
        "source": "peter-pan",
        "header_re": re.compile(r"^Chapter ([IVXLCDM]+)\.$"),
        "mode": "next_line",
    },
    {
        "file": "little-women.txt",
        "source": "little-women",
        "header_re": re.compile(r"^CHAPTER ([A-Z]+)$"),
        "mode": "next_line",
    },
]
MIN_CHAPTER_CHARS = 500


def _strip_boilerplate(raw: str) -> str:
    start = START_RE.search(raw)
    end = END_RE.search(raw)
    return raw[start.end() : end.start()] if start and end else raw


def split_book(book: dict) -> list[dict]:
    path = SRC_DIR / "books" / book["file"]
    if not path.exists():
        return []
    raw = _strip_boilerplate(path.read_text(encoding="utf-8", errors="ignore"))
    lines = raw.splitlines()

    headers: list[tuple[int, str, str]] = []  # (line_idx, number, title)
    i = 0
    while i < len(lines):
        m = book["header_re"].match(lines[i].strip())
        if m:
            if book["mode"] == "inline":
                number, title = m.group(1), m.group(2).strip()
            elif book["mode"] == "next_line":
                number = m.group(1)
                title = ""
                j = i + 1
                while j < len(lines) and not lines[j].strip():
                    j += 1
                if j < len(lines) and 3 <= len(lines[j].strip()) <= 80:
                    title = lines[j].strip()
            else:  # numbered_only
                number, title = m.group(1), ""
            headers.append((i, number, title))
        i += 1

    docs = []
    seen_ids: dict[str, int] = {}
    for idx, (line_idx, number, title) in enumerate(headers):
        end_idx = headers[idx + 1][0] if idx + 1 < len(headers) else len(lines)
        body = "\n".join(lines[line_idx + 1 : end_idx]).strip()
        body = re.sub(r"\n{3,}", "\n\n", body)
        if len(body) < MIN_CHAPTER_CHARS:
            continue
        label = title if title else f"Chapter {number}"
        # Some books restart chapter numbering across "Part"/"Volume" divisions
        # our regexes don't track, so the same parsed number can legitimately
        # recur for a different real chapter -- disambiguate rather than
        # silently overwrite/collide (caught by tests/test_corpus.py's
        # uniqueness check, which is exactly why that test exists).
        doc_id = f"text:{book['source']}:{number}"
        if doc_id in seen_ids:
            seen_ids[doc_id] += 1
            doc_id = f"{doc_id}-dup{seen_ids[doc_id]}"
        else:
            seen_ids[doc_id] = 1
        docs.append(
            {
                "id": doc_id,
                "doc_type": "text",
                "source": book["source"],
                "title": f"{book['source']} — {label}",
                "content": body,
            }
        )
    return docs


def collect_text_docs() -> list[dict]:
    docs = []
    for book in BOOKS:
        docs.extend(split_book(book))
    return docs


def main() -> None:
    code_docs = collect_code_docs()
    text_docs = collect_text_docs()
    all_docs = code_docs + text_docs

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUT_PATH.open("w", encoding="utf-8") as f:
        for doc in all_docs:
            f.write(json.dumps(doc, ensure_ascii=False) + "\n")

    by_source: dict[str, int] = {}
    for d in all_docs:
        by_source[d["source"]] = by_source.get(d["source"], 0) + 1
    print(f"code docs: {len(code_docs)}, text docs: {len(text_docs)}, total: {len(all_docs)}")
    for source, count in sorted(by_source.items()):
        print(f"  {source}: {count}")
    print(f"written to {OUT_PATH}")


if __name__ == "__main__":
    main()
