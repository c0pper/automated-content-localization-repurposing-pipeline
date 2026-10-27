# Deployment runbook (v1, single host)

v1 ships as one Docker Compose stack: Caddy, the API, the worker, Postgres, Redis, Silo
(S3-compatible object storage) and a nightly backup service. Caddy is the only public
ingress; the Silo console stays private.

The Compose file is the deployment contract. See
[ADR 0014](adr/0014-single-host-compose.md) and
[the v1 spec §12](spec/v1-pipeline.md#12-retention-purge-and-deployment).

## 1. Host prerequisites

- Linux host with Docker Engine 25+ and the Compose plugin.
- Ports 80 and 443 reachable from the internet (Caddy issues TLS certificates).
- A DNS record for `${PIPELINE_DOMAIN}` and `s3.${PIPELINE_DOMAIN}` pointing at the host.
- An off-host backup target mounted at the Docker volume `backups`. The target must be a
  different host or object store; a second directory on the same disk is not a backup.
- **Encrypted volumes.** Encrypt the host block devices that back the Docker volumes with
  LUKS, or run the host on a provider-managed encrypted disk. A host with unencrypted
  volumes is out of compliance with ADR 0014.

Example LUKS setup for a dedicated data disk (adapt the device name):

```bash
cryptsetup luksFormat /dev/nvme1n1
cryptsetup open /dev/nvme1n1 pipeline-data
mkfs.ext4 /dev/mapper/pipeline-data
mount /dev/mapper/pipeline-data /var/lib/docker
```

Verify the mount before starting the stack:

```bash
findmnt /var/lib/docker
lsblk -f
```

## 2. Configure secrets

```bash
cp .env.production.example .env.production
$EDITOR .env.production
chmod 600 .env.production
```

`.env.production` is git-ignored and must never be committed. Generate independent
secrets, for example:

```bash
python3 -c 'import secrets; print(secrets.token_urlsafe(48))'
```

The API refuses to start in `PIPELINE_ENVIRONMENT=production` when:

- the Workspace API key, notification signing secret or webhook secret are missing,
  too short, or still the development defaults;
- API/public URLs are not HTTPS;
- persistence, queue or object storage are still the in-memory/local backends;
- Silo credentials or bucket are missing;
- the media backend is still `stub`.

This fail-closed check lives in `Settings.validate_for_runtime()`.

## 3. Start the stack

```bash
docker compose --env-file .env.production build
docker compose --env-file .env.production up -d
docker compose --env-file .env.production ps
```

Startup order is enforced with health checks:

1. Postgres and Redis become healthy.
2. `migrate` applies `migrations/*.sql`.
3. Silo becomes healthy and `silo-init` creates the bucket.
4. The API and worker start; Caddy starts once the API is healthy.

Readiness covers the database, the object store and the queue:

```bash
curl -fsS https://pipeline.example.com/healthz
curl -fsS https://pipeline.example.com/readyz
```

`/readyz` returns `503` and a `degraded` body when a dependency is down.

## 4. TLS and presigned Silo links

Caddy terminates TLS for both hostnames:

- `https://pipeline.example.com` → `api:8000`
- `https://s3.pipeline.example.com` → `silo:9000`

The Silo console (`:9001`) is not proxied. Review assets redirect to a short-lived
presigned Silo URL. The adapter signs that URL against
`PIPELINE_SILO_PUBLIC_ENDPOINT` (the public hostname), not the internal service name,
because the S3 signature covers the `Host` header. Caddy forwards the original host to
Silo unchanged, so the signature validates.

If presigned links return `SignatureDoesNotMatch`, check that:

- `PIPELINE_SILO_PUBLIC_ENDPOINT` exactly matches the browser-facing hostname and scheme;
- the request reaches Silo through Caddy (bypassing Caddy changes the host);
- the host clock is synchronised (NTP).

## 5. Smoke test

```bash
API_BASE_URL=https://pipeline.example.com \
PIPELINE_WORKSPACE_API_KEY="$(grep '^PIPELINE_WORKSPACE_API_KEY=' .env.production | cut -d= -f2-)" \
INPUT_URL=https://example.com/sample.mp4 \
./deploy/smoke.sh
```

The script submits a synthetic Job, waits for `AWAITING_SELECTION`, confirms the gate,
waits for `COMPLETED` and resolves the review link. Run it after every deploy and after
every restore drill.

## 6. Backups

The `backup` service runs nightly at `BACKUP_HOUR` UTC (default 02:00):

- `pg_dump` → `/backups/postgres/pipeline-<timestamp>.sql.gz`;
- `mcli mirror` of the Silo bucket → `/backups/silo/<YYYYMMDD>/<bucket>/`.

Both age out after `PIPELINE_BACKUP_RETENTION_DAYS` (default 30). RPO is 24 hours.
Backups are independent of the Workspace Purge: a purge deletes live assets immediately,
while older backups age out under this separate policy.

Check the last backup:

```bash
docker compose --env-file .env.production logs --tail=50 backup
docker compose --env-file .env.production exec backup ls -lh /backups/postgres
```

## 7. Restore drill

Run this on a **clean host** with the same Compose file and a copy of the backup volume.
Do not drill against production.

```bash
# Copy the selected backup into the clean host's `backups` volume first.
./deploy/restore.sh postgres/pipeline-20261027T020000Z.sql.gz silo/20261027
API_BASE_URL=https://pipeline.example.com \
PIPELINE_WORKSPACE_API_KEY=... \
INPUT_URL=https://example.com/sample.mp4 \
./deploy/smoke.sh
```

Record the drill result: backup timestamp, restore duration, smoke-test result and any
manual fix-ups. A backup is not considered valid until a restore has been verified.

## 8. Purge and backups

A Workspace Purge is two-step (`POST /api/workspace/purge` then
`POST /api/workspace/purge/{purge_id}/confirm`). Confirmation:

- locks new submissions;
- requires every Job to be terminal;
- deletes Jobs, Clips, localized assets, review tokens, cost entries, events,
  idempotency records and the `jobs/`/`uploads/` object prefixes;
- keeps Workspace Settings, the API key and the Voice Profile.

Backups taken before the purge still exist until their 30-day retention expires. Treat a
purge as irreversible for live data, not as a way to erase backups.

## 9. Operations checklist

- [ ] Host volumes and the backup target are encrypted at rest.
- [ ] `.env.production` is present, mode `600`, and not committed.
- [ ] `docker compose ps` shows every service healthy/running.
- [ ] `/readyz` returns `200`.
- [ ] `./deploy/smoke.sh` passes.
- [ ] The nightly backup log shows a fresh Postgres dump and Silo mirror.
- [ ] A restore drill has been completed and recorded.
- [ ] Caddy certificates renew automatically (`docker compose logs caddy`).
