#!/bin/sh
# Toolchain parity: devbox (devbox.json + devbox.lock) is the source of truth; CI and the
# devcontainer must install exactly what devbox.lock resolved.
#
# Sources of pins:
#   .github/actions/setup-tools/action.yml  version: 1.2.3  # devbox.json: x@1.2
#   .devcontainer/devcontainer.json         "version": "1.2.3", // devbox.json: x@1.2
#                                           (a feature; `(major)` after the spec accepts a
#                                           major-only pin, for features that can't pin more)
#   the devcontainer image's Dockerfile     ARG X_VERSION=1.2.3, mapped below. Fetched from
#                                           pampatzoglou/devcontainer at the commit in the
#                                           image tag; IMAGE_DOCKERFILE=<path> to use a local copy.
# For every pin, check that:
#   1. devbox.json declares <pkg>@<constraint> (the annotation isn't stale),
#   2. the pin equals the version devbox.lock resolved for it. A build suffix on top of the
#      locked version is accepted.
# And that every devbox package is in the devcontainer (image or a feature), and that each
# setup-tools sha256 is set, and identical to the image's when annotated `# Dockerfile: <ARG>`.
set -eu

ACTION="${ACTION:-.github/actions/setup-tools/action.yml}"
DEVCONTAINER="${DEVCONTAINER:-.devcontainer/devcontainer.json}"
DEVBOX="${DEVBOX:-devbox.json}"
LOCK="${LOCK:-devbox.lock}"
UPSTREAM="pampatzoglou/devcontainer"

# devbox package -> version ARG in the image's Dockerfile.
IMAGE_TOOLS="
go-task TASK_VERSION
jq JQ_VERSION
yq-go YQ_VERSION
kubectl KUBECTL_VERSION
kubernetes-helm HELM_VERSION
kind KIND_VERSION
istioctl ISTIO_VERSION
skaffold SKAFFOLD_VERSION
kubeconform KUBECONFORM_VERSION
hadolint HADOLINT_VERSION
trivy TRIVY_VERSION
k6 K6_VERSION
python PYTHON_VERSION
uv UV_VERSION
pre-commit PRECOMMIT_VERSION
"

for f in "$ACTION" "$DEVCONTAINER" "$DEVBOX" "$LOCK"; do
  [ -f "$f" ] || { echo "✗ missing $f" >&2; exit 1; }
done

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

image=$(sed -n 's/^[[:space:]]*"image":[[:space:]]*"\([^"]*\)".*/\1/p' "$DEVCONTAINER")
case "$image" in
  ghcr.io/$UPSTREAM:*@sha256:*) ;;
  *) echo "✗ $DEVCONTAINER: image '$image' is not ghcr.io/$UPSTREAM:<commit>@sha256:<digest>" >&2
     exit 1 ;;
esac
commit=${image#*:}
commit=${commit%@*}
if [ -n "${IMAGE_DOCKERFILE:-}" ]; then
  dockerfile="$IMAGE_DOCKERFILE"
else
  dockerfile="$tmp/Dockerfile"
  curl -fsSL --proto '=https' --retry 3 -o "$dockerfile" \
    "https://raw.githubusercontent.com/$UPSTREAM/$commit/Dockerfile" || {
    echo "✗ cannot fetch $UPSTREAM@$commit Dockerfile (offline? set IMAGE_DOCKERFILE)" >&2; exit 1; }
fi
image_label="image $UPSTREAM@$commit"
arg() { sed -n "s/^ARG $1=//p" "$dockerfile"; }

# "<source>|<pkg@constraint>|<pinned version>|<mode>" per pin; mode is exact or major.
{
  awk -v f="$ACTION" '
    /# devbox\.json:/ && !/^[[:space:]]*#/ {
      spec = $0; sub(/.*# devbox\.json:[[:space:]]*/, "", spec); sub(/[[:space:]].*/, "", spec)
      ver = $0;  sub(/#.*/, "", ver); sub(/^[^:]*:[[:space:]]*/, "", ver)
      gsub(/["[:space:]]/, "", ver); sub(/^v/, "", ver)
      print f "|" spec "|" ver "|exact"
    }' "$ACTION"
  awk -v f="$DEVCONTAINER" '
    /\/\/ devbox\.json:/ && !/^[[:space:]]*\/\// {
      spec = $0; sub(/.*\/\/ devbox\.json:[[:space:]]*/, "", spec)
      mode = (spec ~ /\(major\)/) ? "major" : "exact"; sub(/[[:space:]].*/, "", spec)
      ver = $0
      if (!sub(/.*"version":[[:space:]]*"/, "", ver)) ver = "UNPAIRED"; else sub(/".*/, "", ver)
      print f "|" spec "|" ver "|" mode
    }' "$DEVCONTAINER"
  echo "$IMAGE_TOOLS" | while read -r pkg var; do
    [ -n "$pkg" ] || continue
    spec=$(jq -r --arg p "$pkg" '.packages[] | select(startswith($p + "@"))' "$DEVBOX")
    echo "$image_label|${spec:-$pkg@?}|$(arg "$var")|exact"
  done
} > "$tmp/pins"

status=0
checked=0
while IFS='|' read -r file spec ver mode; do
  checked=$((checked + 1))
  if [ "$ver" = "UNPAIRED" ]; then
    echo "✗ $file: '// devbox.json: $spec' is not on a \"version\" line"; status=1; continue
  fi
  if ! jq -e --arg s "$spec" '.packages | index($s)' "$DEVBOX" >/dev/null; then
    echo "✗ $file: pins $spec, but devbox.json does not declare it"; status=1; continue
  fi
  locked=$(jq -r --arg s "$spec" '.packages[$s].version // empty' "$LOCK")
  if [ -z "$locked" ]; then
    echo "✗ $spec: no resolved version in devbox.lock (run devbox install)"; status=1; continue
  fi
  if [ -z "$ver" ]; then
    echo "✗ $file: no version for ${spec%@*}"; status=1; continue
  fi
  case "$mode:$locked" in
    exact:"$ver" | exact:"$ver".* | exact:"$ver"+* | major:"$ver".*) ;;
    *) case "$ver" in
         "$locked".* | "$locked"+*) ;;
         *) echo "✗ $file: ${spec%@*} pinned $ver, devbox.lock resolves $locked"; status=1 ;;
       esac ;;
  esac
done < "$tmp/pins"

# Coverage: every devbox package is in the devcontainer, from the image or a feature.
for spec in $(jq -r '.packages[]' "$DEVBOX"); do
  grep -Eq "^($DEVCONTAINER|$image_label)\|$spec\|" "$tmp/pins" || {
    echo "✗ devcontainer: no pin for devbox package $spec (map it in IMAGE_TOOLS or add a feature)"
    status=1; }
done

# sha256 pins in setup-tools: all set; those annotated `# Dockerfile: <ARG>` match the image.
hashes=0
matched=0
grep '^[[:space:]]*SHA256_[A-Z0-9]*:' "$ACTION" > "$tmp/hashes" || true
while read -r line; do
  hashes=$((hashes + 1))
  hash=$(echo "$line" | sed 's/^[^"]*"\([^"]*\)".*/\1/')
  echo "$hash" | grep -Eqx '[0-9a-f]{64}' || {
    echo "✗ $ACTION: not a sha256: $line"; status=1; continue; }
  case "$line" in *"# Dockerfile: "*) ;; *) continue ;; esac
  var=$(echo "$line" | sed 's/.*# Dockerfile: \([A-Z0-9_]*\).*/\1/')
  want=$(arg "$var")
  if [ -z "$want" ]; then
    echo "✗ $ACTION: references $var, which the $image_label Dockerfile does not define"; status=1
  elif [ "$hash" != "$want" ]; then
    echo "✗ $ACTION: hash for $var differs from the $image_label Dockerfile"; status=1
  else
    matched=$((matched + 1))
  fi
done < "$tmp/hashes"

[ "$checked" -gt 0 ] || { echo "✗ no pins found"; exit 1; }
if [ "$status" -eq 0 ]; then
  echo "✓ $checked pins (CI + devcontainer) match devbox.lock; devcontainer covers all $(jq '.packages | length' "$DEVBOX") devbox packages"
  echo "✓ $hashes setup-tools sha256 pins set; $matched match the $image_label Dockerfile"
fi
exit "$status"
