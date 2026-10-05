# Week 11 -- Self-hosting an LLM on a VPS with Ollama (edge deployment)

## Overview

Every week so far the "generate" step of the RAG pipeline has been an API call to
OpenAI. This week you move that one step onto a machine you control: a ~€5/month VPS
running an open-weight model (Llama 3.2 3B) served by **Ollama**, fronted by **Nginx** for
TLS and authentication. The rest of the system -- BM25 retrieval, the FastAPI service,
the RAGAS evals -- stays the same, which is the point: it lets you measure exactly what
changes (quality, latency, cost, data exposure) when only the model host changes.

Three reasons teams do this, and the week's goals map onto them:

| Motivation | What self-hosting buys | What it costs you |
|---|---|---|
| **Data privacy** | Prompts and retrieved documents never go to a third-party model API. | The VPS provider (and you) are now the data processor; you own patching, access control, logging. |
| **Offline / edge** | The same stack runs on an on-prem box, a laptop, or a site with no internet -- no dependency on a vendor's uptime. | You own availability. One small VPS is one point of failure. |
| **Cost at high volume** | Fixed monthly price instead of per-token billing. | Only wins above a break-even volume, and only if the box can serve that volume at acceptable latency (worked through below). |

## Core concept, in depth

### 1. What Ollama actually is

Ollama is a local model server wrapped around **llama.cpp**. It downloads models in
**GGUF** format (weights already **quantized**), loads them into RAM (or VRAM if a GPU
exists), and exposes an HTTP API on port **11434**:

- `POST /api/generate` and `POST /api/chat` -- Ollama's native API (streams
  newline-delimited JSON by default; `"stream": false` returns one object).
- `GET /api/tags` -- lists locally pulled models. `POST /api/pull` -- downloads one.
- `POST /v1/chat/completions` (and friends) -- an **OpenAI-compatible** route. This is
  what lets the FastAPI service reuse the `openai` SDK unchanged: point `base_url` at
  `https://<host>/v1`, set `model="llama3.2:3b"`.

**Ollama has no authentication.** Anything that can reach port 11434 can generate, pull
models, or delete them. Publicly reachable Ollama instances are routinely found and abused
on the open internet. That is the entire reason for the Nginx layer, and why this week's
setup binds Ollama to `127.0.0.1` and never opens 11434 in the firewall.

### 2. Will a 3B model fit in 2 GB? (No -- and here is the arithmetic)

The roadmap says Llama-3.2-3B "fits in 2 GB RAM". Weights alone are about that size, but
that is not the whole footprint:

```
weights   ≈ parameters × bits-per-weight / 8
          ≈ 3.2 B × ~4.8 bits (Q4_K_M) / 8  ≈ 1.9-2.0 GB   (the GGUF download is ~2 GB)
KV cache  grows with context length (tokens in prompt + generated)
runtime   llama.cpp buffers, Ollama process, the OS, Nginx, sshd ...
```

So a 2 GB machine has no headroom: it swaps or gets OOM-killed. **Plan for 4 GB RAM** for
the 3B model (add swap as a safety net -- `setup_vps.sh` does), or drop to Llama 3.2 **1B**
(~0.8 GB) for a 2 GB box. Provider naming has also moved on: "CX21" is the older Hetzner
name; check the current console for the ~2 vCPU / 4 GB shared-vCPU tier at roughly the same
price. Rules of thumb for other models (Q4): 4B ≈ 2.5-3 GB (Gemma 3 4B, Qwen3 4B),
7B ≈ 4.5 GB (Mistral 7B -- needs an 8 GB VPS).

### 3. Why CPU inference is slow, and which part is slow

Generation has two phases with different bottlenecks:

- **Prefill** (reading the prompt): compute-bound. A RAG prompt carries the system prompt
  plus 3 retrieved passages -- a few hundred tokens -- so this is a multi-second wait on
  2 shared vCPUs before the first output token.
- **Decode** (producing tokens one at a time): **memory-bandwidth-bound**. Every token
  requires streaming essentially all the weights through the CPU once, so
  `tokens/s ≲ memory bandwidth / model size`. A shared VPS with ~10-20 GB/s effective
  bandwidth and a 2 GB model tops out around single-digit tokens/s.

These are estimates -- `evals/compare_models.py` measures the real numbers on your box
(p50/max latency and tokens/s per provider). Expect an answer to take on the order of
seconds to tens of seconds, versus ~1 s from a hosted API. Also expect the **first**
request after idle to be slower: loading the model from disk. `OLLAMA_KEEP_ALIVE=30m`
(set by `setup_vps.sh`) keeps it resident between requests.

### 4. The cost break-even, worked through

Illustrative numbers -- **verify current prices before trusting them**:

```
gpt-4o-mini (assumed):  $0.15 / 1M input tokens,  $0.60 / 1M output tokens
one RAG request:        ~600 input + ~60 output tokens
                     -> 600×0.15/1e6 + 60×0.60/1e6 ≈ $0.000126 per request

VPS:                    ~€5 ≈ $5.4 / month, fixed
break-even              ≈ 5.4 / 0.000126 ≈ 43,000 requests / month ≈ 1,400 / day
```

Now the other side: capacity. One box, one request at a time (`OLLAMA_NUM_PARALLEL=1`),
~15 s per request ≈ 4 requests/minute ≈ 170,000 requests/month if saturated 24/7 -- and
real traffic is bursty, so far less is usable without queueing. The window where
self-hosting wins is therefore **between roughly 43k requests/month and whatever the
box can serve at latency your users tolerate**. Below break-even the API is cheaper;
above capacity you need a bigger box or a GPU, and the fixed-cost story changes. "Cost
elimination" is true only for high-volume, latency-tolerant, quality-tolerant workloads
(batch classification, internal tools, offline summarisation) -- not a live chat UI.

### 5. Nginx: what each directive is doing (see `deploy/ollama.nginx.conf`)

- **TLS termination.** Nginx holds the certificate; Ollama speaks plain HTTP on loopback.
  This matters because **basic auth is not encryption**: the header is just
  `base64(user:password)`. Over plain HTTP anyone on the path reads the password. HTTPS is
  mandatory, not optional polish.
- **`auth_basic` + `auth_basic_user_file`.** Nginx checks `Authorization: Basic ...`
  against an `htpasswd` file before proxying. No credentials or wrong credentials -> `401`
  and Ollama never sees the request.
- **`proxy_buffering off`.** With `stream: true`, Ollama emits tokens as they are made.
  Buffering would hold them and deliver the answer in one lump, defeating streaming.
- **`proxy_read_timeout 300s`.** Nginx's 60 s default would return `504` on a slow
  model-load-plus-generate. CPU inference legitimately exceeds it.
- **`limit_req`.** A cheap brake against scanners and runaway client loops.
- **`/healthz` with `auth_basic off`.** An unauthenticated liveness endpoint that leaks
  nothing about Ollama, so uptime monitors don't need credentials.

### 6. Let's Encrypt in one paragraph

Certbot proves you control the domain via the **HTTP-01 challenge**: Let's Encrypt fetches
a token from `http://<domain>/.well-known/acme-challenge/...` on **port 80**, so you need
(a) a real DNS name pointing at the VPS and (b) port 80 open. No domain? Names like
`203-0-113-7.sslip.io` resolve to the embedded IP and work. `certbot --nginx` edits the
server block to add the 443 listener and redirect, and installs a timer that renews the
90-day certificate. That is why `ollama.nginx.conf` is HTTP-only when first installed --
`nginx -t` would fail if it referenced certificate files that don't exist yet.

### 7. Swapping the LLM client (`app/llm.py`)

Because Ollama speaks the OpenAI wire format, "swapping the client" is a config change,
not a rewrite: `LLM_PROVIDER=ollama` selects `base_url=$OLLAMA_BASE_URL/v1` and
`model=$OLLAMA_MODEL`. One real wrinkle: the `openai` SDK always sends
`Authorization: Bearer <api_key>`, but Nginx wants `Authorization: Basic ...`. The fix is
to hand the SDK an `httpx.Client(auth=httpx.BasicAuth(user, password))`; httpx applies
auth at send time and overwrites the header, so the Bearer placeholder never reaches
Nginx. `tests/test_llm.py` proves this against a real local HTTP server rather than
trusting the reading of the SDK source.

### 8. Comparing quality fairly with RAGAS

`evals/compare_models.py` runs the same 8 golden questions through both backends and
reports retrieval hit rate, RAGAS Faithfulness, latency, and tokens/s. Design choices
that make the comparison honest:

- **Same retrieval for both.** Retrieval is BM25, independent of the LLM, so any
  difference in Faithfulness is attributable to generation.
- **Fixed judge.** Faithfulness is always judged by OpenAI, whichever model *wrote* the
  answer. If the 3B model graded itself, a weak judge could hide exactly the gap you are
  trying to measure.
- **Read Faithfulness correctly.** It measures whether the answer is *supported by the
  retrieved context*, not whether it is *correct*. Small models tend to fail it by adding
  plausible but unsupported detail, or by ignoring "answer only from the context".
- **n=8 is tiny.** One question flipping moves the mean by ~0.12. Treat differences under
  ~0.1-0.15 as noise; look at per-case output (`--out results.json`) before concluding.
- **The hardened system prompt from Week 7 is reused unchanged.** A 3B model follows
  multi-rule instructions less reliably than `gpt-4o-mini`; if it fails the "say you don't
  know" rule, that is a finding, not a bug in the harness.

## Why it matters in production

- **Data residency and vendor risk** are the main real-world drivers: regulated data,
  contractual "no third-party processing" clauses, air-gapped sites.
- **Hybrid routing** is the common end state, not all-or-nothing: send routine or
  sensitive traffic to the self-hosted model and hard queries to a frontier API. This week
  builds the switch that makes that routing possible.
- **What breaks if you get it wrong:** an open port 11434 (free compute for strangers),
  basic auth over HTTP (leaked password), a 60 s proxy timeout (intermittent 504s that
  look like model failures), a too-small context window (see pitfalls), and a box with no
  RAM headroom (OOM kills mid-request).

## Tradeoffs and comparisons

| | Hosted API (gpt-4o-mini) | Ollama 3B on 4 GB VPS |
|---|---|---|
| Latency (typical RAG answer) | ~1 s | seconds to tens of seconds |
| Answer quality | Strong instruction following | Noticeably weaker; more unsupported claims |
| Cost model | Per token | Fixed monthly |
| Data leaves your infra | Yes | No (still on the VPS provider's hardware) |
| Concurrency | Effectively unlimited | ~1 request at a time |
| Ops burden | None | You: OS patches, TLS renewals, monitoring, backups of config |

**Basic auth vs alternatives:** basic auth is the simplest thing that works and fits this
week. Its limits: one shared static secret, revocation means editing the file, no
per-user audit. Stronger options: an `X-API-Key` check per client, mTLS, or -- best for
internal use -- keeping the endpoint **off the public internet** entirely with WireGuard
or Tailscale so there is nothing to attack. **Caddy** is a fair Nginx substitute that
obtains and renews certificates automatically (fewer moving parts than certbot).

## Common pitfalls

1. **Believing the 2 GB claim.** See section 2. Symptom: the process is killed or the box
   crawls in swap.
2. **Small default context window.** Ollama's default `num_ctx` has historically been
   small (2048 in older releases, 4096 later; newer versions expose
   `OLLAMA_CONTEXT_LENGTH`). If a prompt exceeds it, older tokens are silently dropped --
   for RAG that can mean the retrieved passage is truncated away and the model "doesn't
   know". Check your version's behaviour and set it explicitly if answers look context-blind.
3. **Exposing 11434.** Bind to loopback; firewall it; only Nginx faces the internet.
4. **Bearer vs Basic header clash** (section 7).
5. **Judging the 3B model with itself** (section 8).
6. **First-request latency read as steady-state.** Warm the model before benchmarking.
7. **Thinking-mode models.** Some Qwen3 variants emit reasoning text before the answer; that
   inflates tokens/latency and can pollute Faithfulness scoring. Disable thinking or strip
   it if you try them.
8. **Certbot before DNS/port 80 is ready.** Repeated failures hit Let's Encrypt rate limits.

## Check yourself

1. Why does a "3B model in 2 GB RAM" plan fail in practice, and what would you provision
   instead?
2. Decode speed on a CPU VPS is limited by memory bandwidth, not compute. What does that
   predict about a 1B vs a 3B model's tokens/s, and about adding more vCPUs?
3. Basic auth is only a few lines of Nginx config -- why is it unsafe without HTTPS, and
   what does Let's Encrypt's HTTP-01 challenge require of your server?
4. The OpenAI SDK sends a Bearer header but Nginx expects Basic. How does this project make
   both work, and how would you test it without a real VPS?
5. At roughly what request volume does the €5 VPS beat the API on cost, and what
   constraint stops it from scaling far past that?
6. Why does the eval harness judge both providers with OpenAI instead of letting each model
   score itself? What can Faithfulness *not* tell you about the answers?
