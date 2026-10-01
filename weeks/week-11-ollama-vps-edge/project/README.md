# Week 11 project -- Northwind RAG on a self-hosted Ollama model

The Week 9/10 RAG service (BM25 retrieval + FastAPI), with the generation step made
swappable: `LLM_PROVIDER=openai` or `LLM_PROVIDER=ollama` (an Ollama server on a VPS behind
Nginx with HTTPS and basic auth). Includes the VPS setup script, the Nginx config, an
endpoint verification script, and an eval harness that compares the two backends.

```
app/            corpus, BM25 retrieval, provider-switchable llm.py, pipeline, FastAPI (main.py)
evals/          compare_models.py -- retrieval hit / RAGAS faithfulness / latency / tok/s per provider
deploy/         ollama.nginx.conf (reverse proxy + basic auth + streaming-safe settings)
scripts/        setup_vps.sh (run on the VPS), verify_endpoint.sh (run from your laptop)
terraform/      GCP deployment: VPC, firewall, static IP, service account, Secret Manager, VM (+ numbered scripts/)
tests/          45 tests, no network/keys/GCP access needed
```

## Setup

```bash
uv sync
cp .env.example .env      # fill in as you go
uv run pytest -q          # 45 passed, 1 skipped (nginx -t, only if nginx is installed locally)
```

## Deploy to GCP with Terraform (recommended)

`terraform/` builds the whole thing on GCP; the "VPS" is a Compute Engine VM.

| Resource | Why |
|---|---|
| Custom VPC + subnet | Isolated from the project's `default` network |
| Static external IP | Stable address; also gives a free `<dashed-ip>.sslip.io` name for Let's Encrypt |
| Firewall | 80 open (Let's Encrypt must reach it), 443 limited to `allowed_source_ranges`, SSH **only** from the IAP range, 11434 never opened |
| VM service account | Not the default Compute account; can read only the one password secret |
| Secret Manager secret | Basic-auth password. Value is added by a script, so it never lands in `.tfstate` |
| VM (Debian 12, e2-medium) | Shielded VM, OS Login, project SSH keys blocked; startup script installs Ollama (loopback), pulls the model, sets up Nginx + basic auth + Let's Encrypt |

```bash
cd terraform/scripts
export PROJECT_ID=<your-project> LE_EMAIL=you@example.com

./01_bootstrap.sh          # APIs + secret + generated password (-> terraform/.ollama_password)
./02_plan.sh               # read it
./03_apply.sh              # type "yes"; the VM then takes ~5-10 min to finish first boot
./04_wait_and_verify.sh    # waits for HTTPS, checks 200/401/401/200, runs a real generation
# ... use it, run the comparison ...
./05_destroy.sh            # stops the billing
```

Optional knobs (env vars before the scripts): `MACHINE_TYPE=e2-standard-2` (7B models),
`OLLAMA_MODEL=qwen3:4b`, `DOMAIN_NAME=ollama.example.com`,
`ALLOWED_SOURCE_RANGES='["203.0.113.7/32"]'` (strongly recommended: only your IP can reach
443), `ADMIN_MEMBERS='["user:you@example.com"]'` (IAM users allowed to SSH via IAP).

Notes:
- **Cost:** e2-medium is roughly $25/month running 24/7 (check current pricing). It is
  pay-while-it-exists -- `05_destroy.sh` when you're done.
- **Changing the startup script or nginx config** takes effect by recreating the VM:
  `terraform apply -replace=google_compute_instance.ollama ...`. The static IP survives, but
  a new VM requests a fresh certificate; Let's Encrypt limits duplicate certificates
  (about 5/week per name), so don't churn it.
- **Rotate the password:** add a new secret version, then reboot the VM (it re-reads the
  secret on every boot).
- **SSH:** `terraform output ssh_command` (goes through IAP; there is no public port 22).
- **First-boot logs:** `terraform output startup_log_command`.

The manual path below does the same steps by hand on any VPS.

## The manual VPS runbook (any provider)

1. **Provision** a small Linux VPS -- **4 GB RAM** for `llama3.2:3b` (see `concept.md` §2;
   2 GB only fits the 1B model). Ubuntu 24.04 or Debian 12. Point a DNS `A` record at it, or
   use `<dashed-ip>.sslip.io` (e.g. `203-0-113-7.sslip.io`).
2. **Copy this project** to the VPS and run, as root:
   ```bash
   sudo SERVER_NAME=ollama.example.com LE_EMAIL=you@example.com \
        BASIC_AUTH_USER=rag BASIC_AUTH_PASSWORD='a-long-random-password' \
        ./scripts/setup_vps.sh
   ```
   That installs Ollama (loopback-only), pulls `llama3.2:3b`, sets up Nginx with basic auth,
   opens only 22/80/443, and gets a Let's Encrypt certificate. Override the model with
   `OLLAMA_MODEL=qwen3:4b` (or `gemma3:4b`, `llama3.2:1b`, `mistral`).
3. **Verify from your laptop:**
   ```bash
   BASIC_AUTH_USER=rag BASIC_AUTH_PASSWORD=... ./scripts/verify_endpoint.sh https://ollama.example.com
   ```
   Expect `200 / 401 / 401 / 200`, then a `pong` from both the native and the
   OpenAI-compatible routes. The first generation call is slow (model load).

## Run the service against it

```bash
# .env
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=https://ollama.example.com
OLLAMA_MODEL=llama3.2:3b
OLLAMA_BASIC_AUTH_USER=rag
OLLAMA_BASIC_AUTH_PASSWORD=...

uv run uvicorn app.main:app --port 8000
curl localhost:8000/health
curl -s localhost:8000/chat -H 'content-type: application/json' \
     -d '{"question":"How many days do I have to request a refund on an annual plan?"}'
```

The response includes `provider` and `model`, so you can tell which backend answered.
Local Ollama without Nginx also works: `OLLAMA_BASE_URL=http://localhost:11434` and leave
the auth variables empty.

## Compare against the cloud model

```bash
# needs OPENAI_API_KEY (the cloud arm AND the RAGAS judge for both arms)
uv run python -m evals.compare_models --providers openai ollama --out results.json

# latency/tokens only, no judge cost:
uv run python -m evals.compare_models --providers ollama --skip-faithfulness
```

Prints one row per provider: retrieval hit rate, mean Faithfulness, p50/max latency, tokens
per second. Warm the model with one request first, and read `concept.md` §8 before drawing
conclusions from 8 questions.

## What was and wasn't verified when this was built

- Verified: all 45 tests pass, including an end-to-end test of the OpenAI SDK against a
  local fake Ollama server that asserts the request carries a *Basic* (not Bearer)
  `Authorization` header; both shell scripts pass `bash -n`; static checks on the Nginx
  config and setup script (auth on the proxy location, loopback upstream, buffering off,
  port 11434 never opened, certbot after `nginx -t`).
- Also verified: `terraform validate` and `fmt` pass; the VM startup template renders to valid bash (rendered through real `terraform`); firewall rules, IAM scoping, hardening flags and the no-secret-in-state rule are pinned by tests.
- **Not verified:** `terraform plan/apply` against a real GCP project, a real VPS, real Ollama, real Let's Encrypt issuance, or the live
  RAGAS comparison -- those need a server, a domain, and an `OPENAI_API_KEY`. The scripts
  are written against Ubuntu/Debian conventions but untested on a live box; expect to
  adjust if your image differs. The numbers in `concept.md` (tokens/s, break-even) are
  estimates for you to replace with what `compare_models` measures.
