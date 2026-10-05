resource "google_compute_security_policy" "app" {
  name        = "${var.service_name}-armor-policy"
  description = "Cloud Armor policy in front of the Northwind RAG Cloud Run service."
  type        = "CLOUD_ARMOR"

  advanced_options_config {
    json_parsing = "STANDARD"
    log_level    = "NORMAL"
  }

  # Required catch-all: without an explicit lowest-priority rule, Cloud Armor still
  # defaults to allow, but every policy must define this rule per the provider schema.
  rule {
    action      = "allow"
    priority    = 2147483647
    description = "Default allow"
    match {
      versioned_expr = "SRC_IPS_V1"
      config {
        src_ip_ranges = ["*"]
      }
    }
  }

  # Rate-based ban: casual scraping/abuse from a single source gets throttled before it
  # ever reaches an autoscaled Cloud Run instance (cost + noisy-neighbor protection, not
  # just a security control).
  rule {
    action      = "throttle"
    priority    = 1000
    description = "Throttle high-rate single-source traffic"
    match {
      versioned_expr = "SRC_IPS_V1"
      config {
        src_ip_ranges = ["*"]
      }
    }
    rate_limit_options {
      conform_action = "allow"
      exceed_action  = "deny(429)"
      enforce_on_key = "IP"
      rate_limit_threshold {
        count        = 100
        interval_sec = 60
      }
    }
  }

  # OWASP preconfigured WAF rules: SQLi/XSS payloads never reach /chat's LLM-backed
  # handler. This blocks the transport-layer attack; app/llm.py's prompt-injection
  # defenses (Week 7) are a separate, complementary layer for payloads that arrive as
  # legitimate-looking natural language instead.
  rule {
    action      = "deny(403)"
    priority    = 1001
    description = "Block SQL injection payloads"
    match {
      expr {
        expression = "evaluatePreconfiguredWaf('sqli-v33-stable')"
      }
    }
  }

  rule {
    action      = "deny(403)"
    priority    = 1002
    description = "Block XSS payloads"
    match {
      expr {
        expression = "evaluatePreconfiguredWaf('xss-v33-stable')"
      }
    }
  }
}
