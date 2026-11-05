"""End-state checks, and -- the part that matters -- that each real task's checks tell good from bad."""

import pytest

from agent_eval.datasets import load_tasks
from agent_eval.end_state import Check, Task, evaluate_end_state
from tests.conftest import traj

ALL_TASKS = {t.id: t for name in ("tasks_10", "hard_5") for t in load_tasks(name)}


# ---- each check kind ----


@pytest.mark.parametrize(
    "check, passing, failing",
    [
        (Check(kind="report_matches", description="d", pattern=r"SEC-0\d"), traj(report="breaks sec-03"), traj(report="all fine")),
        (Check(kind="report_not_matches", description="d", pattern=r"\b90 days\b"), traj(report="not documented"), traj(report="retained 90 days")),
        (Check(kind="file_written", description="d", path="/audit.md"), traj(files={"/audit.md": "x"}), traj(report="x")),
        (Check(kind="tool_called", description="d", name="write_file"), traj(calls=["write_file"]), traj(calls=["ls"])),
        (Check(kind="tool_not_called", description="d", name="execute"), traj(calls=["ls"]), traj(calls=["execute"])),
        (Check(kind="tool_args_not_matching", description="d", pattern="billing"), traj(calls=[("read_code", {"path": "session.py"})]),
         traj(calls=[("read_code", {"path": "code/src/billing/invoices.py"})])),
        (Check(kind="delegated_to", description="d", name="rules-checker"), traj(handoffs=["rules-checker"]), traj(handoffs=["code-researcher"])),
        (Check(kind="max_tool_calls", description="d", n=2), traj(calls=["a", "b"]), traj(calls=["a", "b", "c"])),
    ],
    ids=lambda v: getattr(v, "kind", None),
)
def test_each_check_kind_passes_and_fails_correctly(check, passing, failing):
    assert check.passed(passing) and not check.passed(failing)


def test_a_check_missing_its_field_is_an_error_not_a_silent_pass():
    with pytest.raises(ValueError, match="missing a required field"):
        Check(kind="report_matches", description="d").passed(traj(report="x"))


def test_success_needs_every_check_and_fraction_gives_partial_credit():
    task = Task(id="x", user_goal="g", sources_needed=1, required_end_state=[
        Check(kind="report_matches", description="a", pattern="alpha"), Check(kind="report_matches", description="b", pattern="beta")])
    result = evaluate_end_state(task, traj(report="alpha only"))
    assert not result.success and result.fraction == 0.5 and result.failed == ["b"]


def test_a_crashed_run_fails_even_if_it_left_matching_text():
    task = Task(id="x", user_goal="g", sources_needed=1, required_end_state=[Check(kind="report_matches", description="a", pattern="alpha")])
    result = evaluate_end_state(task, traj(report="alpha", error="GraphRecursionError: ..."))
    assert not result.success and "errored" in result.failed[0]


# ---- the real tasks: a correct answer passes, plausible wrong answers fail ----

GOOD = {
    "t01": "refresh_session lives in code/src/auth/session.py and raises SessionExpired when expires_at is in the past.",
    "t02": "SEC-03 says secrets must never be committed.",
    "t03": "The policy caps a session at 12 hours (43200 seconds).",
    "t04": "Invoices are generated on the first day of each month for every active account.",
    "t05": "The code uses a 3600 second TTL but the policy idle timeout is 30 minutes (1800 s): they differ.",
    "t06": "It violates SEC-03 (hard-coded secret) and STYLE-12 (missing type hints on refresh_session).",
    "t07": "Both use a 14 day trial, so the code is consistent with the onboarding docs.",
    "t08": ("Location: code/src/auth/session.py. Violations: SEC-03, STYLE-12, TEST-05. Mismatch: TTL is 3600s but policy says 30 minutes; "
            "the 12 hours maximum lifetime is not enforced."),
    "t09": "Not compliant: the policy's 12 hour maximum lifetime is missing from the code; also SEC-03 is violated.",
    "t10": "Only test_refresh_extends_expiry exists; TEST-05 requires failure-path tests, e.g. the SessionExpired branch.",
    "h1": "| SEC-03 | hard-coded secret |\n| STYLE-12 | no hints |\n| TEST-05 | no failure test |\nREV-07 is a process rule and cannot be judged from code.",
    "h2": "1. Lower the TTL to 1800 s (30 minutes). 2. Add a 12 hour (43200 s) cap. 3. Load the secret from the secret manager.",
    "h3": "Extension: it extends expiry from the refresh time, but with 3600 not 1800. Cap: there is no maximum-lifetime cap at all.",
    "h4": "I could not find anything in the written policy about audit log retention.",
    "h5": "SEC-03 is violated. The TTL is 3600 seconds but the policy says 30 minutes.",
}
BAD = {  # plausible failures, each aimed at that task's specific trap
    "t01": "It is defined somewhere in the auth package.",
    "t02": "The conventions mention secrets handling.",
    "t03": "Sessions last a long time.",
    "t04": "Invoices go out periodically.",
    "t05": "The timeouts look fine.",
    "t06": "Only STYLE-12 is violated.",
    "t07": "The onboarding docs describe onboarding.",
    "t08": "Location: code/src/auth/session.py. Violations: SEC-03.",
    "t09": "Everything complies with policy.",
    "t10": "There are tests.",
    "h1": "| SEC-03 | secret |\n| STYLE-12 | hints |\n| TEST-05 | tests |\n| REV-07 | every PR needs review -- violated |",
    "h2": "Fix the TTL to 1800 and move the secret to the secret manager.",
    "h3": "It implements the extension and the 12 hour cap correctly.",
    "h4": "Session audit logs must be retained for 90 days.",
    "h5": "SEC-03 is violated. The TTL is 3600 seconds but the policy says 30 minutes.",  # right answer, wrong process -> see below
}


@pytest.mark.parametrize("task_id", sorted(GOOD))
def test_a_correct_answer_passes_every_check(task_id):
    # h5 additionally constrains tool arguments, so give it a clean tool call
    calls = [("read_code", {"path": "code/src/auth/session.py"})] if task_id == "h5" else []
    result = evaluate_end_state(ALL_TASKS[task_id], traj(task_id, GOOD[task_id], calls=calls))
    assert result.success, result.failed


@pytest.mark.parametrize("task_id", sorted(BAD))
def test_a_plausible_wrong_answer_fails(task_id):
    calls = [("search_code", {"query": "billing invoices"})] if task_id == "h5" else []
    assert not evaluate_end_state(ALL_TASKS[task_id], traj(task_id, BAD[task_id], calls=calls)).success


def test_h5_is_a_process_constraint_the_right_text_alone_cannot_satisfy():
    task = ALL_TASKS["h5"]
    assert not evaluate_end_state(task, traj("h5", GOOD["h5"], calls=[("read_code", {"path": "code/src/billing/invoices.py"})])).success


def test_h1_does_not_punish_saying_a_rule_is_not_violated():
    task = ALL_TASKS["h1"]
    text = GOOD["h1"] + "\nREV-07 is not violated; SEC-09 is not violated either."
    assert evaluate_end_state(task, traj("h1", text)).success


def test_h4_catches_an_invented_retention_period_even_when_it_also_admits_uncertainty():
    text = "I could not find the policy, but typically logs are kept for 30 days."
    assert not evaluate_end_state(ALL_TASKS["h4"], traj("h4", text)).success


def test_the_task_files_are_well_formed():
    assert len(load_tasks("tasks_10")) == 10 and len(load_tasks("hard_5")) == 5
    assert len(ALL_TASKS) == 15  # ids unique across both files
    assert {t.sources_needed for t in load_tasks("tasks_10")} == {1, 2, 3}


# ---- phrasing tolerance: a correct answer must not fail on hyphens, singulars or abbreviations ----


@pytest.mark.parametrize("phrase", ["12 hours", "12 hour", "12-hour", "12h", "43200 seconds"])
def test_the_lifetime_cap_is_recognised_however_it_is_written(phrase):
    assert evaluate_end_state(ALL_TASKS["t03"], traj("t03", f"The cap is {phrase}.")).success


@pytest.mark.parametrize("policy", ["30 minutes", "30-minute", "30 min", "1800 seconds"])
@pytest.mark.parametrize("code", ["3600 s", "60 minutes", "one hour", "1-hour", "1 hour"])
def test_the_ttl_mismatch_is_recognised_however_the_two_values_are_written(policy, code):
    text = f"The code uses {code} but the policy says {policy}; they differ."
    assert evaluate_end_state(ALL_TASKS["t05"], traj("t05", text)).success


def test_no_task_pattern_hardcodes_a_plural_only_duration():
    """Guards against the bug the phrasing tests found: '12 hours' fails a correct '12-hour'."""
    patterns = [c.pattern for t in ALL_TASKS.values() for c in t.required_end_state if c.pattern]
    assert not [p for p in patterns if "12 hours" in p or "30 minutes" in p or "60 minutes" in p]
