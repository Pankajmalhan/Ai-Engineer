# Week 10: Cloud Run functions serverless inference

## Overview

Week 9 packaged the Northwind RAG service as a hand-written Docker image and deployed
it to Cloud Run as a **service** -- something you build, tag, push, and point Cloud
Run at yourself. This week deploys the *same kind of workload* through a different,
lighter-weight path: **Cloud Run functions** (2nd gen; Google renamed "Cloud
Functions" to "Cloud Run functions" in August 2026 -- see `resources.md`). Instead of
writing a Dockerfile, you write one Python function, point `gcloud run deploy
--function` at it, and Google's buildpacks build the container for you and push it to
Artifact Registry. Under the hood it is still Cloud Run -- same autoscaler, same
revision model, same `*.run.app` URL shape -- but the packaging convention and the
default expectations (small, single-purpose, event- or HTTP-triggered) are different
enough that cold-start behavior, dependency hygiene, and "should this be a function or
a service" become real design questions, not just a deployment detail. This week
answers those questions with actual measurements, not received wisdom: a Cloud Run
function and a Cloud Run service, running the identical RAG pipeline, deployed for
real, benchmarked cold and warm.

## Core concept, in depth

### Cloud Run functions are Cloud Run, wearing a thinner API

The single most important fact this week's deployment surfaces: **there is no
separate compute tier**. `gcloud run deploy --source . --function ENTRY_POINT
--base-image python313` does three things:

1. Runs Google Cloud buildpacks (via Cloud Build) against your source directory. The
   Python buildpack detects `requirements.txt`, installs your dependencies, and
   wraps your entry-point function in a small WSGI server -- the **Functions
   Framework** (`functions-framework`) -- that translates raw HTTP requests into a
   call to your function and your return value back into an HTTP response.
2. Pushes the resulting image to an Artifact Registry repo Cloud Run creates for you
   the first time (`REGION-docker.pkg.dev/PROJECT/cloud-run-source-deploy`).
3. Deploys that image to Cloud Run -- the exact same `google_cloud_run_v2_service`-
   shaped resource Week 9's Terraform created directly.

That third step is the tell: `gcloud run services describe northwind-rag-fn` returns
a completely ordinary Cloud Run service description -- `containerConcurrency`,
`containers[].resources.limits`, a `startupProbe`, a `serviceAccountName`. There is no
`gcloud functions describe` result that looks different in kind. The "function" label
is a *deploy-time convenience and a UI grouping*, not a distinct runtime. This is
also why min-instances, concurrency, CPU/memory limits, and IAM (`roles/run.invoker`)
all work identically for both -- they're the same knobs on the same resource.

What *is* different is the packaging path, and that has real consequences:

- **You don't write a Dockerfile.** You write `requirements.txt` + a Python file with
  one decorated function (`@functions_framework.http`). Buildpacks does the rest.
  This is genuinely less code to maintain, at the cost of less control over the base
  image, layer caching, and non-root user setup that Week 9's Dockerfile handled
  explicitly.
- **The image buildpacks produces is not a generic container.** It's built with the
  [Cloud Native Buildpacks (CNB) spec](https://buildpacks.io/docs/for-app-developers/concepts/launch/),
  which bakes in a `/cnb/lifecycle/launcher` process and metadata describing named
  "process types" (e.g. a `web` process). Cloud Run's function-specific deploy path
  knows how to invoke that correctly. A generic `gcloud run deploy --image` of that
  *exact same image digest*, with no function-specific context, does not -- see
  **Common pitfalls** below for what that failure looks like and why it happens.

### Cold starts, mechanically

A "cold start" is the latency added when a request arrives and there is no already-
running container instance to serve it. Cloud Run has to:

1. Schedule the container onto a worker (find capacity, pull the image if not cached
   there).
2. Start the container process.
3. Wait for it to pass its startup probe (by default, a TCP check on `$PORT`).
4. *Then* your application code's own import-time and first-request work runs --
   for this RAG service, that's importing `rank_bm25`/`openai`, constructing the
   `BM25Okapi` index over the fixture corpus, and (on the very first request only,
   thanks to `@lru_cache`) constructing the OpenAI client.

Every one of those steps scales with **image size and dependency weight**. This is
the concrete reason this week's function code (`function/app/`) drops
`braintrust.wrap_openai`, Langfuse, and Ragas entirely versus Week 9's version of the
same pipeline -- not because they're bad tools, but because every import Python has to
resolve before your function can answer its first request is pure added cold-start
latency, and a "function" workload (small, spiky, frequently cold) pays that cost far
more often than a warm, steady-traffic service does.

`min-instances` sidesteps the problem entirely rather than solving it: Cloud Run keeps
that many container instances running *all the time*, regardless of traffic, so
there's always a warm instance to route to. It trades cold-start latency for
continuous billing -- you pay for idle capacity the same as if it were handling
traffic (CPU is "always allocated" for min-instances, not just "during requests").
`--min-instances=0` (the default, and cheapest) means every idle period long enough
to scale to zero reintroduces the cold-start tax on the next request.

### This project's actual measurements

Both `northwind-rag-fn` (Cloud Run function) and `northwind-rag-svc` (Cloud Run
service, identical app code, hand-written Dockerfile) were deployed for real to
`us-central1` and benchmarked: 8 rounds each of a forced-cold request (achieved by
touching an env var to force a fresh revision -- Cloud Run has no "make this cold"
API) followed by 5 warm requests, plus a separate run of the function with
`min-instances=1`. Full methodology and raw data: `project/benchmarks/results.md` /
`results.jsonl`.

| | n | p50 | p95 | p99 |
|---|---|---|---|---|
| function, min=0, **cold** | 8 | 3406ms | 4447ms | 4447ms |
| function, min=0, warm | 40 | 957ms | 1149ms | 1583ms |
| service, min=0, **cold** | 8 | 4228ms | 4782ms | 4782ms |
| service, min=0, warm | 40 | 980ms | 1505ms | 1518ms |
| function, min=1, first request post-deploy | 1 | 2932ms | -- | -- |
| function, min=1, warm | 20 | 1000ms | 1090ms | 1090ms |

Three real findings, not hypothetical ones:

1. **The cold-start tax here is roughly 2.5-3.9 seconds** (warm p50 ~950-980ms vs.
   cold p50 3406-4228ms) -- for an endpoint an interactive user is waiting on, that's
   the difference between "instant" and "did this hang?"
2. **The function cold-started faster than the service** running the identical code
   (3406ms vs 4228ms p50, ~820ms faster) -- despite the platform being identical
   underneath. The most likely explanation is the buildpacks-built image's layer
   structure/base image, not anything about "function" execution being special (see
   Tradeoffs below) -- this is a single-sample, single-region measurement, not a law.
3. **`min-instances=1` doesn't make the first request free -- it makes cold requests
   rare instead of routine.** The one post-deploy first-request sample still took
   2932ms (constructing the OpenAI client, the BM25 index, etc. still happens once).
   What changes is that this cost is paid once per deploy instead of once per
   idle-then-traffic cycle -- every one of the 20 subsequent warm requests landed in a
   tight 799-1090ms band, identical to the min=0 warm numbers.

## Why it matters in production

- **Traffic shape determines the right packaging, not the workload's "size."** A
  small, cheap-to-run RAG endpoint that gets bursty, infrequent traffic (an internal
  tool, a low-volume webhook handler) is exactly what Cloud Run functions were
  designed for: minimal code to own, pay only for actual usage, accept occasional cold
  starts because nothing time-sensitive is waiting on them. The same code serving a
  customer-facing chat widget with continuous traffic wants `min-instances >= 1`
  regardless of whether it's packaged as a function or a service -- at that point the
  packaging choice is about developer ergonomics, not latency.
- **API Gateway adds a second network hop and its own deadline.** Every request now
  goes client -> API Gateway -> Cloud Run function, and API Gateway's own backend
  deadline (this project sets 30s, above the observed cold p99 -- see
  `gateway/openapi.yaml`) has to be longer than the *slowest* path through your
  function, including a cold start, or the gateway will time out requests your
  backend would have eventually answered.
- **Secret Manager access is IAM, not configuration.** Both the function and the
  gateway's backend service account needed explicit `roles/secretmanager.secretAccessor`
  / `roles/run.invoker` grants during this deployment -- Cloud Run does not
  transitively trust a service account just because it's the "default" one, and API
  Gateway calling your backend is a *separate* principal (`apigw-rag-invoker@...`)
  from whatever calls Cloud Run directly.

## Tradeoffs & comparisons

| | Cloud Run function | Cloud Run service |
|---|---|---|
| Packaging | `requirements.txt` + one entry-point function; buildpacks builds the image | You write and own the Dockerfile |
| Control over base image / layers | Limited (buildpacks decides, though `--base-image` pins the runtime) | Full (Week 9's multi-stage Dockerfile: non-root user, minimal runtime stage, etc.) |
| Runtime platform | Cloud Run (identical) | Cloud Run (identical) |
| Best fit | Single-purpose, event/HTTP-triggered, low code-ownership overhead | Anything needing a custom base image, multiple processes, non-HTTP entrypoints, or fine control over the container |
| Cold start | Same platform mechanics as a service running equivalent code -- what actually differs is how heavy the *image* is, not the "function" label | Same |

The comparison that matters in practice is not "function vs. service" as categories --
this project's own benchmark deployed the *identical application code* both ways and,
because the platform underneath is the same, that isolates the real variable:
**image weight and packaging path**, not "function" vs. "service" as compute tiers.

## Common pitfalls

- **Assuming a buildpacks-built function image is a portable container.** This
  project tried it: taking `northwind-rag-fn`'s exact built image digest and deploying
  it a second time via a plain `gcloud run deploy --image=...` (no `--function` flag)
  failed with `terminated: Application failed to start: failed to resolve binary path:
  error finding executable "functions-framework" in PATH [/cnb/process /cnb/lifecycle
  ...]`. The image *works* under the function deploy path and *fails* under a generic
  one, despite being byte-for-byte the same artifact -- because CNB images rely on the
  `/cnb/lifecycle/launcher` process being invoked with launch metadata that Cloud
  Run's function-specific deploy path wires up and a bare `--image` deploy does not.
  The fix used here: a completely ordinary Dockerfile (`function/Dockerfile`) for the
  service comparison arm, instead of fighting the CNB launcher.
- **Forgetting IAM grants are per-principal, not per-project.** The first
  `deploy_function.sh` run failed outright (`Permission denied on secret ...`) because
  granting `roles/secretmanager.secretAccessor` to *a* service account doesn't cover
  *the* service account Cloud Run actually runs as unless you grant it explicitly.
  Every new caller -- the function's own runtime SA, API Gateway's backend SA -- needs
  its own grant.
- **Sizing API Gateway's deadline off warm-path latency.** If you only ever test a
  gateway against an already-warm backend, the deadline you pick will be too short
  the first time real traffic hits a cold function behind it.
- **Treating `min-instances=1` as free.** It eliminates the *cold* path, but the
  instance it keeps warm is billed continuously, not per-request -- for a genuinely
  low-traffic endpoint this can cost more than the occasional cold start it prevents.

## Decision: routing threshold for low- vs. high-traffic paths

Given this week's measurements, the threshold isn't "requests per minute" in the
abstract -- it's **whether a path's traffic keeps at least one instance warm on its
own**. Cloud Run reclaims an idle instance after a period of no traffic (on the order
of minutes, not seconds); any path whose *typical gap between requests* is shorter
than that window never actually pays the cold-start tax measured above, regardless of
`min-instances`. Any path whose gaps regularly exceed it will hit that ~2.5-3.9s cold
penalty on a real fraction of its requests.

The decision this project makes, concretely:

- **`min-instances=1` for `northwind-rag-fn`** (already applied above) -- this is a
  customer-facing RAG endpoint; a user typing a question and waiting 3-4 extra seconds
  for infrastructure reasons is a bad experience regardless of how rarely it happens,
  and the benchmark shows `min-instances=1` collapses that to a one-time
  ~2.9s cost at deploy instead of a recurring per-idle-cycle one.
- **`min-instances=0` would be the right call instead** for a path that is (a)
  genuinely low-and-bursty (long idle gaps are the normal case, not an edge case) and
  (b) tolerant of an occasional multi-second delay -- an internal admin tool, an async
  webhook handler, a batch/cron-triggered job. Paying continuously for a warm instance
  there buys latency nobody is watching in real time.
- **The general rule this data supports:** route a path to `min-instances >= 1` when
  its p95/p99 latency SLA is smaller than the measured cold p50 (here, ~3.4-4.2s) --
  because that means cold requests, whenever they occur, blow the SLA outright, not
  just look slow. Below that bar, `min-instances=0` is the cheaper default and the
  occasional cold request is a rounding error, not an incident.

## Check yourself

1. Why does `gcloud run services describe` return the same shape of object for both
   `northwind-rag-fn` and `northwind-rag-svc`? What does that tell you about what
   "Cloud Run functions" actually is?
2. Why did redeploying the exact same image digest as a plain `--image` service fail,
   when deploying it via `--function` worked? What's the actual mechanism?
3. What three things does a request pay for on a cold start that it doesn't pay for
   on a warm one? Which of those three scale with your dependency tree, and which
   don't?
4. Given this week's measured cold/warm p50/p95/p99 (`benchmarks/results.md`), at what
   requests-per-minute would you switch a path from `min-instances=0` to
   `min-instances=1`, and what's the actual cost/latency tradeoff you're making at
   that threshold?
5. Why does API Gateway need its own service account with `roles/run.invoker`, rather
   than inheriting whatever permissions the caller of the gateway has?
