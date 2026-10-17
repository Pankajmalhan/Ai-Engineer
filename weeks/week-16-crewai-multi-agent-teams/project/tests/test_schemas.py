import pytest

from app.schemas import format_passages, parse_grade_report, parse_passages


def test_parse_passages_reads_id_and_text_lines():
    text = "[refunds] Annual plans are refundable.\n[rate-limits] 600 per minute."
    assert parse_passages(text) == {"refunds": "Annual plans are refundable.", "rate-limits": "600 per minute."}


def test_parse_passages_tolerates_bullets_indent_and_chatter():
    # CrewAI's observation line puts the first passage after a prefix; real models add bullets
    text = "Here you go:\n  - [auth] Use a bearer key.\n* [webhooks] Retried 5 times.\n> [refunds] 30 days."
    assert list(parse_passages(text)) == ["auth", "webhooks", "refunds"]


def test_parse_passages_ignores_citations_inside_a_sentence():
    assert parse_passages("The answer is 10% [uptime-sla] and more.") == {}


def test_format_and_parse_round_trip():
    passages = {"a-1": "first", "b": "second one"}
    assert parse_passages(format_passages(passages)) == passages


def test_grade_report_from_clean_json():
    report = parse_grade_report('{"grades": [{"id": "refunds", "relevant": true, "reason": "x"}, {"id": "auth", "relevant": false}]}')
    assert report.kept_ids == ["refunds"]


def test_grade_report_from_fenced_json_with_surrounding_text():
    raw = 'Sure! Here are the grades:\n```json\n{"grades": [{"id": "auth", "relevant": true}]}\n```\nHope that helps.'
    assert parse_grade_report(raw).kept_ids == ["auth"]


@pytest.mark.parametrize("raw", ["no json at all", '{"grades": [{"id": "x"}]}', '{"wrong": 1}'])
def test_grade_report_rejects_malformed_output(raw):
    with pytest.raises(Exception):
        parse_grade_report(raw)
