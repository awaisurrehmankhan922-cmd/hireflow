# Security & backup

## Access
- Admin passwords are hashed with bcrypt. Sessions are JWTs in an httpOnly, SameSite=Lax cookie (12 h).
- Only one port is published, bound to `127.0.0.1`. Public access goes through Cloudflare Tunnel (TLS).
- Open WebUI is reachable only after dashboard login (nginx `auth_request`). Its identity headers are set by nginx and overwrite anything the client sends. Open WebUI sign-up is disabled.
- WordPress webhooks are signed with HMAC-SHA256 over `timestamp.body`, use a constant-time comparison, and are rejected outside a ±5 minute window.
- Containers run as a non-root user. Secrets live only in `.env` (chmod 600, git-ignored).

## Compliance and oversight
- Every admin action, login, send, block, opt-out, escalation and settings change goes to `audit_log`.
- Opt-out is applied the moment the email is read and blocks **all** further mail, including manual mail. Only the applicant can restore consent.
- The AI drafts and triages. Hiring, rejection and eligibility decisions are blocked in code.
- Applicants get `email_verified=true` when they reply from their address.

## Backups
- The `backup` service runs a nightly `pg_dump | gzip | openssl aes-256-cbc -pbkdf2` into `BACKUP_DIR`, with `BACKUP_RETENTION_DAYS` retention.
- Copy `BACKUP_DIR` off-server, for example with rclone to S3 or B2. Store `BACKUP_PASSPHRASE` offline.
- Restore:
  ```bash
  docker compose stop api worker
  BACKUP_PASSPHRASE=... ./scripts/restore.sh backups/hireflow-<ts>.sql.gz.enc
  docker compose start api worker
  ```
- Test a restore monthly into a scratch database.

## Monitoring
- `GET /api/health` reports database and AI status. The dashboard sidebar shows both live.
- KPIs show pending AI work, failed deliveries and escalations.
- Use `docker stats` and `docker compose logs` for resources. Point an uptime checker at `/api/health`.
