from app.dedup import dedup_rate, find_near_duplicates
from app.models import ProcessedDocument

BASE_TEXT = (
    "Our refund policy allows a full refund within thirty days of purchase for "
    "annual plans, and a prorated refund for any time used beyond that window, "
    "provided the request is submitted through the billing portal. Exceptions are "
    "reviewed case by case by the billing team, and approved refunds are issued "
    "to the original payment method within five business days of approval."
)

# Appending a short clause (rather than editing a word in place) keeps every
# original shingle intact, which -- on a base text this length -- estimates well
# above the 0.85 threshold with margin to spare for MinHash's own approximation
# error (a single in-place word edit on shorter text sits right at the threshold
# and is unreliable across MinHash's random hash draws; see concept.md's Common
# Pitfalls on LSH recall not being guaranteed even above threshold).
NEAR_DUPLICATE_TEXT = BASE_TEXT + " Last reviewed this quarter."

UNRELATED_TEXT = (
    "The incident response runbook requires paging the on-call engineer within "
    "five minutes of a triggered alert, and a written postmortem within three "
    "business days of resolution."
)


def _doc(doc_id: str, text: str) -> ProcessedDocument:
    return ProcessedDocument(id=doc_id, source_path=f"mem://{doc_id}", format="md", text=text)


def test_near_duplicate_is_dropped_and_original_kept():
    docs = [_doc("original", BASE_TEXT), _doc("near-dup", NEAR_DUPLICATE_TEXT)]
    unique, duplicates = find_near_duplicates(docs)
    assert [d.id for d in unique] == ["original"]
    assert len(duplicates) == 1
    assert duplicates[0].kept_id == "original"
    assert duplicates[0].dropped_id == "near-dup"
    assert duplicates[0].jaccard >= 0.85


def test_unrelated_documents_are_both_kept():
    docs = [_doc("a", BASE_TEXT), _doc("b", UNRELATED_TEXT)]
    unique, duplicates = find_near_duplicates(docs)
    assert {d.id for d in unique} == {"a", "b"}
    assert duplicates == []


def test_exact_duplicate_is_dropped():
    docs = [_doc("a", BASE_TEXT), _doc("b", BASE_TEXT)]
    unique, duplicates = find_near_duplicates(docs)
    assert len(unique) == 1
    assert duplicates[0].jaccard == 1.0


def test_dedup_rate_computation():
    assert dedup_rate(total=100, dropped=15) == 0.15
    assert dedup_rate(total=0, dropped=0) == 0.0


def test_50_near_duplicates_are_all_detected_and_removed():
    docs = [_doc("base", BASE_TEXT)]
    for i in range(50):
        perturbed = f"{BASE_TEXT} Revision note {i}."
        docs.append(_doc(f"dup-{i}", perturbed))
    unique, duplicates = find_near_duplicates(docs)
    assert len(unique) == 1
    assert len(duplicates) == 50
    assert all(pair.jaccard >= 0.85 for pair in duplicates)
