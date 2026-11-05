"""Langfuse dataset-run logging, against a fake client (never a live Langfuse -- see the module docstring)."""

from types import SimpleNamespace

import pytest

from agent_eval.datasets import RUNS, load_routing
from agent_eval.langfuse_log import DATASET, langfuse_configured, log_routing_run
from agent_eval.trajectory import read_jsonl

ITEMS = load_routing()
TRAJS = read_jsonl(RUNS / "w14_heuristic.jsonl")


class FakeDataset:
    def __init__(self, items, log):
        self.items, self.log = items, log

    def run_experiment(self, *, name, run_name, task, evaluators, run_evaluators, **kw):
        self.log["experiment"] = {"name": name, "run_name": run_name}
        results = []
        for item in self.items:
            output = task(item=item)
            evals = [e(input=item.input, output=output, expected_output=item.expected_output, metadata=item.metadata) for e in evaluators]
            results.append(SimpleNamespace(item=item, output=output, evaluations=evals))
        self.log["run_scores"] = [r(item_results=results) for r in run_evaluators]
        self.log["item_scores"] = {r.item.id: r.evaluations[0].value for r in results}
        return SimpleNamespace(format=lambda: "ok")


class FakeClient:
    def __init__(self, fail_on_experiment=False):
        self.log = {"datasets": [], "items": [], "flushed": 0}
        self.fail = fail_on_experiment

    def create_dataset(self, *, name, **kw):
        self.log["datasets"].append(name)

    def create_dataset_item(self, *, dataset_name, id, input, expected_output, metadata):
        self.log["items"].append(SimpleNamespace(id=id, input=input, expected_output=expected_output, metadata=metadata))

    def get_dataset(self, name):
        if self.fail:
            raise RuntimeError("langfuse down")
        return FakeDataset(self.log["items"], self.log)

    def flush(self):
        self.log["flushed"] += 1


def test_every_item_is_created_with_a_stable_id_label_and_subset():
    client = FakeClient()
    log_routing_run(ITEMS, TRAJS, run_name="r1", client=client)
    items = client.log["items"]
    assert [i.id for i in items] == [i.id for i in ITEMS]  # stable ids -> re-running updates, never duplicates
    assert items[0].expected_output == {"label": "code"} and items[0].metadata["subset"] == "w14"
    assert client.log["datasets"] == [DATASET]


def test_item_scores_are_the_handoff_correctness_of_the_recorded_run():
    client = FakeClient()
    log_routing_run(ITEMS, TRAJS, run_name="r1", client=client)
    scores = client.log["item_scores"]
    assert sum(scores.values()) == 23 and scores["route-01"] == 1.0 and scores["route-12"] == 0.0


def test_the_run_level_score_is_handoff_accuracy():
    client = FakeClient()
    log_routing_run(ITEMS, TRAJS, run_name="r1", client=client)
    (accuracy,) = client.log["run_scores"]
    assert accuracy.name == "handoff_accuracy" and accuracy.value == pytest.approx(23 / 30)
    assert client.log["experiment"] == {"name": "week-14 supervisor handoff", "run_name": "r1"}


def test_the_client_is_flushed_even_when_the_experiment_fails():
    client = FakeClient(fail_on_experiment=True)
    with pytest.raises(RuntimeError, match="langfuse down"):
        log_routing_run(ITEMS, TRAJS, run_name="r1", client=client)
    assert client.log["flushed"] == 1  # short-lived processes must not lose queued scores


def test_a_dataset_that_already_exists_is_not_fatal():
    class Existing(FakeClient):
        def create_dataset(self, **kw):
            raise RuntimeError("already exists")

    client = Existing()
    log_routing_run(ITEMS, TRAJS, run_name="r1", client=client)
    assert len(client.log["items"]) == 30


@pytest.mark.parametrize("env, expected", [({}, False), ({"LANGFUSE_PUBLIC_KEY": "pk"}, False), ({"LANGFUSE_SECRET_KEY": "sk"}, False),
                                           ({"LANGFUSE_PUBLIC_KEY": "pk", "LANGFUSE_SECRET_KEY": "sk"}, True)])
def test_langfuse_is_only_attempted_when_both_keys_are_set(env, expected):
    assert langfuse_configured(env) is expected
