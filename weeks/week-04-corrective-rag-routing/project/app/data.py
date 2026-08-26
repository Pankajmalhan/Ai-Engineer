"""A small demo corpus for each pgvector collection, so the router and CRAG pipeline
have something real to retrieve and grade against. Not realistic scale -- just enough
documents for correct-vs-irrelevant grading to be demonstrable and testable.
"""

from app.models import Document

DOCS_COLLECTION = "docs"
CODE_COLLECTION = "code"

DEMO_HYBRID_CORPUS = [
    Document("d1", "Our refund policy allows full refunds within 30 days of purchase "
                    "for annual plans, and prorated refunds after that."),
    Document("d2", "The company was founded in 2018 by a team of three engineers "
                    "in Austin, Texas."),
    Document("d3", "Our enterprise pricing tier includes SSO, dedicated support, "
                    "and a 99.95% uptime SLA."),
    Document("d4", "Employees get unlimited PTO and a home office stipend of $500 per year."),
    Document("d5", "The next public holiday observed company-wide is Labor Day."),
    Document("d6", "Our uptime SLA guarantees 99.9% availability measured monthly, "
                    "with service credits for any breach."),
]

DEMO_CODE_CORPUS = [
    Document("c1", "def get_user_by_id(user_id): return db.query(User)."
                    "filter(User.id == user_id).first()"),
    Document("c2", "A NullPointerException in getUserById() usually means the user "
                    "record wasn't found and the caller didn't null-check the result."),
    Document("c3", "git merge conflicts are resolved by editing the conflicted file, "
                    "removing the <<<<<<< markers, then running git add and git commit."),
    Document("c4", "IndexError: list index out of range happens when you access an "
                    "index >= len(list); check bounds before indexing."),
    Document("c5", "def reverse_linked_list(head): prev = None\n"
                    "while head: head.next, prev, head = prev, head, head.next\n"
                    "return prev"),
    Document("c6", "requests.Session() with a Retry adapter mounted on HTTPAdapter "
                    "configures automatic retries with backoff."),
]


def seed_demo_data(store) -> None:
    """Upserts the demo corpora into their pgvector collections. Idempotent --
    upsert() is an ON CONFLICT DO UPDATE, so re-running this is safe."""
    store.upsert(DOCS_COLLECTION, DEMO_HYBRID_CORPUS)
    store.upsert(CODE_COLLECTION, DEMO_CODE_CORPUS)
