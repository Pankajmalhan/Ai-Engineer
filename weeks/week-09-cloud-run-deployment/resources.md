# Week 9 resources

## Given

- Primary: Google Cloud Run documentation -- "Deploying container images" and
  "Configuring auto-scaling"
  - https://docs.cloud.google.com/run/docs/deploying
  - https://docs.cloud.google.com/run/docs/configuring/min-instances
  - https://docs.cloud.google.com/run/docs/configuring/max-instances
  - https://docs.cloud.google.com/run/docs/configuring/scaling-controls (target
    CPU/concurrency utilization -- this is the doc that turned out to describe
    template annotations, not a `gcloud run deploy` flag; see `concept.md`)
- Secondary: Docker Best Practices for Python applications

## Added by Claude (thin on Terraform/Cloud Armor specifics, so these fill that in)

- Terraform Google provider docs for the resources this week's `terraform/` uses:
  `google_cloud_run_v2_service`, `google_compute_region_network_endpoint_group`,
  `google_compute_backend_service`, `google_compute_security_policy` (Cloud Armor) --
  https://registry.terraform.io/providers/hashicorp/google/latest/docs
- `google-github-actions/deploy-cloudrun` and `google-github-actions/auth` (Workload
  Identity Federation) README, for the CI deploy pattern --
  https://github.com/google-github-actions/deploy-cloudrun
