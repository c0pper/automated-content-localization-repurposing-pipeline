#!/usr/bin/env bash
# Restore a backup into a clean environment.
#
# Usage:
#   ./deploy/restore.sh postgres/20261027T020000Z.sql.gz silo/20261027
#
# Paths are relative to the backup volume. Run the restore drill on a clean host before
# trusting a backup; see docs/deployment.md.
set -euo pipefail

PG_DUMP_PATH="${1:?usage: restore.sh <postgres-dump> <silo-snapshot>}"
SILO_SNAPSHOT="${2:?usage: restore.sh <postgres-dump> <silo-snapshot>}"
COMPOSE="${COMPOSE:-docker compose --env-file .env.production}"

echo "Stopping API, worker, backup and ingress..."
$COMPOSE stop api worker backup caddy

echo "Restoring Postgres from $PG_DUMP_PATH..."
$COMPOSE exec -T postgres sh -c \
    'PGPASSWORD="$POSTGRES_PASSWORD" dropdb -U pipeline --if-exists pipeline'
$COMPOSE exec -T postgres sh -c \
    'PGPASSWORD="$POSTGRES_PASSWORD" createdb -U pipeline pipeline'
$COMPOSE exec -T postgres sh -c \
    "gunzip -c /backups/$PG_DUMP_PATH | PGPASSWORD=\"\$POSTGRES_PASSWORD\" psql -U pipeline -d pipeline -v ON_ERROR_STOP=1"

echo "Restoring Silo from $SILO_SNAPSHOT..."
$COMPOSE exec -T silo sh -c \
    "mcli alias set local http://localhost:9000 \"\$MINIO_ROOT_USER\" \"\$MINIO_ROOT_PASSWORD\" && \
     mcli mirror --overwrite --remove \"/backups/$SILO_SNAPSHOT/\$PIPELINE_SILO_BUCKET\" \"local/\$PIPELINE_SILO_BUCKET\""

echo "Starting the stack..."
$COMPOSE up -d

echo "Restore complete. Run ./deploy/smoke.sh and inspect /readyz."
