# Week 16c resources

## Given (from the roadmap)

- Primary: Ragas -- "Agentic or Tool use" metrics documentation (`docs.ragas.io`)
- Secondary: DeepEval -- "AI Agent Evaluation Metrics" guide (`deepeval.com`)
- Tools listed for the week: RAGAS (agentic metrics), DeepEval (agent metrics), Langfuse, Pytest, GitHub Actions

## Refreshed links (from the roadmap's research note)

- Langfuse -- AI agent evaluation guide (trajectory, tool use, task completion, multi-turn): https://langfuse.com/resources/engineering/ai-agent-evaluation
- tau-bench (tau2-bench) -- Sierra's benchmark for tool-agent-user interaction: https://github.com/sierra-research/tau2-bench

## Added by Claude

Pages this build was checked against:

- tau2-bench evaluation doc -- `evaluation_criteria` (`actions`, `env_assertions`, `communicate_info`, `nl_assertions`), `reward_basis`, DB end-state hash comparison: https://github.com/sierra-research/tau2-bench/blob/main/docs/evaluation.md
- RAGAS agent metrics (ToolCallAccuracy, ToolCallF1, AgentGoalAccuracy): https://docs.ragas.io/en/latest/concepts/metrics/available_metrics/agents/
- DeepEval AI agent evaluation metrics guide (trajectory vs component metrics): https://deepeval.com/guides/guides-ai-agent-evaluation-metrics
- DeepEval trajectory-based evals in CI (`assert_test(golden=..., metrics=...)`): https://deepeval.com/docs/evaluation-trajectory-based-llm-evals
- Langfuse experiments via the SDK (`create_dataset`, `run_experiment`, `evaluators`, `run_evaluators`): https://langfuse.com/docs/evaluation/get-started/offline

Not verified in this session:
- The exact definition of `pass^k` (the tau2-bench pages fetched do not define it). The project uses the standard
  estimator C(c,k)/C(n,k) from the original tau-bench paper (Yao et al., 2024), cited from memory -- check it
  against the paper before quoting it.
- The RAGAS, DeepEval and Langfuse website URLs above were derived from the documentation *source paths* Context7
  returned (e.g. `docs/concepts/metrics/available_metrics/agents.md`); the content was read through Context7 and
  the installed packages, but those exact web pages were not opened. Only the two tau2-bench pages were fetched directly.
