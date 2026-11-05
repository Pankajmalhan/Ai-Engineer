"""Log a routing evaluation to Langfuse as a dataset run (items + per-item score + run-level accuracy).

NOTE: written against the Langfuse Python SDK 5.x signatures (``create_dataset``, ``create_dataset_item``,
``Dataset.run_experiment`` with ``evaluators`` and ``run_evaluators``) and exercised only against a fake
client in the tests. It has NOT been run against a live Langfuse project.

Nothing is re-executed: the experiment's ``task`` replays the recorded routing for each item, so the run
in Langfuse shows exactly what the recorded agent did and the scores attached to it.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping

from agent_eval.datasets import RoutingItem
from agent_eval.trajectory import Trajectory

DATASET = "agent-eval/routing-30"


def langfuse_configured(env: Mapping[str, str] | None = None) -> bool:
    env = os.environ if env is None else env
    return bool(env.get("LANGFUSE_PUBLIC_KEY") and env.get("LANGFUSE_SECRET_KEY"))


def log_routing_run(
    items: list[RoutingItem], trajectories: list[Trajectory], *, run_name: str, client=None, dataset_name: str = DATASET
):
    """Create the dataset if needed, run a replay experiment against it, return the ExperimentResult."""
    from langfuse import Evaluation

    if client is None:
        from langfuse import get_client

        client = get_client()
    by_id = {t.id: t for t in trajectories}

    try:
        client.create_dataset(name=dataset_name, description="30 labelled routing queries for the Week 14 supervisor")
    except Exception as exc:  # already exists is fine; anything else surfaces on the next call
        print(f"[langfuse] create_dataset: {type(exc).__name__}: {exc}", file=sys.stderr)
    for item in items:
        client.create_dataset_item(
            dataset_name=dataset_name, id=item.id,
            input={"query": item.query}, expected_output={"label": item.expected},
            metadata={"subset": item.subset, "ambiguous": item.ambiguous},
        )

    def replay_task(*, item, **kwargs):
        t = by_id[item.id]
        return {"routed_to": t.meta.get("routed_to"), "asked": t.meta.get("asked"), "tool": t.tool_names()}

    def handoff_correct(*, input, output, expected_output, metadata=None, **kwargs):
        ok = output["routed_to"] == expected_output["label"]
        return Evaluation(name="handoff_correct", value=1.0 if ok else 0.0, data_type="NUMERIC")

    def handoff_accuracy_run(*, item_results, **kwargs):
        scores = [e.value for r in item_results for e in r.evaluations if e.name == "handoff_correct"]
        return Evaluation(name="handoff_accuracy", value=sum(scores) / len(scores) if scores else 0.0, data_type="NUMERIC")

    try:
        return client.get_dataset(dataset_name).run_experiment(
            name="week-14 supervisor handoff", run_name=run_name, task=replay_task,
            evaluators=[handoff_correct], run_evaluators=[handoff_accuracy_run],
        )
    finally:
        client.flush()
