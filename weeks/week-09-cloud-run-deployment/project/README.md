# Week 9 project: containerised Cloud Run deployment

The Northwind API RAG service (same fixture as Weeks 5-8, own copy per this repo's
per-week convention) -- unchanged except `app/main.py`'s `/chat` response now also
returns `retrieved_doc_ids`, needed by `evals/eval_endpoint_parity.py` to check
retrieval parity against a live deployment. What's new this week is everything around
it: a production Dockerfile, Terraform for Cloud Run + an external Load Balancer +
Cloud Armor, and a parity check that gates a deploy on the live endpoint still behaving
like local.

## Architecture

```
Internet --> Cloud Armor (WAF + rate limiting)
         --> External HTTP(S) Load Balancer (google_compute_url_map)
         --> Backend Service (serverless NEG)
         --> Cloud Run service (ingress: LB-only, min=1 max=10, CPU target 60%)
```

Cloud Run's `ingress` is set to `INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER`, so the
`*.run.app` URL rejects direct requests -- every request must go through the LB, which
is where Cloud Armor actually sits. See `terraform/cloud_run.tf` for why this needs the
`google-beta` provider and `launch_stage = "BETA"`.

## Local development

```bash
uv sync
export OPENAI_API_KEY=sk-...
uv run uvicorn app.main:app --port 8000
```

```bash
uv run pytest tests/ -v
```

All 36 tests are structural/mocked -- no live GCP project, `OPENAI_API_KEY`, or running
container needed to run them. `tests/test_dockerfile.py` and `tests/test_terraform.py`
check the Dockerfile and Terraform files themselves (the latter also runs
`terraform validate` if the `terraform` CLI is on `PATH`, skipped otherwise).

## Build and run the container locally

```bash
docker build -t northwind-rag:local .
docker run -p 8080:8080 northwind-rag:local
curl http://localhost:8080/health
```

Verified while building this week's project: image builds multi-stage, runs as
`uid=1000 (appuser)` (not root), and Docker reports the container `healthy` via its
`HEALTHCHECK` within a few seconds of starting.

## Deploy

One-time infra setup, then repeatable deploys:

```bash
export PROJECT_ID=your-gcp-project-id
export REGION=us-central1          # optional, this is the default
export REPO_ID=northwind-rag        # optional, this is the default

scripts/build_and_push.sh   # docker build + push to Artifact Registry, writes .last_image
scripts/deploy.sh           # terraform apply using that image
```

`scripts/deploy.sh` runs `terraform apply -auto-approve` -- review `terraform plan`
yourself first if you want to see the diff before it runs (or comment out the
`terraform apply` line and run `plan` by hand). Nothing in this repo runs
`build_and_push.sh` or `deploy.sh` automatically; they're meant to be run by a human,
or from the `workflow_dispatch`-triggered `.github/workflows/week-09-cloud-run-deploy.yml`.

First-time GCP setup this assumes and does *not* automate: `gcloud auth login` /
`gcloud config set project`, and the Artifact Registry API + Compute Engine API +
Cloud Run API enabled on the target project.

## Confirm parity with local (this week's task 5)

```bash
export ENDPOINT_URL=http://$(terraform -chdir=terraform output -raw load_balancer_ip)
export OPENAI_API_KEY=sk-...   # optional -- skips the faithfulness check without it
uv run python -m evals.eval_endpoint_parity
```

Checks, in order: `/health` responds; every golden question's retrieved doc IDs from
the live endpoint exactly match a local BM25 run (retrieval is deterministic, so any
mismatch means the deployed image doesn't match this checkout); and (if
`OPENAI_API_KEY` is set) each live answer's RAGAS faithfulness score clears
`FAITHFULNESS_MIN` (default 0.7) -- generation isn't diffed byte-for-byte against local
since LLM output varies slightly across environments/time even at temperature 0.
Non-zero exit on any failing check, which is what
`.github/workflows/week-09-cloud-run-deploy.yml` gates the deploy job on.

## CI/CD pipeline

`.github/workflows/week-09-cloud-run-deploy.yml` is `workflow_dispatch`-only (not
run on every push, unlike Weeks 6-8's read-only eval CI) -- this pipeline changes live
infrastructure and costs money, so it's a deliberate trigger, not automatic. It:

1. Authenticates to GCP via Workload Identity Federation (`google-github-actions/auth`)
   -- no service-account key ever stored as a secret.
2. Builds and pushes the image, tagged with the commit SHA.
3. Runs `terraform apply` with that image.
4. Runs `evals/eval_endpoint_parity.py` against the resulting load balancer IP, failing
   the job if parity fails.

Requires repo secrets: `GCP_WORKLOAD_IDENTITY_PROVIDER`, `GCP_SERVICE_ACCOUNT`,
`GCP_PROJECT_ID`, `OPENAI_API_KEY`. Setting up the Workload Identity Federation pool/
provider itself is a one-time manual GCP step this repo doesn't script (it's an IAM
trust relationship between GitHub and GCP, not something to automate blindly).

## What's deliberately out of scope

- **HTTPS on the load balancer** -- needs a real domain (a Google-managed cert requires
  proving ownership). `terraform/lb.tf` documents the 3 resources to add
  (`google_compute_managed_ssl_certificate`, `google_compute_target_https_proxy`, a
  `:443` forwarding rule) once a domain points at `load_balancer_ip`.
- **Traffic splitting between revisions** -- Cloud Run supports it natively
  (`revision_traffic` in `google-github-actions/deploy-cloudrun`, or a `traffic` block
  in the Terraform resource); not wired up here since every apply currently sends 100%
  of traffic to the new revision. See `concept.md` for how you'd add a canary step.
