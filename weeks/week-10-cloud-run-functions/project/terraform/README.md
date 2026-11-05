# Week 10 Terraform (alternative to `../scripts/*.sh`)

Same three things `../scripts/deploy_function.sh`, `deploy_service.sh`, and
`deploy_gateway.sh` create by hand with `gcloud` -- a Cloud Run function, a Cloud
Run service (the benchmark's comparison arm), and an API Gateway in front of the
function -- expressed as Terraform instead, for practicing Terraform itself. This
week's actual measured numbers (`../benchmarks/results.md`) came from the `scripts/`
path; this module is a from-scratch alternative you deploy yourself.

**Nothing here has been applied.** Only `terraform init` and `terraform validate`
have been run against it (schema/syntax checks only, no GCP calls, no state) --
confirmed passing. `terraform plan`/`apply` need your own credentials and haven't
been run.

## Before you run it

1. **Auth**: `gcloud auth login` and `gcloud auth application-default login` --
   Terraform's `google`/`google-beta` providers read credentials from *Application
   Default Credentials*, a separate store from the plain CLI login.
2. **The secret must already exist.** This module reads `openai-api-key` from Secret
   Manager (same one `../scripts/deploy_function.sh` used) -- it doesn't create it
   (see `secrets.tf`'s comment for why). If you've already run the `scripts/` path,
   it's already there; otherwise create it first (see `../README.md`).
3. **Set `PROJECT_ID`** (and optionally `REGION`, `REPO_ID`) in your shell -- every
   script in `scripts/` reads these the same way `../../scripts/*.sh` does:
   ```bash
   export PROJECT_ID=ace-o9h0u9a21e
   export REGION=us-central1   # optional, this is already the default
   ```

## Naming -- this can coexist with what `scripts/` already deployed

Every resource here defaults to a name with a `-tf` suffix
(`northwind-rag-fn-tf`, `northwind-rag-svc-tf`, `northwind-rag-gateway-tf`, ...) --
deliberately different from what `scripts/deploy_function.sh` etc. already created
(`northwind-rag-fn`, `northwind-rag-svc`, `northwind-rag-gateway`). You can `apply`
this module without touching or colliding with the already-deployed resources this
week's benchmark numbers came from. If you'd rather Terraform *own* the same
resources instead of running both side by side, tear down the scripted ones first
(`../scripts/teardown.sh`) and override the `*_name`/`*_id` variables to match.

## Run it end-to-end -- `scripts/01` through `04`, in order

Why four steps instead of one `terraform apply`: `google_cloud_run_v2_service`
(service.tf) needs a real, already-pushed image reference, and Terraform has no
"build a Dockerfile" resource -- so the image must exist *before* the apply that
deploys it. But it also needs somewhere to be pushed *to*, and that Artifact
Registry repo is itself a Terraform resource. Steps 1-2 resolve that chicken-and-egg
problem once; steps 3-4 are the everyday plan/apply loop. (The function has none of
this trouble -- `function_source.tf` zips and uploads `../function/` for Terraform
itself, and Cloud Functions gen2's own `build_config` runs buildpacks against it
during `apply`, no separate build step needed.)

```bash
cd terraform/scripts

./01_bootstrap_registry.sh                 # creates only the Artifact Registry repo
./02_build_and_push_service_image.sh       # builds + pushes the service image into it
./03_plan.sh                               # review what will be created
./04_apply.sh                              # creates the function, service, and gateway
```

**Future deployments** (you changed `function/app/*.py` and want to redeploy both
arms): run the exact same four commands again. Each is idempotent or safely
re-runnable:
- `01_bootstrap_registry.sh` becomes a no-op ("no changes") once the repo exists.
- `02_build_and_push_service_image.sh` tags the new image with the current git SHA
  (not a fixed `v1`/`latest`) precisely so Terraform *sees* the change and deploys a
  new revision -- reusing the same tag would leave `var.service_image` unchanged
  from Terraform's point of view, and it would silently skip redeploying the service.
  The function side needs no rebuild step at all: `function_source.tf`'s zip is named
  by its own content hash, so `04_apply.sh` alone detects a code change and redeploys
  the function on the same run.
- `03_plan.sh` / `04_apply.sh` always read whatever `.last_image` currently holds
  (via `_common.sh`'s `tf_vars()`), so they never redeploy a stale image by accident.

`04_apply.sh` prints `function_url`, `service_url`, and `gateway_hostname` at the end
-- same three endpoints `../README.md`'s "What's actually deployed" section
documents for the scripted (non-Terraform) deployment.

Tear down with `./05_destroy.sh` when you're done (not `-auto-approve` -- same
confirm-before-acting habit as `04_apply.sh`).

## The raw commands, if you'd rather not use the scripts

Everything above is a thin wrapper around plain Terraform CLI calls -- worth seeing
once un-wrapped. `$IMAGE` here is whatever `02_build_and_push_service_image.sh`
would have produced (a real pushed image, SHA-tagged, not `:v1`/`:latest` -- see the
future-deployments note above for why that tag choice matters):

```bash
terraform init -input=false

# Step 1: bootstrap the registry alone
terraform apply -target=google_artifact_registry_repository.app \
  -var="project_id=$PROJECT_ID" -var="service_image=placeholder"

# Step 2: build + push (plain gcloud, no terraform involved)
IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/northwind-rag-tf/northwind-rag-svc-tf:$(git rev-parse --short HEAD)"
gcloud builds submit --tag="$IMAGE" --project="$PROJECT_ID" ../function

# Steps 3-4: plan, then apply, now that the image is real
terraform plan  -var="project_id=$PROJECT_ID" -var="service_image=$IMAGE"
terraform apply -var="project_id=$PROJECT_ID" -var="service_image=$IMAGE"

# Teardown
terraform destroy -var="project_id=$PROJECT_ID" -var="service_image=$IMAGE"
```

Or drop a `terraform.tfvars` (gitignored -- see repo root `.gitignore`) instead of
repeating `-var` flags on every command:
```hcl
project_id    = "ace-o9h0u9a21e"
service_image = "us-central1-docker.pkg.dev/ace-o9h0u9a21e/northwind-rag-tf/northwind-rag-svc-tf:abc1234"
```
then just `terraform plan` / `terraform apply` -- though you'd need to edit this file
by hand after every rebuild, which is exactly the bookkeeping `.last_image` +
`_common.sh`'s `tf_vars()` automate for you in the scripted path.

## What you'll notice is different from the `scripts/` path

- **No separate render-then-create step for the gateway.** `scripts/deploy_gateway.sh`
  has to `envsubst` the function's URL into `gateway/openapi.yaml` *after* the
  function exists, because bash has no way to know that URL ahead of time. Terraform
  doesn't have this problem: `gateway.tf`'s `templatefile(...)` call references
  `google_cloudfunctions2_function.rag.url` directly, and Terraform's own dependency
  graph sequences "create the function, then render the spec with its real URL, then
  create the api config" for you -- see the plan output's resource ordering.
- **`google_cloudfunctions2_function` requires a GCS-uploaded source zip**
  (`function_source.tf`), where `gcloud run deploy --source .` just reads a local
  directory. This is the one place the CLI does noticeably more for you than the
  Terraform resource does.
- **Destroying this is one command** (`05_destroy.sh`), and removes everything
  including the content-addressed GCS source bucket. Note that destroying
  `google_artifact_registry_repository.app` deletes the *whole repository*, images
  included -- Artifact Registry doesn't support deleting an empty repo shell while
  keeping images around. If you want to keep the images, remove that resource from
  state first (`terraform state rm`) or target-destroy around it.
