#!/bin/sh
# Usage: BACKUP_PASSPHRASE=... ./scripts/restore.sh backups/hireflow-<ts>.sql.gz.enc
# Restores into the running `db` service. Stop api/worker first:  docker compose stop api worker
set -eu
f="$1"
openssl enc -d -aes-256-cbc -pbkdf2 -pass env:BACKUP_PASSPHRASE -in "$f" | gunzip | \
  docker compose exec -T db psql -U hireflow -d hireflow -v ON_ERROR_STOP=1
echo "Restored $f. Start services: docker compose start api worker"
