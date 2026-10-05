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
tests/          78 tests, no network/keys/GCP access needed
```

## Setup

```bash
uv sync
cp .env.example .env      # fill in as you go
uv run pytest -q          # 78 passed, 1 skipped (nginx -t, only if nginx is installed locally)
```

## Deploy to GCP with Terraform (recommended)

`terraform/` builds the whole thing on GCP; the "VPS" is a Compute Engine VM. **It is GPU-first**: the default machine is `g2-standard-4` with one L4. Set `MACHINE_TYPE=e2-medium` to get the CPU-only baseline back.

| Resource | Why |
|---|---|
| Custom VPC + subnet | Isolated from the project's `default` network |
| Static external IP | Stable address; also gives a free `<dashed-ip>.sslip.io` name for Let's Encrypt |
| Firewall | 80 open (Let's Encrypt must reach it), 443 limited to `allowed_source_ranges`, SSH **only** from the IAP range, 11434 never opened |
| VM service account | Not the default Compute account; can read only the one password secret |
| Secret Manager secret | Basic-auth password. Value is added by a script, so it never lands in `.tfstate` |
| VM (Debian 12, **g2-standard-4: 4 vCPU, 16 GB, 1x NVIDIA L4**) | Shielded VM, OS Login, project SSH keys blocked; startup script installs the NVIDIA driver, then Ollama (loopback), pulls the model, sets up Nginx + basic auth + Let's Encrypt, and proves the GPU is in use |

```bash
cd terraform/scripts
export PROJECT_ID=<your-project> LE_EMAIL=you@example.com

./00_check_gpu_quota.sh    # GPU only: zone offers the L4 AND your project has quota (new projects: usually 0)
./01_bootstrap.sh          # APIs + secret + generated password (-> terraform/.ollama_password)
./02_plan.sh               # read it
./03_apply.sh              # type "yes"; first boot takes ~10-15 min (driver build, one reboot, model pull)
./04_wait_and_verify.sh    # waits for HTTPS; 200/401/401/200; decode speed; model placement (GPU checks enforced)
./06_gpu_proof.sh          # nvidia-smi + peak GPU utilisation during a real generation, over IAP
# ... run the comparison (below) ...
./05_destroy.sh            # stops the billing -- a GPU VM is not cheap to forget
```

### How we verify Ollama is really using the GPU

Three independent checks, because "the VM has a GPU" does not mean "Ollama is using it":

| Where | Check | Passes when |
|---|---|---|
| On the VM at boot | `nvidia-smi` after the driver install. Fails the boot loudly (`GPU_DRIVER_FAILED`) if the driver can't see a device | A device is listed |
| On the VM at boot and on demand (`ollama-gpu-check`) | Ollama's `/api/ps` reports `size_vram` vs `size` for the loaded model | The model is **>= 99% in VRAM**. A model that only partly fits silently runs partly on the CPU, which is the usual failure |
| From your laptop (`04_wait_and_verify.sh`, via `EXPECT_GPU=1`) | Same VRAM check through Nginx, plus decode speed from the native API's `eval_duration` | VRAM placement is full **and** decode is >= 20 tokens/s (the CPU baseline measured ~4.5) |
| Under load (`06_gpu_proof.sh`) | Samples `nvidia-smi` utilisation while a 200-token generation runs; prints prefill and decode timings | Peak utilisation is clearly above 0 |

The speed floor catches the case where everything looks fine but the CPU is doing the work. Override with `MIN_GPU_TOKENS_PER_SEC`.

Optional knobs (env vars before the scripts): `MACHINE_TYPE=e2-medium` (CPU baseline) or `c3-standard-8` (bigger CPU), `GPU_TYPE=nvidia-tesla-t4` with `MACHINE_TYPE=n1-standard-4` (cheaper, older GPU), `USE_SPOT=true` (much cheaper, can be reclaimed), `OLLAMA_NUM_PARALLEL=8`,
`OLLAMA_MODEL=qwen3:4b`, `DOMAIN_NAME=ollama.example.com`,
`ALLOWED_SOURCE_RANGES='["203.0.113.7/32"]'` (strongly recommended: only your IP can reach
443), `ADMIN_MEMBERS='["user:you@example.com"]'` (IAM users allowed to SSH via IAP).

Notes:
- **Cost:** a `g2-standard-4` (L4) is very roughly $0.7-0.9 per hour on demand, i.e. several hundred dollars a month if left running (check current pricing; `USE_SPOT=true` is much cheaper). The CPU `e2-medium` is roughly $25/month. Either way it is pay-while-it-exists -- `05_destroy.sh` when you're done.
- **GPU quota:** a new project usually has 0 L4 quota and the apply fails with a quota error. `00_check_gpu_quota.sh` tells you up front. Quota requests can take minutes to days.
- **Secure Boot is off on the GPU VM** (automatic): the NVIDIA kernel module built by DKMS is unsigned and would not load. vTPM and integrity monitoring stay on.
- **First boot reboots once:** the driver is installed, then the VM restarts to load it, and the startup script resumes. If `nvidia-smi` still fails after that you get `GPU_DRIVER_FAILED` in the serial log (`terraform output startup_log_command`).
- **GPU VMs can't live-migrate**, so host maintenance terminates and restarts the VM (`on_host_maintenance = TERMINATE`).
- **Zone availability:** L4 isn't offered in every zone; change `ZONE` if the check says no.
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

## Load test: how does each backend behave under concurrency?

```bash
# raise Nginx's per-IP rate limit first (see below), then:
uv run python -m evals.load_test --providers openai ollama --concurrency 1 2 4 8 16 \
    --requests-per-level 48 --out load-gpu.json
```

For each concurrency level it runs that many workers back to back and prints p50/p95/max
latency, requests/s, aggregate tokens/s and errors. Read it like this: flat latency with
rising throughput = spare capacity; latency rising while throughput stops growing = you hit
the ceiling. For Ollama that ceiling is `OLLAMA_NUM_PARALLEL` (4 on the GPU default; extra
requests queue); for OpenAI it is your account's rate limit. `--max-retries 0` (default)
makes 503/429s show up in the `err` column instead of disappearing into latency; use
`--max-retries 2` to mimic a production client.

**Raise the Nginx rate limit before load testing.** The default (5 req/s per IP, burst 10) is
an abuse brake sized for CPU inference. A GPU answers in ~0.5 s, so a benchmark exceeds it
and gets `503`s -- that is measuring the limiter, not the GPU (we saw exactly this: a burst
of 40 parallel requests got 11 through and 29 `503`). On the running VM:

```bash
eval "$(terraform -chdir=terraform output -raw ssh_command)"     # opens a shell on the VM
sudo sed -i 's|rate=5r/s|rate=50r/s|; s|burst=10 nodelay|burst=100 nodelay|' /etc/nginx/conf.d/ollama.conf \
  && sudo nginx -t && sudo systemctl reload nginx
```

For a fresh deploy set `NGINX_RATE_LIMIT_PER_SECOND=50 NGINX_RATE_LIMIT_BURST=100` before
`03_apply.sh`. Lower them again for anything you leave exposed.

## Trying bigger models to raise faithfulness

Faithfulness measures whether answers are supported by the retrieved context. The 3B model
fails it by hallucinating (e.g. "365 days" for a 30-day refund window) or refusing when the
answer was in the text. Levers, in the order I would try them:

1. **A bigger / better instruction-following model.** An L4 has 24 GB, so roughly (Q4,
   approximate sizes): `qwen2.5:7b-instruct` ~5 GB, `llama3.1:8b` ~5 GB, `gemma3:12b` ~8 GB,
   `qwen2.5:14b-instruct` ~9 GB. ~24B models fit but leave little room for the KV cache of 4
   parallel slots. Qwen2.5 has no thinking mode; Qwen3 does (its `<think>` text is stripped by
   `app/llm.py`, but it costs tokens and latency).
2. **A steadier measurement.** `--questions extended` runs 24 questions (the 8 plus two
   paraphrases each) so one flipped answer moves the mean by ~0.04, not ~0.12. Also note that
   the CPU run (0.688) and the GPU run (0.625) used the *same model at temperature 0* -- that
   gap is noise from n=8 and the LLM judge, which is why the sample size matters.
3. **Prompt changes for small models**: a shorter system prompt, `RETRIEVAL_TOP_K=2`.
4. **Check the metric's quirks**: a correct "I don't know" scores 0 on Faithfulness.

Pull models onto the running server (no redeploy), then compare them side by side:

```bash
BASIC_AUTH_USER=rag BASIC_AUTH_PASSWORD="$(cat terraform/.ollama_password)" \
  ./scripts/pull_model.sh "$OLLAMA_BASE_URL" qwen2.5:14b-instruct      # repeat per model

uv run python -m evals.compare_models --questions extended --out sweep.json --providers \
  openai ollama:llama3.2:3b ollama:qwen2.5:7b-instruct ollama:qwen2.5:14b-instruct
```

Only one model stays loaded at a time (`OLLAMA_MAX_LOADED_MODELS=1`), so switching between
models costs a load (a few seconds) the first time each is used -- the harness' first
request per model includes that. Then load-test the winner:
`--providers ollama:qwen2.5:14b-instruct`. To make it the default after a redeploy, set
`OLLAMA_MODEL=qwen2.5:14b-instruct`.

## Compare CPU vs GPU vs the cloud model

The earlier CPU run is saved as `results-cpu.json` (p50 ~14.6 s, faithfulness 0.688). After the GPU deploy, run:

```bash
uv run python -m evals.compare_models --providers openai ollama --out results-gpu.json
```

and compare p50/max latency, tokens/s and faithfulness against both `results-cpu.json` and the `openai` row. Faithfulness should be unchanged from the CPU run (same model, temperature 0); latency is what the GPU changes.

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

- Verified: all 78 tests pass, including an end-to-end test of the OpenAI SDK against a
  local fake Ollama server that asserts the request carries a *Basic* (not Bearer)
  `Authorization` header; both shell scripts pass `bash -n`; static checks on the Nginx
  config and setup script (auth on the proxy location, loopback upstream, buffering off,
  port 11434 never opened, certbot after `nginx -t`).
- Also verified: `terraform validate` and `fmt` pass; the VM startup template renders to valid bash (rendered through real `terraform`); firewall rules, IAM scoping, hardening flags and the no-secret-in-state rule are pinned by tests.
- Also verified for the GPU path: the startup template renders to valid bash in both GPU and CPU mode (driver install before Ollama, GPU check only on GPU), the machine-type logic (`g2`/`a2` imply a GPU, `n1` needs `gpu_type`, Secure Boot and parallelism defaults follow), and the verify scripts' pass/fail logic against fake Ollama output (fast+VRAM passes; CPU speed, CPU placement, and half-spilled placement all fail when a GPU is expected).
- **Not verified:** that the NVIDIA driver install works on a real Debian 12 GCE image, GPU quota, and `terraform plan/apply` against a real GCP project, a real VPS, real Ollama, real Let's Encrypt issuance, or the live
  RAGAS comparison -- those need a server, a domain, and an `OPENAI_API_KEY`. The scripts
  are written against Ubuntu/Debian conventions but untested on a live box; expect to
  adjust if your image differs. The numbers in `concept.md` (tokens/s, break-even) are
  estimates for you to replace with what `compare_models` measures.
