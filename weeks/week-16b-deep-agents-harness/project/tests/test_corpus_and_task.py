"""The mock repo, its retrieval, and the report scorer."""

import pytest

from app import corpus
from app.supervisor import retrieve
from app.task import FACTS, score_audit


def paths(chunks):
    return [c.path for c in chunks]


def test_code_search_ranks_the_session_module_first_and_excludes_unrelated_code():
    hits = corpus.search("code", "session refresh")
    assert hits[0].path == "code/src/auth/session.py"
    assert "code/src/billing/invoices.py" not in paths(hits)


def test_search_splits_snake_case_so_identifiers_match_plain_words():
    assert corpus.search("code", "refresh_session")[0].path == "code/src/auth/session.py"


def test_search_is_scoped_to_its_kind():
    assert all(p.startswith("docs/") for p in paths(corpus.search("domain", "session")))
    assert all(p.startswith("code/") for p in paths(corpus.search("code", "session")))


def test_domain_search_finds_the_session_policy_first():
    assert corpus.search("domain", "session timeout lifetime")[0].path == "docs/session-policy.md"


def test_no_match_returns_nothing_rather_than_arbitrary_chunks():
    assert corpus.search("code", "kubernetes") == []
    assert corpus.format_chunks([]) == "(no results)"


def test_rules_lookup_returns_the_whole_rulebook_with_ids():
    text = corpus.format_chunks(corpus.all_rules())
    for rule_id in ("STYLE-12", "STYLE-03", "SEC-03", "SEC-09", "TEST-05", "REV-07"):
        assert rule_id in text


def test_read_numbers_the_lines_and_rejects_unknown_paths():
    out = corpus.read("code/src/api/routes.py")
    assert out.splitlines()[0].strip().startswith("1")
    with pytest.raises(FileNotFoundError, match="known:"):
        corpus.read("code/nope.py")


def test_chunk_line_numbers_point_at_the_real_line():
    chunk = next(c for c in corpus.search("code", "refresh_session") if "def refresh_session" in c.text)
    body = corpus.REPO[chunk.path].splitlines()
    assert body[chunk.line - 1].startswith("def refresh_session")


# ---- the task is only a fair comparison if one source cannot answer all of it ----


def test_no_single_source_can_answer_the_whole_task_but_the_union_can():
    code = retrieve("code", "session refresh implementation")
    rules = retrieve("rules", "")
    domain = retrieve("domain", "session timeout refresh lifetime policy")
    for single in (code, rules, domain):
        assert score_audit(single).points < len(FACTS)
    assert score_audit("\n".join([code, rules, domain])).points == len(FACTS)


def test_code_alone_cannot_establish_the_policy_mismatch():
    score = score_audit(retrieve("code", "session refresh implementation"))
    assert score.found["location"]
    assert not score.found["ttl_mismatch"] and not score.found["max_lifetime"]


# ---- scorer ----


def test_scorer_counts_each_fact_independently_and_is_case_insensitive():
    score = score_audit("see CODE/SRC/AUTH/SESSION.PY; sec-03 and style-12 violated")
    assert score.found == {**{k: False for k in FACTS}, "location": True, "SEC-03": True, "STYLE-12": True}
    assert (score.points, score.total) == (3, 6)
    assert score.missing == ["TEST-05", "ttl_mismatch", "max_lifetime"]


def test_ttl_mismatch_needs_both_the_policy_and_the_code_value():
    assert not score_audit("idle timeout is 30 minutes").found["ttl_mismatch"]
    assert not score_audit("the code uses 3600").found["ttl_mismatch"]
    assert score_audit("policy says 30 minutes but the code uses 3600").found["ttl_mismatch"]
    assert score_audit("code: 1 hour. policy: 1800 seconds").found["ttl_mismatch"]


def test_empty_report_scores_zero():
    assert str(score_audit("")) == "0/6"
