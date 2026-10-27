#!/usr/bin/env bash
# Nightly Postgres logical dump + Silo bucket mirror.
#
# The backup volume is the operator-provided off-host target. It must be encrypted at
# rest. Retention is independent of the Workspace Purge policy.
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/backups}"
BACKUP_HOUR="${BACKUP_HOUR:-2}"
BACKUP_RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-30}"
BACKUP_ON_START="${BACKUP_ON_START:-false}"

: "${PGHOST:?PGHOST is required}"
: "${PGDATABASE:?PGDATABASE is required}"
: "${PGUSER:?PGUSER is required}"
: "${PGPASSWORD:?PGPASSWORD is required}"
: "${SILO_ENDPOINT:?SILO_ENDPOINT is required}"
: "${SILO_BUCKET:?SILO_BUCKET is required}"

mkdir -p "$BACKUP_DIR/postgres" "$BACKUP_DIR/silo"

log() {
    printf '%s backup: %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"
}

wait_for_postgres() {
    until pg_isready -h "$PGHOST" -p "${PGPORT:-5432}" -U "$PGUSER" -d "$PGDATABASE" >/dev/null 2>&1; do
        log "waiting for postgres at $PGHOST"
        sleep 5
    done
}

configure_mcli() {
    mcli alias set local "$SILO_ENDPOINT" "$SILO_ACCESS_KEY" "$SILO_SECRET_KEY" >/dev/null
}

dump_postgres() {
    local stamp tmp
    stamp="$(date -u +%Y%m%dT%H%M%SZ)"
    tmp="$BACKUP_DIR/postgres/.pipeline-$stamp.sql.gz.partial"
    log "dumping postgres to postgres/pipeline-$stamp.sql.gz"
    pg_dump --no-owner --no-privileges --clean --if-exists | gzip -9 >"$tmp"
    mv "$tmp" "$BACKUP_DIR/postgres/pipeline-$stamp.sql.gz"
    find "$BACKUP_DIR/postgres" -type f -name 'pipeline-*.sql.gz' \
        -mtime +"$BACKUP_RETENTION_DAYS" -delete
}

mirror_silo() {
    local stamp snapshot
    stamp="$(date -u +%Y%m%d)"
    snapshot="$BACKUP_DIR/silo/$stamp"
    log "mirroring silo bucket $SILO_BUCKET to silo/$stamp"
    mcli mirror --overwrite --remove "local/$SILO_BUCKET" "$snapshot/$SILO_BUCKET"
    find "$BACKUP_DIR/silo" -mindepth 1 -maxdepth 1 -type d \
        -mtime +"$BACKUP_RETENTION_DAYS" -exec rm -rf {} +
}

run_backup() {
    wait_for_postgres
    configure_mcli
    dump_postgres
    mirror_silo
    log "backup complete"
}

if [ "$BACKUP_ON_START" = "true" ]; then
    run_backup
fi

while true; do
    if [ "$(date -u +%H)" = "$(printf '%02d' "$BACKUP_HOUR")" ]; then
        run_backup || log "backup failed; will retry next cycle"
        sleep 3600
    else
        sleep 300
    fi
done
