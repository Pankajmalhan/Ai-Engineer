"""20 complex queries over the Northwind corpus, each with the answer key needed to score it.

"Complex" here means the query cannot be answered from one sentence of one passage: most need two
documents, several need arithmetic or a condition applied to a number, and three have NO answer in
the corpus (a pipeline that answers them is hallucinating -- the right behaviour is to abstain).

``facts`` is a list of requirements; each requirement is a list of acceptable alternative substrings
(case-insensitive). An answer "has" a fact if it contains any alternative. This is a coarse proxy for
correctness -- cheap, deterministic and reproducible, but blind to a fluent answer that states a fact
wrongly next to the right one. Treat differences of a point or two as noise.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Query:
    id: str
    question: str
    kind: str  # multi-doc | numeric | conditional | single-doc | unanswerable
    expected_docs: tuple[str, ...] = ()
    facts: tuple[tuple[str, ...], ...] = field(default=())

    @property
    def answerable(self) -> bool:
        return self.kind != "unanswerable"


QUERIES: list[Query] = [
    Query("q01", "I'm on the Pro tier and my service had 99.4% uptime last month. What do I get, and how fast will support respond if I file a ticket about it?",
          "multi-doc", ("uptime-sla", "support-sla"), (("10%", "10 %", "ten percent"), ("4 business hours", "four business hours"))),
    Query("q02", "My Pro service only managed 98.2% uptime this month. What credit am I entitled to?",
          "conditional", ("uptime-sla",), (("25%", "25 %", "twenty-five percent"),)),
    Query("q03", "If I buy an annual plan and change my mind after 3 weeks, can I get my money back, and how much would the annual plan have saved me compared with monthly billing?",
          "multi-doc", ("refunds", "billing-cycle"), (("full refund",), ("20%", "20 %", "twenty percent"))),
    Query("q04", "I'm on a monthly plan and want to stop being charged. Can I get a refund for the current month, and how do I stop future billing?",
          "multi-doc", ("refunds",), (("non-refundable", "not refundable", "no refund", "cannot be refunded", "can't be refunded"), ("cancel",))),
    Query("q05", "We rotated our API key an hour ago but one deploy still uses the old key. Will its requests fail, and for how long does the old key keep working?",
          "single-doc", ("auth",), (("24 hours", "24-hour", "24 hrs", "twenty-four hours"),)),
    Query("q06", "Our Free tier integration sends 100 requests per minute. What happens to the excess, and which response header should our client read?",
          "multi-doc", ("rate-limits",), (("429",), ("retry-after",), ("60 requests", "60 req", "60/min", "60 per minute"))),
    Query("q07", "Would upgrading from Free to Pro let us send 100 requests per minute without errors, and would our support response time change?",
          "multi-doc", ("rate-limits", "support-sla"), (("600",), ("4 business hours", "four business hours"))),
    Query("q08", "Our webhook endpoint was down for a full day. Will deliveries resume on their own, and what do we have to do afterwards?",
          "conditional", ("webhooks",), (("5 ", "five"), ("disabled",), ("re-enabled", "re-enable", "manually"))),
    Query("q09", "How long do you keep my request logs, and what happens to my account data after an admin deletes the account?",
          "multi-doc", ("data-retention",), (("90 days", "90-day", "ninety days"), ("7 days", "seven days"))),
    Query("q10", "For a compliance review: if an admin deletes our account today, how long until request logs and account data are each gone?",
          "conditional", ("data-retention",), (("90 days", "90-day", "ninety days"), ("7 days", "seven days"))),
    Query("q11", "When exactly will I be billed each month if I signed up on March 17 on a monthly plan?",
          "conditional", ("billing-cycle",), (("17",), ("signup", "sign-up", "sign up", "signed up", "anniversary"), ("calendar month",))),
    Query("q12", "Compare what a Free customer and a Pro customer get in terms of rate limit and support response.",
          "multi-doc", ("rate-limits", "support-sla"), (("600",), ("60 requests", "60 req", "60/min", "60 per minute"), ("4 business hours", "four business hours"), ("best-effort", "best effort"))),
    Query("q13", "Is the Pro uptime SLA measured per month or per year, and what uptime level triggers the larger credit?",
          "multi-doc", ("uptime-sla",), (("monthly", "per month", "each month"), ("below 99.0", "99.0%", "under 99"), ("25%", "25 %"))),
    Query("q14", "A teammate committed our API key to a public repo. What should we do, and does the old key stop working immediately?",
          "conditional", ("auth",), (("rotate",), ("24 hours", "24-hour", "24 hrs", "twenty-four hours"))),
    Query("q15", "Do failed webhook deliveries keep being retried for longer than a day?",
          "single-doc", ("webhooks",), (("24 hours", "24-hour", "twenty-four hours"), ("5 ", "five"))),
    Query("q16", "We need a 6-month audit trail of API requests for a regulated customer. Is your request log retention long enough?",
          "conditional", ("data-retention",), (("90 days", "90-day", "ninety days"), ("not", "no,", "insufficient", "shorter", "less than", "short"))),
    Query("q17", "If our plan costs $100 per month, how much would we save over a year by switching to annual billing?",
          "numeric", ("billing-cycle",), (("20%", "20 %"), ("240",))),
    Query("q18", "Does Northwind hold SOC 2 Type II certification?", "unanswerable"),
    Query("q19", "What is the monthly price of the Pro plan?", "unanswerable"),
    Query("q20", "Which regions are your data centres in, and can we pin our data to the EU?", "unanswerable"),
]
assert len(QUERIES) == 20 and len({q.id for q in QUERIES}) == 20
