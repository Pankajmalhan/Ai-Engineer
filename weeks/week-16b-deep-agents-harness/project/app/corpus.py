"""A tiny in-memory "codebase" both agents audit, plus the retrieval over it.

Three kinds of material, as in the Q2 3-index design: ``code/`` (source), ``rules/`` (team
conventions) and ``docs/`` (domain documentation). The audit task needs *all three*:

* the code holds the facts (a hard-coded secret, no type hints, a 3600s TTL, no max lifetime),
* the rules say which of those are violations,
* the session policy says what the TTL *should* be (30 minutes, 12h hard cap).

Retrieval is plain keyword scoring over blank-line-separated chunks -- deliberately dumb, so the
experiment measures the agent architecture, not the retriever.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

REPO: dict[str, str] = {
    "code/src/auth/session.py": '''"""Session management for the web app."""
import time

SESSION_SECRET = "dev-secret-123"
SESSION_TTL_SECONDS = 3600


class SessionExpired(Exception):
    pass


def create_session(user_id: str) -> dict:
    now = int(time.time())
    return {"user_id": user_id, "issued_at": now, "expires_at": now + SESSION_TTL_SECONDS, "refreshes": 0}


def refresh_session(session, now=None):
    now = now or int(time.time())
    if session["expires_at"] < now:
        raise SessionExpired(session["user_id"])
    session["expires_at"] = now + SESSION_TTL_SECONDS
    session["refreshes"] += 1
    return session
''',
    "code/src/api/routes.py": '''"""HTTP routes."""
from auth.session import refresh_session


def post_refresh(request: dict) -> dict:
    session = request["session"]
    return {"status": 200, "session": refresh_session(session)}


def get_health() -> dict:
    return {"status": 200}
''',
    "code/tests/test_session.py": '''"""Session tests."""
from auth.session import create_session, refresh_session


def test_refresh_extends_expiry():
    session = create_session("u1")
    refreshed = refresh_session(session, now=session["issued_at"] + 10)
    assert refreshed["expires_at"] > session["issued_at"] + 10
''',
    "code/src/billing/invoices.py": '''"""Monthly invoice generation."""
import datetime


def generate_invoices(accounts: list[dict], today: datetime.date) -> list[dict]:
    if today.day != 1:
        return []
    return [{"account": a["id"], "amount": a["plan_price"]} for a in accounts]
''',
    "code/src/users/onboarding.py": '''"""New-account onboarding."""


def start_onboarding(user_id: str) -> dict:
    return {"user_id": user_id, "tier": "free", "trial_days": 14}
''',
    "rules/conventions.md": """# Team conventions

STYLE-12: Public functions must have type hints on all parameters and the return value.

STYLE-03: Module and function names use snake_case.

SEC-03: Secrets (keys, tokens, passwords) must never be committed to source; load them from the secret manager.

SEC-09: Log lines must never contain session tokens or secrets.

TEST-05: Every public function needs at least one test for its failure path, not just the happy path.

REV-07: Every pull request needs one approving review before merge.
""",
    "docs/session-policy.md": """# Session policy

Idle timeout: a session expires after 30 minutes (1800 seconds) without activity.

Refresh: refreshing a session extends its expiry by another 30 minutes from the moment of the refresh.

Maximum lifetime: no session may live longer than 12 hours (43200 seconds) from creation, however often it is refreshed.
""",
    "docs/glossary.md": """# Glossary

Session: a signed-in period for one user, identified by a signed token.

Tenant: a customer organisation that owns one or more accounts.
""",
    "docs/billing.md": """# Billing

Invoices are generated on the first day of each month for every active account.

Accounts on the free tier are never invoiced.
""",
    "docs/onboarding.md": """# Onboarding

New accounts start on the free tier for 14 days.

After the trial the account owner must pick a paid plan or the account is archived.
""",
}

KINDS = {"code": "code/", "rules": "rules/", "domain": "docs/"}


@dataclass(frozen=True)
class Chunk:
    path: str
    line: int  # 1-based line the chunk starts on
    text: str


def _tokens(text: str) -> set[str]:
    # split on non-alphanumerics so `refresh_session` yields {"refresh", "session"}
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def _chunks(prefix: str) -> list[Chunk]:
    out: list[Chunk] = []
    for path, body in REPO.items():
        if not path.startswith(prefix):
            continue
        line = 1
        for block in body.split("\n\n"):
            stripped = block.strip("\n")
            if stripped:
                out.append(Chunk(path, line + (len(block) - len(block.lstrip("\n"))), stripped))
            line += block.count("\n") + 2
    return out


def search(kind: str, query: str, k: int = 3) -> list[Chunk]:
    """Top-``k`` chunks of ``kind`` ('code' | 'rules' | 'domain') by distinct-query-word overlap."""
    query_words = _tokens(query)
    scored = [(len(query_words & _tokens(c.text + " " + c.path)), c) for c in _chunks(KINDS[kind])]
    scored = [(score, c) for score, c in scored if score > 0]
    scored.sort(key=lambda pair: -pair[0])  # stable: ties keep repo order
    return [c for _, c in scored[:k]]


def all_rules() -> list[Chunk]:
    """The rulebook is short, so a rules lookup returns every rule, not a top-k slice."""
    return _chunks(KINDS["rules"])


def read(path: str) -> str:
    """Whole file with line numbers, like a real ``read_file``."""
    if path not in REPO:
        raise FileNotFoundError(f"{path} (known: {', '.join(sorted(REPO))})")
    return "\n".join(f"{i:>3}  {line}" for i, line in enumerate(REPO[path].splitlines(), 1))


def format_chunks(chunks: list[Chunk]) -> str:
    if not chunks:
        return "(no results)"
    return "\n\n".join(f"--- {c.path}:{c.line}\n{c.text}" for c in chunks)
