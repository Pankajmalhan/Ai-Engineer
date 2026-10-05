Your RAG demo works. Then a customer pastes an error code and it retrieves the wrong document.

That is the problem I wanted to understand properly this quarter: **a single embedding vector per document is a lossy summary, and some questions need the exact words that summary threw away.** Error codes, SKUs, version strings, someone's surname. Dense retrieval ranks by meaning; BM25 ranks by literal terms; each fails exactly where the other is strong.

So over twelve weeks I built the thing end to end and measured every step. Here is what held up, and what surprised me.

**1. Hybrid search is insurance, not a magic number.**
I combined pgvector embeddings with BM25 using reciprocal rank fusion, on a 70-document corpus with 20 queries. BM25 alone hit 90% recall@10. Dense alone and hybrid both hit 100%.

I expected dense to fail on exact tokens. It did not: the small embedding model's tokenizer kept rare strings recognisable enough. Hybrid's benefit showed up at the level of individual queries, not in the headline number. If I had only reported the headline, I would have told you a cleaner story than the true one.

**2. Reranking earned its latency.**
Adding a cross-encoder reranker (bge-reranker-base) took NDCG@10 from 0.910 to 0.945 and recovered the one query that retrieval missed entirely. It cost about 166 ms per query. It also made one exact-match query worse, which is why I read the per-query table and not just the average.

**3. Evals are only useful if they can stop a merge.**
I wired the quality checks into CI: a DeepEval suite that fails the push if Faithfulness drops below 0.8, Answer Relevancy below 0.75 or Contextual Recall below 0.7. A promptfoo red-team suite found that my first system prompt leaked an internal escalation contact when asked directly. One failure out of ten cases. I hardened the prompt, and the suite went to 10 of 10. Braintrust then diffs every pull request's scores against main, so "faithfulness dropped from X to Y on this PR" is a comment, not a guess.

**4. Self-hosting a model is a quality question before it is a cost question.**
I deployed the service to Cloud Run as both a service and a function and measured cold starts: about 4.2 s for the service and 3.4 s for the function, against roughly 1 s warm. Then I tried running the generator myself on a GCP GPU VM. On my 24-question set, Llama 3.2 3B scored 0.71 on RAGAS Faithfulness. gpt-4o-mini scored 0.98. Qwen2.5 14B on a single L4 GPU also scored 0.98, at a 1.7 s median versus 1.06 s. A small model on a CPU took about 15 s per answer; the GPU brought it to about one second.

The sample is small and the corpus is synthetic, so I read this as "the method works", not "Qwen beats everything".

**5. Observability is the part nobody screenshots.**
Every deployed target sends traces to Langfuse, tagged with its own environment, so a failing function and a healthy service are different facts. Each request also writes a boolean `request_error` score. The average of a boolean score is the share that are true, so `average > 0.02 over an hour` is literally "error rate above 2%".

Two things I only learned by building it. Serverless instances freeze between requests, so I flush traces before returning or the last ones before scale-down vanish. And Langfuse alerts notify by Slack, webhook or GitHub Actions, not e-mail, so I wrote a small signed-webhook relay to send the e-mail.

**What I would tell someone starting:**
- Report the result that surprised you. It is the most credible one.
- Put the sample size next to every number.
- Make a metric exist as one number before you try to alert on it.
- Test the failure path of your telemetry as hard as the happy path.

Everything is in the repo, with tests: [repo link]. If you are building retrieval and have a failure mode I did not hit, I would like to hear about it.

#RAG #LLM #MLOps #AIEngineering
