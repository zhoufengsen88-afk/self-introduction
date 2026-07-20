#!/usr/bin/env bash
set -euo pipefail

SERVER="${SERVER:-root@155.133.7.215}"
SSH_KEY="${SSH_KEY:-/Users/zfs/.ssh/contabo_self_lite_ed25519}"
REMOTE_BACKUP_DIR="${REMOTE_BACKUP_DIR:-/opt/backups/portfolio-stack/postgres}"
LOCAL_BACKUP_DIR="${LOCAL_BACKUP_DIR:-/Users/zfs/Documents/portfolio-stack-backups/postgres}"

mkdir -p "$LOCAL_BACKUP_DIR"

rsync -az \
  -e "ssh -i $SSH_KEY -o BatchMode=yes" \
  "$SERVER:$REMOTE_BACKUP_DIR/" \
  "$LOCAL_BACKUP_DIR/"

echo "Pulled backups into: $LOCAL_BACKUP_DIR"
