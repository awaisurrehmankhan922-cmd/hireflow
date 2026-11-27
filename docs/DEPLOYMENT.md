# Deployment (existing Ubuntu + Docker host)

## 0. Audit first. Change nothing yet.

```bash
docker ps --format 'table {{.Names}}\t{{.Ports}}\t{{.Networks}}'
docker network ls && docker volume ls
ss -tlnp                       # ports already in use
free -h && nproc && df -h      # RAM/CPU/disk for the model
nvidia-smi || echo "no GPU"    # decides qwen3:8b vs qwen3:4b
cloudflared tunnel list        # existing tunnel + ingress rules
```

Record the findings, pick a free `GATEWAY_PORT`, and get the plan approved before touching production.

## 1. Configure

```bash
git clone <repo> /opt/hireflow && cd /opt/hireflow
cp .env.example .env && chmod 600 .env    # fill every CHANGE value
openssl rand -hex 32                      # use for JWT_SECRET / WEBHOOK_SECRET / WEBUI_SECRET_KEY
```

## 2. Start

```bash
docker compose up -d --build
docker compose logs -f ollama-pull        # wait for the model download
curl -s localhost:8088/api/health         # {"status":"ok","database":true,"llm":true,...}
```

## 3. Cloudflare Tunnel

Add one ingress rule to the **existing** tunnel config, for example `hr.example.com → http://localhost:8088`, then restart `cloudflared`. Put Cloudflare Access in front for an extra login layer if you want one.

## 4. WordPress

1. Upload `wordpress-plugin/hireflow-connector` to `wp-content/plugins/` and activate it. Activation creates its own queue table only.
2. Go to **Settings → HireFlow** and enter the platform URL and `WEBHOOK_SECRET`. Optionally limit forwarding to specific form IDs and set the field-name mapping.
3. Submit a test application. It should appear in the dashboard within seconds.

## 5. Mailbox

Set the IMAP/SMTP values in `.env`, then run `docker compose restart worker`. Use an app password where the provider supports it.

## Updating

```bash
git pull && docker compose up -d --build api worker gateway   # migrations run automatically
```

## Rollback

Stop the new services with `docker compose down`. Volumes are kept. The website and MariaDB are unaffected because nothing was shared. Restore data with `scripts/restore.sh`.
