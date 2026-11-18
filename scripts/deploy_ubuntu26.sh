#!/usr/bin/env bash
# Ubuntu 26.04 only: explicit persistent disk and localhost-only MCP.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
die() { echo "ERROR: $*" >&2; exit 1; }
check_host() {
  [[ -r /etc/os-release ]] || die "Linux OS information missing."
  . /etc/os-release
  [[ "${ID:-}" == ubuntu && "${VERSION_ID:-}" == 26.04 ]] || die "Only Ubuntu 26.04 LTS supported: ${PRETTY_NAME:-unknown}"
  command -v docker >/dev/null || die "Install Docker Engine + Compose; see docs/DEPLOYMENT_UBUNTU26.md"
  command -v python3 >/dev/null || die "Python 3 required for Compose config parsing"
  command -v findmnt >/dev/null || die "findmnt required to verify data disk"
  docker compose version >/dev/null
  [[ -f "$ROOT/.env" ]] || die "Copy .env.example to .env and configure PATENT_IMAGE and PATENT_DATA_DIR."
}
compose=(docker compose --env-file "$ROOT/.env" -f "$ROOT/compose.yaml" -p mechanical-patent)
data_dir() {
  "${compose[@]}" config --format json |
    python3 -c 'import json,sys; c=json.load(sys.stdin); print(next(v["source"] for v in c["services"]["patent-mcp"]["volumes"] if v["target"]=="/data"))'
}
validate_path() {
  local path="$1"
  [[ "$path" == /* && "$path" != / ]] || die "PATENT_DATA_DIR must be an absolute non-root path."
  [[ ! -L "$path" ]] || die "PATENT_DATA_DIR cannot be a symlink."
  local ancestor="$path"
  while [[ ! -e "$ancestor" && "$ancestor" != / ]]; do ancestor="$(dirname "$ancestor")"; done
  if [[ "${PATENT_REQUIRE_SEPARATE_DISK:-true}" == true ]]; then
    local mount
    mount="$(findmnt -n -o TARGET -T "$ancestor" | head -n1)" || die "Cannot locate parent mount."
    [[ "$mount" != / ]] || die "Data disk not mounted. Mount separate disk or explicitly set PATENT_REQUIRE_SEPARATE_DISK=false."
  fi
}
check_data() {
  local path="$1"
  validate_path "$path"
  [[ -d "$path" ]] || die "Data directory missing; run init."
  [[ "$(stat -c %u "$path")" == 10001 ]] || die "Data directory owner must be UID 10001; run init."
  [[ "$(stat -c %a "$path")" == 700 ]] || die "Data directory mode must be 0700; run init."
}
check_host
target="$(data_dir)"
case "${1:-help}" in
  init)
    validate_path "$target"
    sudo install -d -m 0700 -o 10001 -g 10001 -- "$target"
    check_data "$target"
    echo "Persistent storage ready: $target"
    ;;
  up|upgrade)
    check_data "$target"
    "${compose[@]}" config --quiet
    "${compose[@]}" pull patent-mcp
    "${compose[@]}" up -d --no-build --remove-orphans
    "${compose[@]}" ps
    ;;
  status)
    "${compose[@]}" ps
    ;;
  logs)
    "${compose[@]}" logs --tail=100 patent-mcp
    ;;
  down)
    "${compose[@]}" down --remove-orphans
    echo "Container stopped. Data retained at $target"
    ;;
  *)
    echo "Usage: bash scripts/deploy_ubuntu26.sh {init|up|upgrade|status|logs|down}"
    exit 2
    ;;
esac
