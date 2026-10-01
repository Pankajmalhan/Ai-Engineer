#!/usr/bin/env bash
# Checks a deployed Ollama endpoint from outside the VPS: TLS, the auth gate, native
# generation, and the OpenAI-compatible route the FastAPI service uses.
#
#   BASIC_AUTH_USER=rag BASIC_AUTH_PASSWORD=... ./scripts/verify_endpoint.sh https://ollama.example.com
set -euo pipefail

BASE_URL="${1:?usage: verify_endpoint.sh <base-url>}"
BASE_URL="${BASE_URL%/}"
USER_="${BASIC_AUTH_USER:?set BASIC_AUTH_USER}"
PASS_="${BASIC_AUTH_PASSWORD:?set BASIC_AUTH_PASSWORD}"
MODEL="${OLLAMA_MODEL:-llama3.2:3b}"

code() { curl -s -o /dev/null -w '%{http_code}' "$@"; }

echo "1. /healthz is open ................ $(code "$BASE_URL/healthz") (want 200)"
echo "2. no credentials is rejected ...... $(code "$BASE_URL/api/tags") (want 401)"
echo "3. wrong password is rejected ...... $(code -u "$USER_:wrong" "$BASE_URL/api/tags") (want 401)"
echo "4. right credentials list models ... $(code -u "$USER_:$PASS_" "$BASE_URL/api/tags") (want 200)"

echo
echo "5. native /api/generate (first call may be slow: model load) --"
curl -sS --max-time 300 -u "$USER_:$PASS_" "$BASE_URL/api/generate" \
  -d "{\"model\":\"$MODEL\",\"prompt\":\"Reply with the single word: pong\",\"stream\":false}" \
  | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d["response"].strip(), "| eval tokens:", d.get("eval_count"))'

echo
echo "6. OpenAI-compatible /v1/chat/completions (what app/llm.py calls) --"
curl -sS --max-time 300 -u "$USER_:$PASS_" "$BASE_URL/v1/chat/completions" \
  -H 'Content-Type: application/json' \
  -d "{\"model\":\"$MODEL\",\"messages\":[{\"role\":\"user\",\"content\":\"Reply with the single word: pong\"}],\"temperature\":0}" \
  | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d["choices"][0]["message"]["content"].strip(), "| usage:", d["usage"])'
