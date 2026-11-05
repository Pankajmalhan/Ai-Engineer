"""The multi-step task both architectures run, and a deterministic scorer for the report.

One question, three sources, one deliverable: find the implementation (code), judge it against
the team rules (rules), compare its behaviour to the written policy (domain docs). A single
retrieval hop can only ever answer a third of it -- that is the point.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

TASK = (
    "Audit the session-refresh feature of this codebase. Do three things: "
    "(1) locate its implementation and its tests; "
    "(2) check the implementation and tests against the team rules and list every violated rule by its id; "
    "(3) compare its behaviour with the documented session policy and flag every mismatch. "
    "Produce a short markdown audit report with the sections Location, Rule violations and Policy mismatches."
)

# Appended only for the Deep Agent: its deliverable is a file in the virtual filesystem.
DEEP_SUFFIX = " Save the finished report to /audit.md, then reply with a one-line confirmation."

# fact name -> regex that must match the report. Each is something a correct audit has to say.
# Recall only: the scorer cannot tell "SEC-03 is violated" from "SEC-03 exists", so it rewards
# naming the right ids; read the report before trusting a score.
FACTS: dict[str, str] = {
    "location": r"src/auth/session\.py",
    "SEC-03": r"SEC-03",
    "STYLE-12": r"STYLE-12",
    "TEST-05": r"TEST-05",
    "ttl_mismatch": r"(?s)(?=.*(30 minutes|1800))(?=.*(3600|60 minutes|1 hour|one hour))",
    "max_lifetime": r"12 hours|12h|43200",
}


@dataclass(frozen=True)
class AuditScore:
    found: dict[str, bool]

    @property
    def points(self) -> int:
        return sum(self.found.values())

    @property
    def total(self) -> int:
        return len(self.found)

    @property
    def missing(self) -> list[str]:
        return [name for name, ok in self.found.items() if not ok]

    def __str__(self) -> str:
        return f"{self.points}/{self.total}"


def score_audit(report: str) -> AuditScore:
    return AuditScore({name: bool(re.search(pattern, report, re.IGNORECASE)) for name, pattern in FACTS.items()})
