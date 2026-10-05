# Week 12 -- Production observability and writing it up (Q1 wrap-up)

## Overview

Eleven weeks produced a RAG system that retrieves well, is gated by evals in CI, and runs on
three kinds of infrastructure (a Cloud Run service, a Cloud Run function, a self-hosted model
on a GPU VM). This week answers the question every one of those eval gates leaves open: **what
is happening to real requests right now?** Evals tell you whether a *change* is safe to ship;
observability tells you whether *what you shipped* is still working. The deliverables are
(1) every deployment target sending traces to Langfuse, (2) an error-rate alert that reaches
you, (3) a README and architecture diagram, and (4) a post that explains the work to someone
who has not lived it.

One finding shaped the whole week and is worth stating up front: **Langfuse alerts cannot send
e-mail.** The roadmap task says "error rate > 2% sends an email notification", but Langfuse's
documented alert channels are Slack, Webhook and GitHub Actions. So the e-mail leg has to be
built, and the interesting engineering is in how you do that without a second, fragile
monitoring system. That is covered below.

## Core concept, in depth

### 1. The Langfuse data model (what a trace actually is)

A **trace** is one request through your system. It contains **observations**, a tree of timed
steps: a plain **span** (`rag-request`), nested spans (`retrieval`), and **generations**
(the LLM call, which additionally carry model, token usage and cost). A **score** is a named
value attached to a trace -- numeric, categorical, or boolean -- and is how *quality and
outcome* become queryable data rather than something you read in logs. Two more fields do a lot
of work in a multi-deployment system:

- **environment** (`LANGFUSE_TRACING_ENVIRONMENT`): a first-class filter in dashboards, the API
  and alerts. We set it to `cloud-run-service` or `cloud-run-function`, so "the function is
  failing" and "the service is failing" are different, separately alertable facts.
- **tags / metadata**: free-form labels. We also write the deployment target as a tag.

### 2. Langfuse sits on OpenTelemetry

The Python SDK (v3+) is built on OpenTelemetry: the traces it emits go out as OTLP over HTTP to
`/api/public/otel/v1/traces` on your Langfuse host (you can see this on the wire -- this week's
real-SDK test captures exactly that request). Langfuse also accepts OTLP from *any* OTel client
and states that it aims to follow the **OpenTelemetry GenAI semantic conventions**
(`gen_ai.request.model`, `gen_ai.usage.input_tokens`/`output_tokens`, `gen_ai.operation.name`, ...).
Practical meaning: if a service in another language, or a framework with built-in OTel
instrumentation, joins the system later, its traces land in the same place with the same shape,
and you are not locked to one SDK. (The GenAI conventions are still marked experimental upstream,
so attribute names can change between releases.)

### 3. Instrumenting serverless is different from instrumenting a server

Three rules, each learned from how Cloud Run behaves (all three live in `app/tracing.py`, which
is deliberately identical in Week 9's service and Week 10's function):

**Flush before the response returns.** Langfuse exports spans in the background, in batches.
Cloud Run with request-based billing throttles CPU to near zero between requests and may freeze
or terminate the instance at any time. A batch that was "about to be sent" can simply never be
sent -- and the requests you are most likely to lose are the last ones before scale-down, which
include the failures you care about most. So each request ends with `langfuse.flush()` (one
short network call; `LANGFUSE_FLUSH_ON_REQUEST=false` turns it off for long-lived servers).

**Telemetry must never take the app down.** If the Langfuse client cannot be constructed, scoring
fails, or the flush times out, the request still succeeds -- the failure is logged and swallowed.
A failure of the request itself is the opposite: it is recorded on the trace, scored, and then
**re-raised unchanged**. Observability that changes behaviour is a bug.

**Mind the cold start.** Langfuse is imported on the first traced request. Importing it costs
about 200 ms on a laptop (measured here: `import langfuse` 207 ms vs `import openai` 267 ms);
a 512 MB Cloud Run container is slower than a laptop. Week 10's whole point was a *lightweight*
function with a measured cold-start tax, so adding this dependency is a trade you should
re-measure (`benchmarks/benchmark.py`), not assume away.

### 4. Turning failures into a rate you can alert on

Langfuse alerts evaluate **one metric** over a **window** against a **threshold** -- for example
"count of observations", "p95 latency", "average of a numeric score". They do not divide one
count by another. "Error rate" is a ratio, so it has to *exist as a single number* before an alert
can watch it. The trick: write a boolean score on every request,

```
request_error = 1   if the request raised
request_error = 0   if it succeeded
```

The documentation notes that the average of a boolean score "is the share of scores that are
true". So `avg(request_error) > 0.02` over one hour **is** "error rate above 2%" -- computed by
Langfuse, filterable by environment, with no ratio logic on your side. Writing the 0 on success
matters as much as writing the 1 on failure: without it the denominator is wrong.

**Alert design details that decide whether anyone trusts it:**

- **Minimum sample.** One failure in eight requests is a "12.5% error rate" and almost certainly
  nothing. A real alert needs a floor on request count (our poller defaults to 20) or it pages
  you for noise and you start ignoring it.
- **Window versus schedule.** A 1-hour window evaluated every hour gives at most one
  notification per breach hour. A 1-hour window checked every minute re-sends the same incident
  60 times.
- **State, not events.** Langfuse alerts have severity states (`OK`, `WARNING`, `ALERT`,
  `NO_DATA`, `PAUSED`) and notify on *transitions*, which is the correct shape: you hear about
  "broke" and "recovered", not "still broken" every cycle.
- **`NO_DATA` is an alert in disguise.** If the service dies completely, there are no requests,
  so no errors, so `avg(request_error)` is undefined and the error-rate alert stays quiet. That is
  exactly when you most need to know. Watch request *count* (or a `NO_DATA` severity) too.

### 5. Two ways to get that rate to your inbox

| | **A. Native alert + webhook relay** | **B. Scheduled poller** |
|---|---|---|
| Who evaluates the threshold | Langfuse (boolean-score average) | Our function, via the Scores API |
| How you are notified | Langfuse POSTs an HMAC-signed webhook to a small relay, which e-mails | Cloud Scheduler calls the function, which e-mails if breached |
| De-duplication | Built in (notifies on severity change; has re-notification) | Not built in -- relies on window = schedule interval |
| Failure mode | If the relay is down, Langfuse **disables the automation's trigger after 5 consecutive delivery failures** (per its docs) -- so a broken relay silently ends your alerting until you re-enable it | If the scheduler or function fails, you hear nothing -- needs its own monitoring |
| Cost of the threshold logic | None -- it is Langfuse's | Ours to test and maintain |
| Alert limit | Langfuse Cloud Hobby allows 2 alerts per organization | None |

This week builds **both**, sharing one e-mail sender: the relay (`langfuse_webhook`) verifies the
webhook signature and formats the e-mail; the poller (`error_rate_check`) is the fallback that
works even if you outgrow the alert limit or distrust the webhook path. Prefer A in production --
it reuses a state machine you did not have to write. Keep B when you need a rule Langfuse alerts
cannot express.

**Verifying a webhook correctly.** Langfuse signs `"<timestamp>.<raw body>"` with HMAC-SHA256 and
sends `x-langfuse-signature: t=<timestamp>,v1=<hex>`. Three mistakes to avoid: verifying against
*re-serialised* JSON (whitespace changes break the signature -- use the raw bytes), comparing with
`==` instead of `hmac.compare_digest`, and accepting any timestamp (a captured request could then
be replayed forever; the docs do not state a tolerance, so we enforce one -- 5 minutes).

### 6. Prove it, do not assume it

"Every deployment target sends traces" is a claim, and the usual way it fails is silently: a
secret is not mounted, `LANGFUSE_BASE_URL` points at a laptop (a Langfuse on `localhost:3000`, as
in Week 8, is unreachable from Cloud Run), a typo in the environment name. `scripts/verify_traces.py`
turns the claim into a check: send N real requests to each target, then poll Langfuse until the
traces and `request_error` scores for that environment arrive (ingestion is asynchronous --
seconds, not milliseconds), and fail loudly if any target is silent.

### 7. Writing it up: problem first, then solution

The roadmap points at how Anthropic and Weaviate write technical posts. What those have in common:

1. **Open with the problem the reader already has**, in their words -- not with your project.
2. **One idea per section**, each ending in something the reader can use.
3. **Show the measurement, including the one that surprised you.** A result that went against the
   expectation is more credible, and more interesting, than a clean win. (This repo has one: dense
   retrieval alone matched hybrid on the top-line recall number; the value of hybrid only showed up
   at the single-query level. A post that hid that would be weaker.)
4. **Claim only what you measured**, with the sample size next to it. 24 questions on a synthetic
   corpus is a real result and a small one; say both.
5. **Close with what to do and what is still open.**

A README is a different genre: it answers "what is this, does it work, how do I run it" in under a
minute -- architecture picture first, results table second, commands third.

## Why it matters in production

- Most RAG incidents are not crashes. They are **silent degradation**: retrieval quietly missing,
  a model update shifting tone, latency drifting up, cost doubling. Traces plus scores are the only
  way to see those; logs are not queryable by "answer quality dropped".
- **CI evals and production monitoring are one loop.** The retrieval_hit_rate proxy and
  `request_error` rate give production a few cheap, always-on numbers; the offline RAGAS/DeepEval
  suites give the expensive, accurate ones. A drop in the cheap numbers is the cue to run the
  expensive ones.
- **Per-environment signals** are what make multi-target deployments debuggable: a function with a
  2% error rate and a service at 0% points at the function's packaging or config, not the model.
- What breaks if you get it wrong: lost traces on scale-down (no flush), a telemetry exception that
  becomes a user-facing 500, an alert that fires on noise, an alert that never fires because the
  denominator is empty, and a webhook endpoint that accepts unsigned or replayed requests.

## Tradeoffs and comparisons

| Choice | Option 1 | Option 2 | What decided it here |
|---|---|---|---|
| Langfuse hosting | Langfuse Cloud | Self-hosted (Week 8's 6-container compose) | Deployed targets must reach it; Cloud is the cheapest way to satisfy that. Self-host when data residency demands it |
| Flush strategy | Per request | Background batching only | Cloud Run throttles CPU between requests; lost traces cost more than ~tens of ms |
| Error rate source | Boolean score average | Ratio of two observation counts | A single metric is what alerts evaluate; booleans make the rate native |
| Alert path | Native alert + relay | Poller | Built both; native preferred for its state machine |
| One module vs per-target modules | One identical file, drift-tested | Two diverging copies | Separate containers need separate copies; a test keeps them byte-identical |

## Common pitfalls

1. **No flush on a frozen instance** -- traces vanish exactly when instances scale down.
2. **Telemetry in the request's failure path** -- a Langfuse timeout turns into a user 500.
3. **Only scoring failures** -- with no `request_error = 0`, the average is always 1.0 or empty.
4. **Alerting on tiny samples** -- add a request-count floor.
5. **Pointing a deployed service at `localhost` Langfuse** -- unreachable from Cloud Run.
6. **Environment name rules** -- `LANGFUSE_TRACING_ENVIRONMENT` must be lowercase alphanumerics with
   `-`/`_` and must not start with "langfuse" (per the SDK docs) -- check the name you set, because a rejected environment is a failure you will only notice by its absence.
7. **Verifying webhooks on parsed JSON** or without a timestamp tolerance.
8. **Secrets in plain environment variables** -- Langfuse's secret key belongs in Secret Manager,
   wired by reference (Terraform here never sees the value).
9. **Believing the post's numbers are bigger than the sample** -- say "24 questions, one synthetic
   corpus" next to every table.

## Check yourself

1. Why does `avg(request_error) > 0.02` express "error rate above 2%", and what breaks if the
   successful requests never write a score?
2. A Cloud Run service uses request-based billing. Explain why a background span exporter can lose
   traces there, and what the per-request flush costs and buys.
3. Langfuse can deliver an alert by webhook but not e-mail. Describe the relay you would build, and
   name three ways a naive implementation of its signature check would be insecure.
4. Your error-rate alert has been green for a week, then the service goes completely down. Why might
   it stay green, and what would you add?
5. The function's traces never show up in Langfuse after deploy, but the service's do. List the
   first four things you would check, in order. (Then compare with what `verify_traces.py` prints.)
6. In one paragraph: which result from this repo would you lead a post with, which would you put in
   the middle, and which one surprised you and why does it belong in the post anyway?
