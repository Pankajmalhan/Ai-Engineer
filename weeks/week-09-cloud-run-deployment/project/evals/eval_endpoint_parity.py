"""Task 5's "confirm parity with local" gate: hits a live Cloud Run endpoint's /chat
for every GOLDENS question and checks it behaves the same way the local pipeline does.

Two different notions of "parity", checked differently on purpose:

- Retrieval is deterministic (BM25 over a fixed corpus) -- the deployed service's
  retrieved_doc_ids MUST exactly match a local BM25Retriever run over the same
  questions. Any mismatch means the deployed image is running different code/corpus
  than this checkout, which is exactly the class of bug a container deploy can
  silently introduce (stale image, wrong revision, build cached the wrong layer).

- Generation is not deterministic across environments/time even at temperature=0 (model
  provider updates, minor infra differences) -- so this doesn't diff remote vs. local
  answers byte-for-byte. Instead it re-scores the remote's own answer with RAGAS
  faithfulness and asserts it clears FAITHFULNESS_MIN, i.e. "still answers well", which
  is what actually matters after a deploy.

Run with: uv run python -m evals.eval_endpoint_parity
Requires: ENDPOINT_URL (the load balancer IP or a domain in front of it -- not the
*.run.app URL, which the Terraform ingress setting rejects direct requests to).
OPENAI_API_KEY is only needed for the faithfulness check; without it, that check is
skipped and only retrieval parity + health run (still a meaningful smoke gate).
"""

from __future__ import annotations

import os
import sys

import httpx

from app.dataset import GOLDENS
from app.retrieval import BM25Retriever

FAITHFULNESS_MIN = float(os.environ.get("FAITHFULNESS_MIN", "0.7"))
REQUEST_TIMEOUT = 30.0


def check_health(endpoint: str, client: httpx.Client) -> bool:
    try:
        response = client.get(f"{endpoint}/health", timeout=REQUEST_TIMEOUT)
    except httpx.HTTPError as exc:
        print(f"FAIL health: could not reach {endpoint}/health -- {exc}")
        return False
    ok = response.status_code == 200 and response.json().get("status") == "ok"
    print(f"{'PASS' if ok else 'FAIL'} health: {response.status_code} {response.text[:200]}")
    return ok


def check_retrieval_parity(endpoint: str, client: httpx.Client) -> bool:
    retriever = BM25Retriever()
    all_ok = True
    for sample in GOLDENS:
        local_ids = [d.id for d in retriever.retrieve(sample.question, k=3)]
        response = client.post(
            f"{endpoint}/chat", json={"question": sample.question}, timeout=REQUEST_TIMEOUT
        )
        if response.status_code != 200:
            print(f"FAIL retrieval parity: HTTP {response.status_code} for {sample.question!r}")
            all_ok = False
            continue
        remote_ids = response.json().get("retrieved_doc_ids", [])
        match = remote_ids == local_ids
        all_ok = all_ok and match
        status = "PASS" if match else "FAIL"
        print(f"{status} retrieval parity: {sample.question!r} local={local_ids} remote={remote_ids}")
    return all_ok


def check_faithfulness(endpoint: str, client: httpx.Client) -> bool:
    if not os.environ.get("OPENAI_API_KEY"):
        print("SKIP faithfulness: OPENAI_API_KEY not set")
        return True

    from app.metrics import score_faithfulness

    all_ok = True
    for sample in GOLDENS:
        response = client.post(
            f"{endpoint}/chat", json={"question": sample.question}, timeout=REQUEST_TIMEOUT
        )
        if response.status_code != 200:
            continue
        body = response.json()
        score = score_faithfulness(sample.question, body["answer"], body["retrieved_contexts"])
        ok = score >= FAITHFULNESS_MIN
        all_ok = all_ok and ok
        status = "PASS" if ok else "FAIL"
        print(f"{status} faithfulness: {sample.question!r} score={score:.2f} (min {FAITHFULNESS_MIN})")
    return all_ok


def main() -> int:
    endpoint = os.environ.get("ENDPOINT_URL")
    if not endpoint:
        print("ENDPOINT_URL is not set -- point it at the load balancer, e.g. http://<lb_ip>", file=sys.stderr)
        return 2
    endpoint = endpoint.rstrip("/")

    with httpx.Client() as client:
        results = [
            check_health(endpoint, client),
            check_retrieval_parity(endpoint, client),
            check_faithfulness(endpoint, client),
        ]

    return 0 if all(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
