# Resources

## From the roadmap

- **Primary**: [Promptfoo documentation -- "Red Team" section](https://promptfoo.dev/docs/red-team)
- **Secondary**: OWASP Top 10 for LLMs (2025 edition)
- **Note (✓ verified Aug 2026)**: Promptfoo remains the leading open-source LLM
  red-teaming tool and now maintains a dedicated OWASP Top 10 for Agentic Applications
  page too, worth adding given the plan's later agent focus.
  - [Promptfoo -- OWASP LLM Top 10 mapping](https://www.promptfoo.dev/docs/red-team/owasp-llm-top-10/)
  - [DeepTeam -- Confident AI's red-teaming framework](https://github.com/confident-ai/deepteam)

## Added by Claude, while implementing this week

Pulled live via Context7 (the promptfoo GitHub repo / promptfoo.dev docs) rather than
from training data, since Promptfoo's plugin/CLI surface moves fast:

- [Red team quickstart -- HTTP target configuration](https://github.com/promptfoo/promptfoo/blob/main/site/docs/red-team/quickstart.md)
- [RAG-specific red-teaming guide -- `indirect-prompt-injection`, `rag-poisoning`, `rag-document-exfiltration`](https://github.com/promptfoo/promptfoo/blob/main/site/docs/red-team/rag.md)
- [`policy` plugin -- custom rule enforcement (e.g. "never reveal the system prompt")](https://github.com/promptfoo/promptfoo/blob/main/site/docs/red-team/llm-agents.md)
- [`system-prompt-override` plugin](https://github.com/promptfoo/promptfoo/blob/main/site/docs/red-team/plugins/system-prompt-override.md)
- [Jailbreaking vs. prompt injection -- worked example with `not-contains-any` assertions](https://github.com/promptfoo/promptfoo/blob/main/site/blog/jailbreaking-vs-prompt-injection.md)
- [Command line reference -- exit codes (`100` on any failed test), `PROMPTFOO_FAILED_TEST_EXIT_CODE`, `PROMPTFOO_DISABLE_REDTEAM_REMOTE_GENERATION`](https://github.com/promptfoo/promptfoo/blob/main/site/docs/usage/command-line.md)
- [`redteam report --output report.html` -- HTML report generation](https://github.com/promptfoo/promptfoo/blob/main/site/docs/red-team/model-drift.md)
- [CI integration patterns -- GitHub Actions + `promptfoo-action`, and manual exit-code gating](https://github.com/promptfoo/promptfoo/blob/main/site/docs/guides/llm-as-a-judge.md)
