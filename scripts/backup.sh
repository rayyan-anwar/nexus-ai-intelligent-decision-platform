#!/usr/bin/env bash
# Back up the database and the data directory (datasets + model files).
#   SQLite:      NEXUS_DATABASE_URL=sqlite:///./var/nexus.db ./scripts/backup.sh [out_dir]
#   PostgreSQL:  DATABASE_URL=postgresql://user:pass@host/db ./scripts/backup.sh [out_dir]   (needs pg_dump)
# Backups contain user data: store them encrypted and apply the same retention rules as the live data.
set -euo pipefail
OUT="${1:-./dumps}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
DATA_DIR="${NEXUS_DATA_DIR:-./var}"
mkdir -p "$OUT"
umask 077

if [[ -n "${DATABASE_URL:-}" ]]; then
  pg_dump --format=custom --file "$OUT/nexus-db-$STAMP.dump" "$DATABASE_URL"
else
  URL="${NEXUS_DATABASE_URL:-sqlite:///./var/nexus.db}"
  DB_PATH="${URL#sqlite:///}"
  sqlite3 "$DB_PATH" ".backup '$OUT/nexus-db-$STAMP.sqlite'"
fi
tar -czf "$OUT/nexus-data-$STAMP.tar.gz" -C "$DATA_DIR" datasets models
echo "Backup written to $OUT (stamp $STAMP)"
