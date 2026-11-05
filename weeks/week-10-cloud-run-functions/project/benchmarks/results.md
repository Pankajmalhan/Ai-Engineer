# Week 10 benchmark results (real deployment, us-central1, 2026-09-27)

Raw samples: `results.jsonl` (117 requests total). Methodology: see `benchmark.py`'s
docstring -- cold samples are the first request against a freshly forced revision
(guaranteed no warm instance to route to); warm samples are the 5-20 requests
immediately following, on the same instance.

## Cloud Run function vs Cloud Run service, both `min-instances=0`

Identical application code (`function/app/`) deployed two ways: `northwind-rag-fn` via
`gcloud run deploy --source --function` (buildpacks), `northwind-rag-svc` via a plain
Dockerfile + `gcloud run deploy --image`. 8 rounds each (1 cold + 5 warm requests/round).

| | n | p50 | p95 | p99 |
|---|---|---|---|---|
| function cold | 8 | 3406ms | 4447ms | 4447ms |
| function warm | 40 | 957ms | 1149ms | 1583ms |
| service cold | 8 | 4228ms | 4782ms | 4782ms |
| service warm | 40 | 980ms | 1505ms | 1518ms |

**Cold-start delta (function vs service): ~820ms at p50, ~335ms at p95.** The
function's buildpacks-built image consistently cold-started faster than the
Dockerfile-built service image running the identical Python code and dependencies in
this sample. Warm-path latency is statistically indistinguishable between the two
(980ms vs 957ms p50) -- once a container is running, "function" vs "service" packaging
has no measurable effect, which is expected given both are the same Cloud Run
platform underneath (see `concept.md`). The cold-start gap is most plausibly explained
by image/layer characteristics (buildpacks' layer caching and base image) rather than
anything about the "function" execution model itself; this is a single-region,
single-point-in-time sample (n=8 per arm), not a claim that buildpacks images are
always faster.

## Cloud Run function, `min-instances=0` vs `min-instances=1`

| | n | p50 | p95 | p99 |
|---|---|---|---|---|
| min=0 cold (scale-from-zero) | 8 | 3406ms | 4447ms | 4447ms |
| min=1 first request post-deploy | 1 | 2932ms | -- | -- |
| min=1 warm | 20 | 1000ms | 1090ms | 1090ms |

`min-instances=1` does not make the *first request after any deploy* free -- that
single sample (2932ms) still pays for the container's own first-invocation costs
(constructing the OpenAI client, the BM25 index, TLS handshake warm-up). What it
eliminates is the *recurring* cold-start tax: with `min-instances=0`, every request
that lands after Cloud Run has scaled an idle service to zero pays the full
3.0-4.8s cost measured above, repeatedly, all day. With `min-instances=1`, that
container never scales to zero, so that tax is paid once (at deploy time) instead of
once per idle-then-traffic cycle. All 20 requests to a warm `min-instances=1` instance
landed in a tight 799-1090ms band -- indistinguishable from the `min-instances=0` warm
numbers above, confirming the *only* thing `min-instances=1` changes is whether a cold
instance exists to be hit at all.

## What this means for the routing-threshold decision

See `concept.md`'s "Decision: routing threshold for low- vs. high-traffic paths".
