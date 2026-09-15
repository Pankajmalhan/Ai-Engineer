"""Fixed, small documentation corpus for a fictional SaaS product ('Northwind API').
Deliberately small and hand-writable so every fact used by the 10 hand-labeled
evaluation samples in app/dataset.py can be traced back to exactly one passage --
useful for sanity-checking Context Recall/Precision by eye.
"""

from dataclasses import dataclass


@dataclass
class Document:
    id: str
    text: str


CORPUS: list[Document] = [
    Document(
        id="refunds",
        text=(
            "Northwind API refund policy: annual plans are eligible for a full refund "
            "within 30 days of purchase. Monthly plans are non-refundable but can be "
            "cancelled at any time to stop future billing."
        ),
    ),
    Document(
        id="rate-limits",
        text=(
            "The Northwind API enforces a rate limit of 600 requests per minute on the "
            "Pro tier and 60 requests per minute on the Free tier. Exceeding the limit "
            "returns HTTP 429 with a Retry-After header."
        ),
    ),
    Document(
        id="auth",
        text=(
            "Authentication uses a bearer API key passed in the Authorization header. "
            "Keys can be rotated from the dashboard at any time; the previous key stays "
            "valid for 24 hours after rotation to avoid downtime during deploys."
        ),
    ),
    Document(
        id="data-retention",
        text=(
            "Request logs are retained for 90 days and then permanently deleted. "
            "Account data itself is retained until the account is explicitly deleted by "
            "an admin, at which point it is purged within 7 days."
        ),
    ),
    Document(
        id="uptime-sla",
        text=(
            "The Pro tier SLA guarantees 99.9% uptime measured monthly. Falling below "
            "that threshold entitles the customer to service credits: 10% of that "
            "month's fee for 99.0-99.9% uptime, and 25% for anything below 99.0%."
        ),
    ),
    Document(
        id="billing-cycle",
        text=(
            "Billing runs on a monthly cycle starting from the signup date, not the "
            "calendar month. Annual plans are billed once per year on the anniversary "
            "of signup and receive a 20% discount versus paying monthly."
        ),
    ),
    Document(
        id="support-sla",
        text=(
            "Support tickets from Pro tier customers receive a first response within 4 "
            "business hours. Free tier tickets are handled on a best-effort basis with "
            "no guaranteed response time."
        ),
    ),
    Document(
        id="data-export",
        text=(
            "Account data can be exported at any time as a JSON archive from the "
            "dashboard's Settings > Export page. Exports are generated asynchronously "
            "and emailed as a download link within 15 minutes for most accounts."
        ),
    ),
    Document(
        id="webhooks",
        text=(
            "Webhook deliveries that fail (non-2xx response) are retried up to 5 times "
            "with exponential backoff over 24 hours. After 5 failed attempts the "
            "webhook is marked disabled and must be manually re-enabled."
        ),
    ),
    Document(
        id="password-reset",
        text=(
            "Password reset links are valid for 1 hour after being sent and can only be "
            "used once. Requesting a new reset link invalidates any previously issued "
            "link for that account."
        ),
    ),
]
