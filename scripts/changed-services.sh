#!/bin/sh
# Print, as a compact JSON array, the services whose source changed between BASE and HEAD:
#   scripts/changed-services.sh <BASE>      e.g. ["order-service","payment-service"]
# Every service is listed when BASE is empty, all zeros (first push of a branch), or not in
# the local history (shallow clone, force push): rebuilding is the safe fallback.
set -eu

BASE="${1:-}"
SERVICES_DIR="${SERVICES_DIR:-services}"

all=$(find "$SERVICES_DIR" -mindepth 1 -maxdepth 1 -type d -exec basename {} \; | sort)

case "$BASE" in
  "" | *[!0]*) ;;
  *) BASE="" ;;   # 0000…: no previous commit
esac

if [ -n "$BASE" ] && git cat-file -e "$BASE^{commit}" 2>/dev/null; then
  changed=$(git diff --name-only "$BASE" HEAD -- "$SERVICES_DIR" \
    | awk -F/ 'NF > 2 { print $2 }' | sort -u)
  # Keep only directories that still exist (a deleted service has nothing to build).
  services=""
  for svc in $changed; do
    [ -d "$SERVICES_DIR/$svc" ] && services="$services$svc
"
  done
else
  services=$all
fi

printf '%s\n' "$services" | jq -R . | jq -sc 'map(select(length > 0))'
