#!/usr/bin/env bash
# Restore a backup made by backup.sh. STOP THE API FIRST. This overwrites current data.
#   ./scripts/restore.sh <db_backup_file> <data_tarball>
set -euo pipefail
DB_BACKUP="${1:?db backup file}"
DATA_TAR="${2:?data tarball}"
DATA_DIR="${NEXUS_DATA_DIR:-./var}"
read -r -p "This replaces the current database and data in $DATA_DIR. Type 'restore' to continue: " ANSWER
[[ "$ANSWER" == "restore" ]] || { echo "aborted"; exit 1; }

if [[ -n "${DATABASE_URL:-}" ]]; then
  pg_restore --clean --if-exists --no-owner --dbname "$DATABASE_URL" "$DB_BACKUP"
else
  URL="${NEXUS_DATABASE_URL:-sqlite:///./var/nexus.db}"
  cp "$DB_BACKUP" "${URL#sqlite:///}"
fi
mkdir -p "$DATA_DIR"
tar -xzf "$DATA_TAR" -C "$DATA_DIR"
echo "Restore complete. Start the API and check /api/v1/health."
