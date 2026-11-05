import sys

from app import compare


def test_offline_comparison_shows_the_three_architectures_in_order():
    results = compare.offline_runs(max_hops=6)
    assert [r.name for r in results] == ["supervisor, 1 hop", "supervisor, loop (<=6)", "deep agent"]
    assert [r.score.points for r in results] == [1, 6, 6]
    assert all(r.error is None for r in results)


def test_table_marks_missing_token_counts_as_na_and_names_the_report_source():
    table = compare.format_table(compare.offline_runs(max_hops=6))
    assert "n/a" in table
    assert "file" in table and "final-message" in table
    assert "1/6" in table and "6/6" in table


def test_details_list_missing_facts_and_tool_calls():
    details = compare.format_details(compare.offline_runs(max_hops=6))
    assert "missing facts : SEC-03, STYLE-12, TEST-05, ttl_mismatch, max_lifetime" in details
    assert "sub-agent calls: 3" in details
    assert "specialists: code -> rules -> domain" in details


def test_cli_offline_flag_runs_end_to_end(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["compare", "--offline"])
    compare.main()
    out = capsys.readouterr().out
    assert "OFFLINE" in out and "deep agent" in out
