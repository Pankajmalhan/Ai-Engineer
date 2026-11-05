# Langfuse wiring shared by function.tf and service.tf -- same shape as Week 9's cloud_run.tf
# locals, but each target gets its own DEPLOY_TARGET / LANGFUSE_TRACING_ENVIRONMENT value so
# Langfuse alerts and dashboards can tell the function's traffic from the service's.
locals {
  langfuse_secrets = var.enable_langfuse ? [
    { name = "LANGFUSE_PUBLIC_KEY", secret = "langfuse-public-key", version = "latest" },
    { name = "LANGFUSE_SECRET_KEY", secret = "langfuse-secret-key", version = "latest" },
  ] : []

  secret_env_vars = concat(var.secret_env_vars, local.langfuse_secrets)

  _langfuse_url = var.enable_langfuse ? { LANGFUSE_BASE_URL = var.langfuse_base_url } : {}

  function_env_vars = merge(
    { DEPLOY_TARGET = "cloud-run-function", LANGFUSE_TRACING_ENVIRONMENT = "cloud-run-function" },
    local._langfuse_url,
  )
  service_env_vars = merge(
    { DEPLOY_TARGET = "cloud-run-service", LANGFUSE_TRACING_ENVIRONMENT = "cloud-run-service" },
    local._langfuse_url,
  )
}
