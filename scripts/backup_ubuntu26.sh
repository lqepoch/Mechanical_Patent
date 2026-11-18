#!/usr/bin/env bash
# Offline-consistent snapshot of the complete SQLite + JSON workspace.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
die() { echo "ERROR: $*" >&2; exit 1; }
[[ "$EUID" -eq 0 ]] || die "Run as root (sudo), to read a private workspace."
[[ -f "$ROOT/.env" ]] || die "Missing .env."
[[ -n "${PATENT_BACKUP_DIR:-}" && "$PATENT_BACKUP_DIR" == /* ]] || die "Set PATENT_BACKUP_DIR to an absolute directory on a separate mounted disk."
[[ ! -L "$PATENT_BACKUP_DIR" ]] || die "Backup dir cannot be a symlink."
command -v docker >/dev/null || die "Docker Compose unavailable."
command -v findmnt >/dev/null || die "findmnt unavailable."
compose=(docker compose --env-file "$ROOT/.env" -f "$ROOT/compose.yaml" -p mechanical-patent)
data_dir="$("${compose[@]}" config --format json | python3 -c 'import json,sys; c=json.load(sys.stdin); print(next(v["source"] for v in c["services"]["patent-mcp"]["volumes"] if v["target"]=="/data"))')"
[[ -d "$data_dir" && ! -L "$data_dir" ]] || die "Invalid data directory."
[[ -d "$PATENT_BACKUP_DIR" ]] || die "Mount and create backup dir first."
data_real="$(realpath "$data_dir")"
backup_real="$(realpath "$PATENT_BACKUP_DIR")"
[[ "$data_real" != "$backup_real" && "$backup_real/" != "$data_real/"* ]] || die "Backup dir must be outside the workspace."
data_source="$(findmnt -n -T "$data_real" -o SOURCE | head -n1)"
backup_source="$(findmnt -n -T "$backup_real" -o SOURCE | head -n1)"
[[ -n "$data_source" && -n "$backup_source" && "$data_source" != "$backup_source" ]] || die "Backup and data must reside on different filesystems."
[[ "$(findmnt -n -T "$backup_real" -o TARGET | head -n1)" != / ]] || die "Backup directory must be on a non-root mount."
umask 077
filename="mechanical-patent-$(date -u +%Y%m%dT%H%M%SZ).tar.gz"
temporary="$backup_real/.$filename.partial"
archive="$backup_real/$filename"
was_running="$("${compose[@]}" ps -q --status running patent-mcp)"
restart() {
  rm -f "$temporary"
  if [[ -n "$was_running" ]]; then
    "${compose[@]}" up -d --no-build patent-mcp || echo "WARNING: restart failed" >&2
  fi
}
trap restart EXIT
if [[ -n "$was_running" ]]; then "${compose[@]}" stop -t 45 patent-mcp; fi
tar --numeric-owner --one-file-system -czf "$temporary" -C "$data_real" .
tar -tzf "$temporary" >/dev/null
mv -n "$temporary" "$archive" || die "Backup target exists."
(cd "$backup_real" && sha256sum "$filename" > "$filename.sha256")
echo "Backup complete: $archive"
