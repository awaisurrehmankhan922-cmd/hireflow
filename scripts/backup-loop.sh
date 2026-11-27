#!/bin/sh
# Nightly encrypted backup of the HireFlow Postgres DB. Keeps BACKUP_RETENTION_DAYS (default 14).
# Encryption: AES-256 via openssl with BACKUP_PASSPHRASE. Restore with scripts/restore.sh.
set -eu
apk add --no-cache openssl >/dev/null 2>&1 || true
: "${BACKUP_PASSPHRASE:?BACKUP_PASSPHRASE must be set}"
while true; do
  ts=$(date -u +%Y%m%dT%H%M%SZ)
  f="/backups/hireflow-$ts.sql.gz.enc"
  if pg_dump -h db -U hireflow hireflow | gzip | openssl enc -aes-256-cbc -pbkdf2 -salt -pass env:BACKUP_PASSPHRASE -out "$f"; then
    echo "$(date -u) backup ok: $f"
  else
    echo "$(date -u) BACKUP FAILED" >&2; rm -f "$f"
  fi
  find /backups -name 'hireflow-*.enc' -mtime +"${BACKUP_RETENTION_DAYS:-14}" -delete
  sleep 86400
done
