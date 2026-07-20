#!/usr/bin/env bash
set -euo pipefail

STACK_DIR="${STACK_DIR:-/opt/apps/self-introduction/deploy/production}"
BACKUP_DIR="${BACKUP_DIR:-/opt/backups/portfolio-stack/postgres}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"

mkdir -p "$BACKUP_DIR"
cd "$STACK_DIR"

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
target="$BACKUP_DIR/lite_llmops-$timestamp.dump"
partial="$target.partial"

finish_partial() {
  if [ -f "$partial" ]; then
    mv "$partial" "$BACKUP_DIR/failed-lite_llmops-$timestamp.partial"
  fi
}
trap finish_partial EXIT

docker compose exec -T postgres sh -c \
  'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom --no-owner --no-acl' \
  > "$partial"

mv "$partial" "$target"
target_name="$(basename "$target")"
(
  cd "$BACKUP_DIR"
  sha256sum "$target_name" > "$target_name.sha256"
)
trap - EXIT

find "$BACKUP_DIR" -type f \
  \( -name 'lite_llmops-*.dump' -o -name 'lite_llmops-*.dump.sha256' -o -name 'failed-lite_llmops-*.partial' \) \
  -mtime +"$RETENTION_DAYS" \
  -delete

echo "Created backup: $target"
