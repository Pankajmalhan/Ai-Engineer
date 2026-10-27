# Week 11 resources

## Given

- Primary: Ollama GitHub README -- "REST API" section
- Secondary: Nginx basic auth setup guide (no specific URL was supplied)
- Suggested reading from the roadmap's Aug 2026 update note:
  - "Ollama behind a reverse proxy with Caddy/Nginx for HTTPS streaming"
  - "How to Run Ollama on a VPS -- self-hosted LLM inference"
  (titles only -- no URLs were included in the paste, so none are invented here)
- Update note from the roadmap: Ollama and the Nginx reverse-proxy pattern are stable;
  Qwen3 and Gemma 3 variants are now commonly recommended for VPS-class hardware
  alongside Llama 3.2 / Mistral. `concept.md` and the project's `OLLAMA_MODEL` setting
  both make the model swappable for that reason.

## Added by Claude (fills in the pieces the given list doesn't point to)

- Ollama API reference (native `/api/generate`, `/api/chat`, `/api/tags`):
  https://github.com/ollama/ollama/blob/main/docs/api.md
- Ollama OpenAI-compatibility notes (the `/v1/chat/completions` route this week's
  `app/llm.py` uses): https://github.com/ollama/ollama/blob/main/docs/openai.md
- Ollama FAQ (server env vars such as `OLLAMA_HOST`, `OLLAMA_KEEP_ALIVE`,
  `OLLAMA_NUM_PARALLEL`; context-length behaviour; running behind a proxy):
  https://github.com/ollama/ollama/blob/main/docs/faq.md
- Nginx `ngx_http_auth_basic_module`:
  https://nginx.org/en/docs/http/ngx_http_auth_basic_module.html
- Nginx `ngx_http_proxy_module` (`proxy_buffering`, `proxy_read_timeout`):
  https://nginx.org/en/docs/http/ngx_http_proxy_module.html
- Let's Encrypt challenge types (why HTTP-01 needs port 80 and a real DNS name):
  https://letsencrypt.org/docs/challenge-types/
- Certbot instructions generator (Nginx + your distro): https://certbot.eff.org/
