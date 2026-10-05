#!/usr/bin/env bash
# Pulls an extra model onto the deployed Ollama server through Nginx -- no redeploy needed.
# The pull streams progress, so Nginx's 300 s read timeout resets on every chunk and a
# multi-GB download is fine.
#
#   ./scripts/pull_model.sh qwen2.5:14b-instruct
#
# The server URL and credentials come from, in order: the environment (BASIC_AUTH_USER /
# BASIC_AUTH_PASSWORD, OLLAMA_BASE_URL), then project/.env (OLLAMA_BASIC_AUTH_USER,
# OLLAMA_BASIC_AUTH_PASSWORD, OLLAMA_BASE_URL). Explicit form still works:
#   BASIC_AUTH_USER=rag BASIC_AUTH_PASSWORD=... ./scripts/pull_model.sh https://host qwen2.5:14b-instruct
#
# Mind the VM's disk (boot_disk_gb, default 50) and GPU memory: a Q4 model needs roughly
# 0.6 GB of VRAM per billion parameters, plus KV cache for each parallel slot.
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Read ONE key from .env without sourcing the file (it is not guaranteed to be valid bash).
env_value() {
  [[ -f "$PROJECT_DIR/.env" ]] || return 0
  grep -E "^$1=" "$PROJECT_DIR/.env" | tail -1 | sed -e "s/^$1=//" -e 's/^"//' -e 's/"$//' || true
}

# One argument = the model; two = <base-url> <model>.
if [[ $# -eq 1 ]]; then
  MODEL="$1"
  BASE_URL="${OLLAMA_BASE_URL:-$(env_value OLLAMA_BASE_URL)}"
elif [[ $# -eq 2 ]]; then
  BASE_URL="$1"
  MODEL="$2"
else
  echo "usage: pull_model.sh [<base-url>] <model>" >&2
  exit 2
fi

[[ -n "$BASE_URL" ]] || { echo "No server URL: pass it as the first argument, or set OLLAMA_BASE_URL (env or .env)" >&2; exit 2; }
BASE_URL="${BASE_URL%/}"
USER_="${BASIC_AUTH_USER:-$(env_value OLLAMA_BASIC_AUTH_USER)}"
PASS_="${BASIC_AUTH_PASSWORD:-$(env_value OLLAMA_BASIC_AUTH_PASSWORD)}"
[[ -n "$USER_" && -n "$PASS_" ]] || { echo "No credentials: set BASIC_AUTH_USER/BASIC_AUTH_PASSWORD or OLLAMA_BASIC_AUTH_* in .env" >&2; exit 2; }

echo "Pulling $MODEL on $BASE_URL (this can take several minutes)..."
curl -sS --no-buffer --max-time 3600 -u "$USER_:$PASS_" "$BASE_URL/api/pull" \
  -d "{\"model\":\"$MODEL\",\"stream\":true}" \
  | python3 -u -c '
import sys, json
last = ""
for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    d = json.loads(line)
    if "error" in d:
        print("\nERROR: " + d["error"]); sys.exit(1)
    status = d.get("status", "")
    if d.get("total") and d.get("completed") is not None:
        status += " %.0f%%" % (100.0 * d["completed"] / d["total"])
    if status != last:
        print(status); last = status
print("done")
'
echo
echo "Installed models:"
curl -sS -u "$USER_:$PASS_" "$BASE_URL/api/tags" | python3 -c '
import sys, json
for m in json.load(sys.stdin)["models"]:
    print("  %-34s %.1f GB" % (m["name"], m["size"] / 1e9))
'
