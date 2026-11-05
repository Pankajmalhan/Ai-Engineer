# Week 9: Containerised Cloud Run deployment

## Overview

Weeks 5-8 built and hardened a RAG service running only ever as `uv run uvicorn` on
your own machine. This week turns it into something a real user could actually hit:
packaged as a container image, running on Google Cloud Run (a serverless container
platform that scales instances up and down based on traffic, including to zero), and
fronted by a Load Balancer with a Web Application Firewall (Cloud Armor) so the public
internet never talks to Cloud Run directly. This is the last mile between "code that
works on my machine" and "a service other people can depend on" -- and it's where a
surprising amount of production incidents actually originate, not in the RAG logic
itself.

## Core concept, in depth

### Containerising: what a "production Dockerfile" actually means

A Dockerfile that merely runs your app and a Dockerfile that's safe to run in
production differ in a few specific ways, all present in this week's `project/Dockerfile`:

- **Multi-stage builds.** Stage 1 (`builder`) installs `uv`, resolves dependencies, and
  compiles bytecode. Stage 2 (`runtime`) copies only the resulting virtualenv and your
  app code -- not `uv` itself, not the lockfile, not pip's build cache. The shipped
  image is smaller (faster cold starts on Cloud Run, since Cloud Run has to pull the
  image before a new instance can serve traffic) and has less attack surface (no build
  tooling an attacker could abuse if they got a shell).
- **Non-root user.** Containers run as `root` by default unless you say otherwise. If
  an attacker achieves code execution inside your container (a dependency
  vulnerability, a deserialization bug), running as root gives them a much larger blast
  radius -- write access to most of the filesystem, more kernel attack surface. A
  dedicated `appuser` (fixed UID, no shell, no home directory) costs three lines and
  removes a whole class of privilege escalation.
- **A health check endpoint.** `/health` (already existed in `app/main.py` since Week
  8's tracing work) is what an orchestrator polls to decide "is this instance actually
  ready to serve traffic, or should I kill it and start a new one." Cloud Run has its
  own separate startup/liveness probe configuration (not the Docker `HEALTHCHECK`
  instruction -- see below), but the endpoint itself is the same one either mechanism
  hits.
- **Listening on `$PORT`, not a fixed port.** Cloud Run injects a `PORT` environment
  variable into every container and expects it to bind there; a hardcoded `--port 8000`
  works locally and silently breaks in Cloud Run. This is why the Dockerfile's `CMD` is
  written in *shell form* (`CMD exec gunicorn ... --bind :$PORT`), not the usual
  recommended *exec form* (`CMD ["gunicorn", ...]`) -- exec form doesn't invoke a shell,
  so `$PORT` would never get expanded and the container would try to bind to the
  literal string `:$PORT`.

One subtlety worth sitting with: Docker's own `HEALTHCHECK` instruction and Cloud Run's
health checking are two unrelated mechanisms. `HEALTHCHECK` only affects what
`docker ps`/`docker inspect` report and is entirely a local-Docker/Compose concept;
Cloud Run does not read it and configures startup/liveness probes of its own (via
`gcloud run deploy --*-probe-*` flags or the service YAML). It's still worth keeping in
the Dockerfile because you (and CI) run this image locally with plain `docker run`
too, and `docker inspect --format='{{.State.Health.Status}}'` is a genuinely useful
local smoke check.

### Cloud Run's autoscaling model

Cloud Run scales the number of running **instances** of your container, and it can
scale a service down to zero instances when idle (no cost while idle) or up to a
configured maximum under load. Two independent knobs govern *when* it adds another
instance:

- **Concurrency**: how many simultaneous requests one instance is allowed to handle
  before Cloud Run considers it "full" and routes the next request to a new instance
  (or queues it, if at `max-instances`).
- **Target CPU utilization** (this week's "CPU 60% target"): once an instance's CPU
  usage crosses this threshold, Cloud Run scales out rather than piling more concurrent
  requests onto an already-busy instance. This is configured via *template
  annotations* (`run.googleapis.com/scaling-cpu-target`), not a first-class Terraform
  field on `google_cloud_run_v2_service.template.scaling` as of the provider version
  this project pins (`~> 6.0`) -- the Terraform docs describe `cpu_utilization`/
  `concurrency_utilization` fields, but they aren't in the schema that version actually
  ships; see `terraform/cloud_run.tf`'s comment for how this was actually confirmed
  (by inspecting `terraform providers schema -json`, not by trusting the docs example
  as-is).

`min-instances=1` keeps one instance warm at all times -- this is what eliminates cold
starts for the *first* request after idle, at the cost of paying for that instance
continuously (Cloud Run calls this "instance-based billing" once `min_instance_count >
0`). `max-instances=10` is a cost/blast-radius ceiling: without it, a traffic spike (or
an attack) could scale unboundedly and run up an unbounded bill, which is also exactly
why Cloud Armor's rate limiting sits in front of this, not just Cloud Run's own scaling.

### Why a Load Balancer and Cloud Armor in front of a service that already has a public URL

Every Cloud Run service gets a public `*.run.app` HTTPS URL for free, so it's a fair
question why this week adds an external Load Balancer and Cloud Armor on top of that.
Three concrete reasons, all realized in `terraform/`:

1. **A WAF needs something to attach to.** Cloud Armor (`google_compute_security_policy`)
   attaches to a *backend service*, which is a Load Balancer concept -- there's no way
   to attach a WAF or rate-limiting policy directly to a bare Cloud Run URL.
2. **Closing the direct-access bypass.** Setting Cloud Run's `ingress` to
   `INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER` makes the `*.run.app` URL reject direct
   requests entirely -- traffic *must* come through the LB, so Cloud Armor is a real
   enforcement point, not a WAF that a determined client could just route around by
   hitting `*.run.app` directly.
3. **A stable frontend for a rolling backend.** The LB's IP is what you'd point a real
   domain at; Cloud Run revisions come and go underneath it without the public entry
   point changing.

The mechanism connecting the two is a **serverless Network Endpoint Group (NEG)**
(`google_compute_region_network_endpoint_group`, `network_endpoint_type = "SERVERLESS"`)
-- Cloud Run has no VM or instance group of its own for a backend service to point at,
so a serverless NEG is Google's adapter that lets a `google_compute_backend_service`
treat "traffic to this Cloud Run service" as if it were a normal backend. Because
Cloud Run manages its own instance health, the backend service needs no
`health_checks` block, unlike a VM-backed one.

### Rolling deployments and traffic splitting

Every `gcloud run deploy` (or `google_cloud_run_v2_service` update) creates a new
**revision** -- Cloud Run's immutable snapshot of one deploy. By default a new revision
gets 100% of traffic the moment it's ready (this project's current setup, and its
current gap -- see the project README's "what's out of scope" section). Production
rollouts usually want a **canary**: send 5-10% of traffic to the new revision, watch
error rates/latency, then shift the rest -- Cloud Run supports this natively via a
`traffic` split by revision name and percentage, without needing separate
infrastructure. The tradeoff is entirely operational complexity vs. blast radius: a bad
revision at 100% traffic immediately affects every user; the same bad revision at 5%
affects a small fraction while you notice and roll back.

## Why it matters in production

A RAG pipeline that's correct, evaluated, and red-teamed (Weeks 5-8) is still not a
service anyone else can use until it survives contact with: cold starts under bursty
traffic, a scraper hammering it from one IP, a SQLi payload in the `question` field
aimed at whatever's downstream, and a bad deploy that silently serves wrong answers.
Each of those maps directly onto something built this week -- `min-instances`,
Cloud Armor rate limiting, the WAF rules, and the parity check, respectively. None of
this is generic "best practice" cargo-culting; each piece exists because of a specific
failure mode it closes.

## Tradeoffs & comparisons

- **Cloud Run vs. GKE (Kubernetes).** Cloud Run trades control (no custom scheduling,
  no sidecars beyond what Cloud Run itself offers, no arbitrary networking) for
  operational simplicity -- no cluster to patch, no node pools to size, scale-to-zero
  out of the box. Right choice here because this is a single stateless HTTP service;
  GKE earns its complexity when you have many services needing shared infra
  (service mesh, custom autoscaling logic, DaemonSets) that Cloud Run can't express.
- **`min-instances=1` vs. `min-instances=0`.** Zero cost at idle vs. zero cold-start
  latency for the first request. A low-traffic internal tool wants 0; anything with an
  SLA on first-byte latency wants at least 1.
- **CPU-based vs. concurrency-based scaling target.** CPU-based scaling reacts to
  actual compute pressure (good for CPU-bound work); concurrency-based reacts to
  request count regardless of how expensive each request is (good when request cost is
  uniform). This service sets both (`cpu_utilization` at 0.6 via annotation,
  `concurrency_utilization` at 0.6) since `/chat` requests are I/O-bound (waiting on
  OpenAI) but not free CPU-wise (BM25 retrieval, JSON serialization).
- **Terraform-owned image reference vs. `gcloud run deploy` in CI.** This project has
  Terraform apply the image tag (`var.image`), so `terraform plan` always accurately
  reflects what's running. The simpler, more common alternative is letting CI's
  `gcloud run deploy`/`deploy-cloudrun` action manage revisions directly and letting
  Terraform manage everything *except* the image -- less coupling between infra and
  app deploys, but then `terraform plan` can drift from reality (it thinks the image is
  whatever was last applied, even if a manual `gcloud run deploy` since changed it).

## Common pitfalls

- Writing `CMD ["uvicorn", "app.main:app", "--port", "8080"]` (exec form) and expecting
  `$PORT` to expand -- it doesn't; exec form never invokes a shell.
- Forgetting `ingress = INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER` and assuming Cloud
  Armor is protecting the service, when the `*.run.app` URL is still directly reachable
  and bypasses the WAF entirely.
- Setting `min-instances > 0` without realizing this switches to instance-based billing
  (paying for the idle instance continuously), not just "a nicer cold-start experience."
- Trusting a Terraform resource's documented field names without checking them against
  the actually-installed provider version's schema (`terraform providers schema -json`)
  -- this project hit exactly this with `cpu_utilization`/`concurrency_utilization`
  being documented but not present in the pinned `~> 6.0` provider.
- Declaring "parity with local" as byte-identical LLM output. Retrieval (deterministic)
  should match exactly; generation should be quality-gated (a faithfulness threshold),
  not diffed -- treating the two the same either produces false failures (flaky CI on
  every deploy) or false confidence (an exact-match check on a field that changes
  constantly means the check verifies nothing).

## Check yourself

1. Why does the Dockerfile's `CMD` use shell form instead of the more commonly
   recommended exec form, and what would silently break if it didn't?
2. What's the actual difference between Docker's `HEALTHCHECK` instruction and the
   health checking Cloud Run itself performs -- does setting one configure the other?
3. If you removed `ingress = INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER` from the Cloud Run
   service, what attack surface would that reopen, given Cloud Armor is still attached
   to the Load Balancer?
4. Why does `min-instances=1` cost money even if the service receives zero traffic?
5. Why does this week's parity check treat retrieval and generation differently instead
   of diffing both against a local baseline the same way?
