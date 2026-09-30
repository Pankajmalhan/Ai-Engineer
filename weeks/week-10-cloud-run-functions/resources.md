# Week 10 resources

## Given

- Primary: Google Cloud Run functions (formerly Cloud Functions, 2nd gen) documentation
  -- "Deploy a container image"
  - https://docs.cloud.google.com/run/docs/deploy-functions
  - https://docs.cloud.google.com/run/docs/building/functions
- Secondary: Cold-start mitigation -- Google blog post on min-instances
  - https://docs.cloud.google.com/run/docs/configuring/min-instances

### Correction noted in the pasted brief (Aug 2026)

Google rebranded "Cloud Functions" to "Cloud Run functions" -- 2nd-gen Cloud Functions
is now folded into the Cloud Run product family. The old name still works and
redirects, but current docs use "Cloud Run functions". This project's `concept.md`
and code use the new name throughout.

- Cloud Run functions (formerly Cloud Functions) -- release notes:
  https://docs.cloud.google.com/functions/docs/2nd-gen/2nd-gen-differences
- Cloud Run vs. Cloud Run Functions -- explainer:
  https://docs.cloud.google.com/run/docs/deploy-functions

## Added by Claude

Filled in gaps the given resources didn't cover (API Gateway wiring, the exact
buildpacks-vs-Dockerfile packaging distinction this week's benchmark turned on):

- `gcloud run deploy` reference (the actual current flags: `--function`, `--source`,
  `--base-image`, `--min-instances`) --
  https://docs.cloud.google.com/sdk/gcloud/reference/run/deploy
- API Gateway + Cloud Run get-started guide (OpenAPI `x-google-backend`, service
  account IAM, `api-configs`/`gateways create`) --
  https://docs.cloud.google.com/api-gateway/docs/get-started-cloud-run
- Cloud Native Buildpacks spec, for understanding the "no such file or directory"
  launcher error this project's `deploy_service.sh` had to work around (see
  concept.md's Common pitfalls) -- https://buildpacks.io/docs/for-app-developers/concepts/launch/
