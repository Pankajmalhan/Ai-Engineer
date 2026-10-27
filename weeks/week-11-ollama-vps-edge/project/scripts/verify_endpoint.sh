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
EXPECT_GPU="${EXPECT_GPU:-0}"          # 1 = fail unless the model runs fully on a GPU
MIN_GPU_TOKENS_PER_SEC="${MIN_GPU_TOKENS_PER_SEC:-20}"   # CPU on e2-medium measured ~4.5
FAIL=0

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

echo
echo "7. decode speed (native API, 80-token generation) --"
curl -sS --max-time 300 -u "$USER_:$PASS_" "$BASE_URL/api/generate" \
  -d "{\"model\":\"$MODEL\",\"prompt\":\"Write two sentences about the sea.\",\"stream\":false,\"options\":{\"num_predict\":80}}" \
  | EXPECT_GPU="$EXPECT_GPU" MIN_TPS="$MIN_GPU_TOKENS_PER_SEC" python3 -c '
import sys, json, os
d = json.load(sys.stdin)
n = 1e9
tps = d["eval_count"] / (d["eval_duration"] / n)
print("prefill %d tok in %.2fs | decode %d tok in %.2fs = %.1f tokens/s" % (d["prompt_eval_count"], d["prompt_eval_duration"] / n, d["eval_count"], d["eval_duration"] / n, tps))
if os.environ["EXPECT_GPU"] == "1" and tps < float(os.environ["MIN_TPS"]):
    print("FAIL: %.1f tokens/s is below %s -- that is CPU speed, not GPU speed" % (tps, os.environ["MIN_TPS"]))
    sys.exit(1)
' || FAIL=1

echo
echo "8. where the model is placed (/api/ps) --"
curl -sS --max-time 30 -u "$USER_:$PASS_" "$BASE_URL/api/ps" \
  | EXPECT_GPU="$EXPECT_GPU" python3 -c '
import sys, json, os
models = json.load(sys.stdin).get("models", [])
if not models:
    print("no model loaded"); sys.exit(1)
ok = True
for m in models:
    size, vram = m.get("size", 0), m.get("size_vram", 0)
    pct = 100.0 * vram / size if size else 0.0
    print("%s: %.0f%% in VRAM (%.2f of %.2f GB)" % (m["name"], pct, vram / 1e9, size / 1e9))
    ok = ok and pct >= 99.0
if os.environ["EXPECT_GPU"] == "1" and not ok:
    print("FAIL: the model is not fully in VRAM -- Ollama is using the CPU for part or all of it")
    sys.exit(1)
' || FAIL=1

if [ "$EXPECT_GPU" = "1" ]; then
  [ "$FAIL" = "0" ] && echo && echo "GPU CHECKS PASSED" || { echo; echo "GPU CHECKS FAILED"; exit 1; }
fi
