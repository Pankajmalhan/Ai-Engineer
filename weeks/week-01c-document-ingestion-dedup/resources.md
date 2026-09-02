# Resources

## From the roadmap paste

- **Primary**: [Unstructured.io documentation](https://docs.unstructured.io/) —
  "Supported File Types" and "Partitioning" sections.
- **Secondary**: "Deduplicating Training Data Makes Language Models Better" (Lee et
  al., 2022) — skim Section 2. https://arxiv.org/abs/2107.06499

## Tooling update noted in the paste (applied in this week's project)

> Swap raw spaCy NER for Microsoft Presidio for the PII step — it's built on spaCy but
> adds purpose-built PII recognizers and anonymization, and is now the more standard
> tool for this exact job.

- [Microsoft Presidio docs](https://microsoft.github.io/presidio/)
- Unstructured — PII detection guide (referenced in the paste; see Unstructured's docs
  site for their current PII-handling guidance)

`app/pii.py`'s `PresidioPIIRedactor` implements this directly (`AnalyzerEngine` +
`AnonymizerEngine`, spaCy `en_core_web_sm` as the NLP engine, plus a custom
`ID_NUMBER` `PatternRecognizer`) rather than a raw spaCy `nlp(text).ents` pass — see
concept.md's "PII redaction: regex vs. Presidio" section for why.

## Added by Claude (thin corpus — the paste didn't cover these directly)

- [datasketch documentation](https://ekzhu.github.io/datasketch/) — `MinHash` and
  `MinHashLSH` API reference; used directly in `app/dedup.py`.
- [pgvector](https://github.com/pgvector/pgvector) — README covers the `vector` column
  type and distance operators this project's `app/vectorstore.py` uses.
- [W&B Python SDK docs](https://docs.wandb.ai/) — `wandb.init`/`run.log` reference for
  `app/metrics.py`; the project defaults to `WANDB_MODE=offline` so no account/API key
  is needed to run it.
