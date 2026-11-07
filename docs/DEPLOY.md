# Deploying Keyway on a VPS with Docker (keyway.rogan.live)

Stack: existing **Caddy** (HTTPS) -> **keyway-web** (Nuxt) -> **keyway-api** (FastAPI) -> Docker volume (SQLite + media).
Nothing is published on host ports; the API is never on the shared network.

## 1. Shared-VPS setup (an existing Caddy owns ports 80/443)
This server already runs other stacks, so Keyway does NOT run its own proxy. It joins the network of the
existing Caddy (`booklet-caddy-1`) and that Caddy serves `keyway.rogan.live`.
1. DNS: `keyway.rogan.live` -> this server (already resolving; if Cloudflare proxy is on, use SSL mode Full).
2. `cd /opt/keyway && git pull`
3. Find the proxy network:
   `docker inspect booklet-caddy-1 -f '{{json .NetworkSettings.Networks}}'` and the Caddyfile it loads:
   `docker inspect booklet-caddy-1 -f '{{json .Mounts}}'`
4. `cp deploy/production.env.example .env`; set `PROXY_NETWORK` (that network's name), `KEYWAY_SECRET_KEY`
   (`python3 -c "import secrets;print(secrets.token_urlsafe(48))"`) and the bootstrap admin email/password.
5. `docker compose up -d --build` and check `docker compose ps` (both healthy).
6. Append `deploy/caddy-site.snippet` to the existing Caddyfile, then reload:
   `docker exec booklet-caddy-1 caddy reload --config /etc/caddy/Caddyfile`
7. Open https://keyway.rogan.live, sign in with the bootstrap admin, change the password; afterwards blank
   the two `BOOTSTRAP_ADMIN_*` values in `.env`.

## 2. Updating (push to GitHub, pull on the VPS)
```
cd /opt/keyway && git pull && docker compose up -d --build
docker compose logs -f --tail=50 keyway-api
```
Data lives in the `keyway-data` volume and survives rebuilds.

## 3. Backups (do this before go-live)
`bash scripts/vps-backup.sh` writes a consistent copy to `./backups` (add the cron line inside the script).
Copy `./backups` off the server regularly. Restore: stop the stack, copy a backup over
`/data/keyway.db` inside the volume, start again.

## 4. WhatsApp Cloud API
Callback URL: `https://keyway.rogan.live/api/whatsapp/webhook`. Set the `KEYWAY_WHATSAPP_*` values in `.env`
(app secret is mandatory - unsigned webhooks are rejected), set `KEYWAY_WHATSAPP_MODE=CLOUD_API`, then
`docker compose up -d`. See `docs/WHATSAPP_SETUP.md`.

## 5. Notes
- `KEYWAY_LLM_ENABLED=false`: the AI extraction micro-service (`mini-services/llm-service`) is not in this
  stack; order parsing uses the built-in rules. It depends on a sandbox-specific SDK.
- One API worker by design (SQLite, in-memory login throttle). Move to Postgres + migrations before scaling.
- Troubleshooting: `docker compose ps`, `docker logs booklet-caddy-1` (certificate issues are almost always DNS), `docker compose logs keyway-api`. A boot error about SECRET_KEY / bootstrap admin means `.env` is
  incomplete.
