# Week 10 project -- Cloud Run functions serverless inference

The Week 5-9 Northwind RAG service (BM25 retrieval + one OpenAI call), repackaged as
a **Cloud Run function (2nd gen)** and deployed for real, fronted by **API Gateway**,
benchmarked cold-vs-warm and against a plain Cloud Run **service** running the same
code.

## What's actually deployed right now (project `ace-o9h0u9a21e`, `us-central1`)

- `northwind-rag-fn` (Cloud Run function, `min-instances=1` -- see the routing
  decision in `../concept.md`): https://northwind-rag-fn-440137296529.us-central1.run.app
- `northwind-rag-svc` (Cloud Run service, comparison arm, `min-instances=0`):
  https://northwind-rag-svc-440137296529.us-central1.run.app
- API Gateway in front of the function: https://northwind-rag-gateway-5m72drip.uc.gateway.dev
  (try `GET /health` or `POST /chat` with `{"question": "..."}`)

`min-instances=1` bills continuously for one warm instance. Run `./scripts/teardown.sh`
when you're done exploring these.

## Layout

- `function/` -- the actual deployable unit: `main.py` (the `rag_chat`
  functions-framework entry point) + `app/` (corpus, BM25 retrieval, OpenAI call,
  pipeline -- deliberately lighter than Week 9's `app/`, no braintrust/langfuse/ragas).
  `function/Dockerfile` exists only for the service comparison arm -- see
  `scripts/deploy_service.sh`.
- `tests/` -- unit tests for the pipeline, plus a test through
  `functions_framework.create_app` exercising the exact deploy target.
- `scripts/` -- `enable_apis.sh`, `deploy_function.sh`, `deploy_service.sh`,
  `deploy_gateway.sh`, `teardown.sh`. This is the path this week's actual benchmark
  numbers came from.
- `terraform/` -- the same three things (function, service, gateway) as a Terraform
  module instead, for practicing Terraform on the same infrastructure. Not applied --
  see `terraform/README.md` for how to run it yourself (`terraform/scripts/01`-`05`
  handle the full bootstrap-image-plan-apply-destroy sequence, safe to re-run for
  future deployments too); it defaults to `-tf`-suffixed resource names so it can
  coexist with whatever `scripts/` already deployed.
- `gateway/openapi.yaml` -- the API Gateway config template (`${FUNCTION_URL}` is
  substituted in by `deploy_gateway.sh`).
- `benchmarks/benchmark.py` -- cold/warm latency sampler; `benchmarks/results.md` has
  the actual numbers from the real deployment.

## Local development

```bash
uv sync
export OPENAI_API_KEY=sk-...
uv run pytest -v
```

Run the function locally exactly as `gcloud run deploy --source --function` would run
it in the container, via the real `functions-framework` CLI:

```bash
uv run functions-framework --target=rag_chat --source=function/main.py --port=8090
curl -s http://localhost:8090/ -X POST -H 'Content-Type: application/json' \
  -d '{"question": "What is the refund window for annual plans?"}'
```

## Deploy for real

```bash
export PROJECT_ID=your-gcp-project-id
export REGION=us-central1

# One-time
./scripts/enable_apis.sh
printf '%s' "$OPENAI_API_KEY" | gcloud secrets create openai-api-key --project="$PROJECT_ID" --data-file=-
gcloud secrets add-iam-policy-binding openai-api-key --project="$PROJECT_ID" \
  --member="serviceAccount:$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')-compute@developer.gserviceaccount.com" \
  --role=roles/secretmanager.secretAccessor

./scripts/deploy_function.sh   # Cloud Run function, min-instances=0
./scripts/deploy_service.sh    # Cloud Run service, min-instances=0 -- comparison arm

gcloud iam service-accounts create apigw-rag-invoker --project="$PROJECT_ID"
gcloud run services add-iam-policy-binding northwind-rag-fn --region="$REGION" --project="$PROJECT_ID" \
  --member="serviceAccount:apigw-rag-invoker@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role=roles/run.invoker
./scripts/deploy_gateway.sh
```

## Benchmark

```bash
uv run python benchmarks/benchmark.py --target function-min0 \
  --url "$(gcloud run services describe northwind-rag-fn --region=$REGION --project=$PROJECT_ID --format='value(status.url)')" \
  --service northwind-rag-fn --project "$PROJECT_ID" --rounds 8

uv run python benchmarks/benchmark.py --target service-min0 \
  --url "$(gcloud run services describe northwind-rag-svc --region=$REGION --project=$PROJECT_ID --format='value(status.url)')" \
  --service northwind-rag-svc --project "$PROJECT_ID" --rounds 8

# Then set min-instances=1 and re-run without --force-cold to see the eliminated cold path
MIN_INSTANCES=1 ./scripts/deploy_function.sh
uv run python benchmarks/benchmark.py --target function-min1 --no-force-cold \
  --url "$(gcloud run services describe northwind-rag-fn --region=$REGION --project=$PROJECT_ID --format='value(status.url)')" \
  --project "$PROJECT_ID" --rounds 1 --warm-requests-per-round 20
```

See `benchmarks/results.md` for this project's actual recorded numbers and
`../concept.md` for what they mean.

## Teardown

```bash
./scripts/teardown.sh
```

`min-instances=1` (or any value above 0) bills for idle capacity continuously --
tear down when you're done, same as Week 9.

## What's deliberately out of scope

- No load balancer / Cloud Armor in front of any of this -- Week 9 already covers
  that edge-hardening lesson; this week's only public surface is API Gateway itself
  (which has its own managed DDoS/quota protection) plus the two `--allow-unauthenticated`
  Cloud Run endpoints used directly for benchmarking.
- No CI workflow -- this week is a one-off deploy-and-measure exercise, not a
  repeatable pipeline.
