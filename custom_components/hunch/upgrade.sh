#!/usr/bin/env bash
set -euo pipefail

REPOSITORY="rahools/cctv-human-sensor-hacs"
SCRIPT_PATH="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/$(basename -- "${BASH_SOURCE[0]}")"

if [[ "${HUNCH_UPGRADE_BOOTSTRAPPED:-}" != "1" ]]; then
  BOOTSTRAP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/hunch-upgrade-bootstrap.XXXXXX")"
  cp "$SCRIPT_PATH" "$BOOTSTRAP_DIR/upgrade.sh"
  export HUNCH_UPGRADE_BOOTSTRAPPED=1
  export HUNCH_UPGRADE_BOOTSTRAP_DIR="$BOOTSTRAP_DIR"
  HUNCH_UPGRADE_SOURCE_DIR="$(dirname -- "$SCRIPT_PATH")"
  export HUNCH_UPGRADE_SOURCE_DIR
  exec bash "$BOOTSTRAP_DIR/upgrade.sh" "$@"
fi

SOURCE_SCRIPT_DIR="$HUNCH_UPGRADE_SOURCE_DIR"
HA_CONFIG="$(cd -- "$SOURCE_SCRIPT_DIR/../.." && pwd)"
COMPONENT_DIR="$HA_CONFIG/custom_components/hunch"
WORK_DIR=""
STAGING_DIR=""
PREVIOUS_DIR=""
REQUESTED_TAG=""
RESTART_CONTAINER=""

cleanup() {
  if [[ -n "$PREVIOUS_DIR" && -d "$PREVIOUS_DIR" && ! -d "$COMPONENT_DIR" ]]; then
    mv "$PREVIOUS_DIR" "$COMPONENT_DIR"
  fi
  if [[ -n "$STAGING_DIR" && -d "$STAGING_DIR" ]]; then
    rm -rf "$STAGING_DIR"
  fi
  if [[ -n "$WORK_DIR" && -d "$WORK_DIR" ]]; then
    rm -rf "$WORK_DIR"
  fi
  if [[ -n "${HUNCH_UPGRADE_BOOTSTRAP_DIR:-}" && -d "${HUNCH_UPGRADE_BOOTSTRAP_DIR:-}" ]]; then
    rm -rf "$HUNCH_UPGRADE_BOOTSTRAP_DIR"
  fi
}
trap cleanup EXIT

usage() {
  echo "Usage: $0 [vX.Y.Z] [--restart <homeassistant-container>]" >&2
}

fail() {
  echo "Upgrade failed: $*" >&2
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --restart)
      [[ $# -ge 2 ]] || fail "--restart requires a container name"
      RESTART_CONTAINER="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    v*)
      [[ -z "$REQUESTED_TAG" ]] || fail "Specify only one version tag"
      REQUESTED_TAG="$1"
      shift
      ;;
    *)
      usage
      fail "Unknown argument: $1"
      ;;
  esac
done

for command in curl git tar python3; do
  command -v "$command" >/dev/null 2>&1 || fail "Required command not found: $command"
done
if [[ -n "$RESTART_CONTAINER" ]]; then
  command -v docker >/dev/null 2>&1 || fail "Docker is required for --restart"
fi
[[ -f "$COMPONENT_DIR/manifest.json" ]] || fail "No Hunch installation found at $COMPONENT_DIR"

manifest_value() {
  python3 - "$1" "$2" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as manifest:
    print(json.load(manifest)[sys.argv[2]])
PY
}

CURRENT_VERSION="$(manifest_value "$COMPONENT_DIR/manifest.json" version)"
if [[ -z "$REQUESTED_TAG" ]]; then
  REQUESTED_TAG="$(
    git ls-remote --tags --refs "https://github.com/$REPOSITORY.git" 'v*' \
      | sed 's#.*refs/tags/##' \
      | grep -E '^v[0-9]+\.[0-9]+\.[0-9]+$' \
      | sort -V \
      | tail -n 1
  )"
  [[ -n "$REQUESTED_TAG" ]] || fail "No release tags found"
fi
[[ "$REQUESTED_TAG" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]] || fail "Invalid version tag: $REQUESTED_TAG"
EXPECTED_VERSION="${REQUESTED_TAG#v}"

if [[ "$CURRENT_VERSION" == "$EXPECTED_VERSION" ]]; then
  echo "Hunch $CURRENT_VERSION is already installed."
  exit 0
fi

WORK_DIR="$(mktemp -d "${TMPDIR:-/tmp}/hunch-upgrade.XXXXXX")"
ARCHIVE="$WORK_DIR/release.tar.gz"
ARCHIVE_URL="https://github.com/$REPOSITORY/archive/refs/tags/$REQUESTED_TAG.tar.gz"
echo "Downloading Hunch $EXPECTED_VERSION..."
curl --fail --location --silent --show-error --retry 3 --connect-timeout 10 --max-time 120 \
  "$ARCHIVE_URL" --output "$ARCHIVE" || fail "Could not download $REQUESTED_TAG"

if tar -tzf "$ARCHIVE" | grep -E '(^|/)\.\.(/|$)' >/dev/null; then
  fail "Archive contains unsafe paths"
fi
mkdir "$WORK_DIR/extracted"
tar -xzf "$ARCHIVE" -C "$WORK_DIR/extracted" || fail "Could not extract the release"
EXTRACTED_COMPONENT="$(find "$WORK_DIR/extracted" -type d -path '*/custom_components/hunch' -print -quit)"
[[ -n "$EXTRACTED_COMPONENT" && -f "$EXTRACTED_COMPONENT/manifest.json" ]] \
  || fail "Release does not contain custom_components/hunch"
[[ "$(manifest_value "$EXTRACTED_COMPONENT/manifest.json" domain)" == "hunch" ]] \
  || fail "Downloaded manifest has the wrong domain"
[[ "$(manifest_value "$EXTRACTED_COMPONENT/manifest.json" version)" == "$EXPECTED_VERSION" ]] \
  || fail "Downloaded manifest version does not match $REQUESTED_TAG"

STAGING_DIR="$HA_CONFIG/custom_components/.hunch-new-$$"
PREVIOUS_DIR="$HA_CONFIG/custom_components/.hunch-old-$$"
[[ ! -e "$STAGING_DIR" && ! -e "$PREVIOUS_DIR" ]] || fail "Temporary component path already exists"
mkdir "$STAGING_DIR"
cp -R "$EXTRACTED_COMPONENT/." "$STAGING_DIR/"
if [[ ! -f "$STAGING_DIR/upgrade.sh" ]]; then
  cp "$SOURCE_SCRIPT_DIR/upgrade.sh" "$STAGING_DIR/upgrade.sh"
fi
chmod +x "$STAGING_DIR/upgrade.sh"

BACKUP_DIR="$HA_CONFIG/backups/hunch/$(date +%Y%m%d%H%M%S)-$CURRENT_VERSION"
mkdir -p "$(dirname -- "$BACKUP_DIR")"
cp -R "$COMPONENT_DIR" "$BACKUP_DIR" || fail "Could not back up the current component"

mv "$COMPONENT_DIR" "$PREVIOUS_DIR"
if mv "$STAGING_DIR" "$COMPONENT_DIR"; then
  rm -rf "$PREVIOUS_DIR"
else
  mv "$PREVIOUS_DIR" "$COMPONENT_DIR"
  rm -rf "$STAGING_DIR"
  fail "Could not install the new component; the previous version was restored"
fi

echo "Hunch upgraded from $CURRENT_VERSION to $EXPECTED_VERSION."
echo "Previous component code backed up at $BACKUP_DIR"
if [[ -n "$RESTART_CONTAINER" ]]; then
  docker restart "$RESTART_CONTAINER" || fail "Component upgraded, but Home Assistant could not be restarted"
  echo "Home Assistant container restarted."
else
  echo "Restart Home Assistant to load the new version."
fi
