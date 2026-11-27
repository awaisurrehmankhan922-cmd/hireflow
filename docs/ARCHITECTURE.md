# Architecture

## Services (docker compose project `hireflow`)

| Service | Role | Notes |
|---|---|---|
| `gateway` | nginx: dashboard, `/api` proxy, `/ai` (Open WebUI) | The only published port, bound to `127.0.0.1` for Cloudflare Tunnel |
| `api` | FastAPI: REST API and webhook intake | Runs `alembic upgrade head` on start |
| `worker` | Background loop: IMAP, pending applications, inbound replies, follow-ups | Each step is isolated, so one failure never stops the others |
| `db` | PostgreSQL 16 | Separate from the existing MariaDB, which is never touched |
| `ollama` (+ `ollama-pull`) | Local inference | GPU block ready to uncomment |
| `open-webui` | Admin AI playground | Trusted-header SSO through the gateway, sign-up disabled |
| `backup` | Nightly encrypted `pg_dump` | AES-256, retention policy |

Own network (`hireflow_net`) and own volumes, so there are no clashes with existing containers.

## Application lifecycle

```
WP form ─► plugin queue ─► POST /api/webhooks/wordpress (HMAC, ±5 min)
   ─► ingest_application()  [no AI dependency]
        idempotency (source+entry id) · applicant upsert · duplicate fingerprint
   ─► 202 Accepted  ─► background: send acknowledgment (templated) ─► AI classify
                                        │                               │
                                  failed → retried               LLMUnavailable → stays "pending"
                                                                 worker retries every cycle
```

## Inbound email lifecycle

```
IMAP UNSEEN ─► record_inbound(): Message-ID dedupe · match by sender, else by In-Reply-To thread · else create lead
  ─► opt-out keywords?  → consent revoked, nothing else is sent, ever
  ─► human takeover?    → AI stays silent
  ─► draft_reply(): knowledge-base retrieval → LLM JSON → guardrails
        sensitive topic / low confidence / decision language / empty → escalate (no draft)
        otherwise → draft (status=draft); auto-sent only if enabled AND the permission gate allows it
```

## The single permission gate

Every automated send goes through `mailer.automation_block_reason()`. It checks, in order: the global pause, opt-out or no consent, the applicant-level pause, and human takeover. Manual admin sends skip the pauses but **never** opt-outs. Blocked sends are stored with `status=blocked` and a reason, so nothing disappears silently.

## Data model

`admin_users`, `applicants` (consent, opt-out, pause, takeover, verification), `applications` (payload, fingerprint, processing status, AI fields), `messages` (direction, status, threading ids, escalation), `knowledge_articles`, `follow_up_rules`, `follow_up_log` (unique per rule/applicant/sequence), `system_settings`, `audit_log`.

## Extending

- **More mailboxes:** move the IMAP/SMTP settings into a `mail_accounts` table. The inbox and mailer already take one account's settings, so this is a loop.
- **More channels (Phase 2):** add a `channel` adapter next to `inbox.py`. `messages.channel` already exists.
- **Better retrieval:** replace `retrieve_knowledge()` with pgvector embeddings (Ollama `nomic-embed-text`).
