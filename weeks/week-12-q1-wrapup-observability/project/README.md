# Week 12 project -- observability across every deployment, and alerts that reach you

What this week adds to the Northwind RAG system:

| Piece | Where | What it does |
|---|---|---|
| **Tracing in both deployments** | Week 9 `app/tracing.py` (Cloud Run service), Week 10 `function/app/tracing.py` (Cloud Run function) -- one identical file | Trace per request with retrieval/generation spans, token usage and cost, a `retrieval_hit_rate` score, a **`request_error` boolean score** (1 failed / 0 ok), the deployment target as `environment` + tag; flushes before returning; never lets telemetry break a request |
| **Credentials reach the deployed targets** | Terraform `enable_langfuse` in Weeks 9 and 10, `ENABLE_LANGFUSE=1` in Week 10's gcloud scripts | Langfuse keys from Secret Manager (by reference), `DEPLOY_TARGET` / `LANGFUSE_TRACING_ENVIRONMENT` / `LANGFUSE_BASE_URL` as plain env |
| **Webhook-to-e-mail relay** | `main.py: langfuse_webhook`, `app/webhook.py`, `app/emailer.py` | Verifies Langfuse's HMAC-signed alert webhook (with a replay window) and e-mails it. Langfuse alerts have no e-mail channel, so this is the e-mail leg |
| **Error-rate poller** | `main.py: error_rate_check`, `app/error_rate.py` | Cloud Scheduler calls it; it computes the error rate per environment from the `request_error` scores and e-mails if above 2% (with a minimum-request floor) |
| **"Do the traces actually arrive?" check** | `scripts/verify_traces.py` | Sends real requests to each target and confirms the traces and scores show up in Langfuse |
| **Drift guard** | `tests/test_tracing_parity.py` | Fails if Week 9's and Week 10's tracing module (or its tests) ever differ |

Read [`../concept.md`](../concept.md) first, especially section 4 (why `request_error` exists) and
section 5 (native alert vs poller).

## Install and test

```bash
uv sync
uv run pytest -q        # 51 tests, no network and no Langfuse account needed
```

The two deployments' own suites (run from their `project/` directories):

```bash
cd ../../week-09-cloud-run-deployment/project && uv run pytest -q      # 45 pass; 1 needs a Docker daemon
cd ../../week-10-cloud-run-functions/project   && uv run pytest -q      # 23 pass
```

Both include `test_tracing_real_sdk.py`, which runs the **real Langfuse SDK** (v4) against a local
capture server and asserts what hits the wire: the OTLP trace export, the `request_error` and
`retrieval_hit_rate` scores, the environment, and that a failed request is recorded and still raised.

## 1. Use a Langfuse the deployments can reach

The Langfuse from Week 8 runs on `localhost:3000`; a Cloud Run container cannot reach your laptop.
Use [Langfuse Cloud](https://cloud.langfuse.com) (a free Hobby project is enough; it allows 2
alerts) or a Langfuse you host publicly. Create a project, copy its API keys, then store them in
Secret Manager. The values never go through Terraform or command-line arguments:

```bash
printf '%s' "$LANGFUSE_PUBLIC_KEY" | gcloud secrets create langfuse-public-key --data-file=- --project="$PROJECT_ID"
printf '%s' "$LANGFUSE_SECRET_KEY" | gcloud secrets create langfuse-secret-key --data-file=- --project="$PROJECT_ID"
# grant the runtime service account roles/secretmanager.secretAccessor on both (see Weeks 9/10 README)
```

## 2. Turn tracing on in each deployment

```bash
# Week 9 -- Cloud Run service (Terraform)
cd ../../week-09-cloud-run-deployment/project
ENABLE_LANGFUSE=true PROJECT_ID=... ./scripts/deploy.sh

# Week 10 -- Cloud Run function AND service, via Terraform (one flag covers both targets)
cd ../../week-10-cloud-run-functions/project/terraform/scripts
ENABLE_LANGFUSE=true PROJECT_ID=... ./03_plan.sh && ENABLE_LANGFUSE=true PROJECT_ID=... ./04_apply.sh
# ...or via the gcloud scripts, one target each:
cd ../../ && ENABLE_LANGFUSE=1 PROJECT_ID=... ./scripts/deploy_function.sh   # and ./scripts/deploy_service.sh
```

With `enable_langfuse` off (the default) behaviour is unchanged: no Langfuse secrets are required
and `traced_answer` falls straight through to the plain pipeline.

## 3. Verify every target actually reports

```bash
cp .env.example .env     # LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY / LANGFUSE_BASE_URL of the SAME project
uv run python scripts/verify_traces.py \
  --target cloud-run-service=https://<load-balancer-ip>/chat \
  --target cloud-run-function=https://<function-or-gateway-url>/ \
  --requests 5
```

Each row must say PASS: every request returned 2xx *and* at least that many traces and
`request_error` scores arrived for that environment. The target name must equal the deployment's
`DEPLOY_TARGET` (`cloud-run-service` / `cloud-run-function`). Ingestion is asynchronous; the script
polls for up to 90 s.

## 4. Alerts

### A. Native Langfuse alert (preferred) + e-mail relay

Create the relay, then point a Langfuse automation at it. Secrets first (`langfuse-webhook-secret`
is the signing secret of the Langfuse webhook automation; `smtp-password` is your SMTP credential):

```bash
PROJECT_ID=... SMTP_HOST=smtp.gmail.com SMTP_USERNAME=you@gmail.com \
ALERT_EMAIL_FROM=you@gmail.com ALERT_EMAIL_TO=you@gmail.com ./scripts/deploy_alerting.sh
```

It prints the **webhook URL**. In the Langfuse UI (steps follow the current docs; I could not click
through them from here, so check the labels against your version):

1. **Automations -> Create Automation**: event source *Alert*, action *Webhook*, URL = the printed URL.
2. **Alerts -> New alert**: data source **Scores (boolean)**, filter name = `request_error`, metric
   **average**, operator `>`, alert threshold **0.02**, window **1 hour**; add a filter
   `environment = cloud-run-service`; link the automation. (The average of a boolean score is the
   share that are true, i.e. the error rate.) Repeat for `cloud-run-function` -- Hobby allows 2 alerts.
3. Optionally set a warning threshold (e.g. 0.01) for an early `WARNING` e-mail.

The relay e-mails on `ALERT`, `WARNING` and `OK` (the recovery); it ignores `NO_DATA`/`PAUSED`/`UNKNOWN`.
Note Langfuse disables an automation after 5 consecutive failed deliveries -- if alerts ever stop,
check the relay and re-enable the trigger.

### B. Scheduled poller (no Langfuse alert needed)

`deploy_alerting.sh` also creates a private `error-rate-check` function and an hourly Cloud Scheduler
job (OIDC-authenticated). It computes the error rate per environment from the Scores API and e-mails
if it exceeds `ERROR_RATE_THRESHOLD` (default 0.02) with at least `ERROR_RATE_MIN_REQUESTS` (20)
requests in the window. Trigger it now:

```bash
gcloud scheduler jobs run error-rate-check --location=us-central1 --project="$PROJECT_ID"
```

Window (60 min) equals the schedule (hourly) on purpose: a continuing breach produces at most one
e-mail per hour, since the poller keeps no state.

## What was and was not verified

- **Verified:** all 51 + 45 + 23 tests above pass. The tracing module was exercised end-to-end with the
  real Langfuse SDK against a capture server (traces over OTLP, scores via ingestion, correct
  environment, error path). Webhook signing follows Langfuse's documented algorithm and is tested by
  re-deriving the HMAC independently. The Scores API calls are checked against the installed SDK's
  typed signatures. Terraform changes `validate`, and the `enable_langfuse` logic was evaluated for both
  values in both stacks.
- **Not verified (needs your accounts):** a real Langfuse project, a real deploy of either target with
  tracing on, a real e-mail send through your SMTP provider, the Langfuse UI steps above, and the
  Cloud Scheduler job. `verify_traces.py` is how you confirm the first two.
- **Not re-measured:** the cold-start cost of adding the Langfuse dependency to the Week 10 function.
  `import langfuse` took ~200 ms on a laptop; re-run Week 10's `benchmarks/benchmark.py` with tracing on.
