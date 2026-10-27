#!/usr/bin/env bash
# Step 0 (GPU deploys). New projects usually have GPU quota 0, and the failure only shows
# up at apply time as a quota error. This checks, up front, that the zone offers the GPU
# and that the project's quota allows at least one.
#
#   GPU=nvidia-l4 (default) | nvidia-tesla-t4        ZONE=us-central1-a
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

PROJECT_ID="${PROJECT_ID:?set PROJECT_ID}"
ZONE="${ZONE:-us-central1-a}"
REGION="${REGION:-${ZONE%-*}}"
GPU="${GPU:-nvidia-l4}"

echo "Zone $ZONE -- does it offer $GPU?"
# List the zone's accelerators and match the name exactly here (gcloud's own --filter on
# `name=` prints a deprecation warning about changing semantics).
if gcloud compute accelerator-types list --project="$PROJECT_ID" \
     --filter="zone:($ZONE)" --format="value(name)" | grep -qx "$GPU"; then
  echo "  yes"
else
  echo "  NO. Find a zone that offers it:" >&2
  echo "    gcloud compute accelerator-types list --project=$PROJECT_ID --format='value(zone.basename(),name)' | grep $GPU" >&2
  exit 1
fi

echo "Quota in $REGION:"
gcloud compute regions describe "$REGION" --project="$PROJECT_ID" --format=json | python3 -c '
import sys, json, re

gpu = sys.argv[1]
want = {"nvidia-l4": "NVIDIA_L4_GPUS", "nvidia-tesla-t4": "NVIDIA_T4_GPUS"}.get(gpu, "GPUS")
rows = [q for q in json.load(sys.stdin)["quotas"] if re.search(r"GPU", q["metric"])]
hit = [q for q in rows if q["metric"] == want]
for q in rows:
    if q["limit"] > 0 or q["metric"] == want:
        print("  %-34s limit %-4g used %g" % (q["metric"], q["limit"], q["usage"]))
if not hit or hit[0]["limit"] - hit[0]["usage"] < 1:
    print()
    print("No free " + want + " quota. Request an increase: Console > IAM & Admin > Quotas,")
    print("filter on " + want + ", pick this region, ask for 1 (also GPUS_ALL_REGIONS if it is 0).")
    print("Approval can take minutes to days.")
    sys.exit(1)
print()
print("OK: quota available.")
' "$GPU"
