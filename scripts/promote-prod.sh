#!/bin/sh
# Point prod at commit REVISION: pin it as prod's targetRevision in the ApplicationSet, and
# pin every service's image digest to the newest image published from main:
#   <service>:sha-<REVISION>  when the service was rebuilt at REVISION, otherwise
#   <service>:main            the last image published from main.
# For a service with no pending build, :main is the image prod already runs, so its digest
# doesn't change. A service with neither tag keeps its current digest.
#
#   REVISION=<full git sha> [REGISTRY=ghcr.io/pampatzoglou/shopflow] scripts/promote-prod.sh
#
# Needs: yq (mikefarah, v4), docker with buildx, and read access to the registry.
set -eu

: "${REVISION:?REVISION (full git commit sha) is required}"
REGISTRY="${REGISTRY:-ghcr.io/pampatzoglou/shopflow}"
APPSET="${APPSET:-deploy/argo/applicationset.yaml}"
SERVICES="${SERVICES:-order-service payment-service inventory-service}"

case "$REVISION" in
  *[!0-9a-f]* | "") echo "REVISION must be a lowercase hex commit sha: $REVISION" >&2; exit 1 ;;
esac
[ "${#REVISION}" -eq 40 ] || { echo "REVISION must be a full 40-char sha: $REVISION" >&2; exit 1; }
[ -f "$APPSET" ] || { echo "missing $APPSET" >&2; exit 1; }

PROD='(.spec.generators[].matrix.generators[].list.elements[] | select(.env == "prod"))'

[ "$(yq "[$PROD] | length" "$APPSET")" -eq 1 ] \
  || { echo "expected exactly one env: prod element in $APPSET" >&2; exit 1; }

REVISION="$REVISION" yq -i "$PROD.revision = strenv(REVISION)" "$APPSET"
echo "prod revision -> $REVISION"

# Index digest when buildx pushes attestations, manifest digest otherwise; either pins.
resolve() {
  docker buildx imagetools inspect "$1" --format '{{json .Manifest}}' 2>/dev/null | jq -er .digest
}

for svc in $SERVICES; do
  digest=""
  for ref in "$REGISTRY/$svc:sha-$REVISION" "$REGISTRY/$svc:main"; do
    if digest=$(resolve "$ref"); then break; fi
    digest=""
  done
  if [ -n "$digest" ]; then
    SVC="$svc" DIGEST="$digest" yq -i "$PROD.digests[strenv(SVC)] = strenv(DIGEST)" "$APPSET"
    echo "$svc -> $digest ($ref)"
  else
    current=$(SVC="$svc" yq "$PROD.digests[strenv(SVC)] // \"\"" "$APPSET")
    echo "$svc: not published yet, keeping ${current:-<none>}"
  fi
done
