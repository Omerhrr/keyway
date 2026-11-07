# Deploying Keyway on a VPS with Docker (keyway.rogan.live)

Stack: **Caddy** (automatic HTTPS) -> **web** (Nuxt) -> **api** (FastAPI) -> Docker volume (SQLite + media).
Only ports 80/443 are exposed; the API is never published.

## 1. One-time server setup
1. Point a DNS **A record** `keyway.rogan.live` -> the VPS public IP (wait for it to resolve).
2. Install Docker + the compose plugin (Ubuntu: `curl -fsSL https://get.docker.com | sh`).
3. Open the firewall: `ufw allow 22,80,443/tcp && ufw allow 443/udp && ufw enable`.
4. `git clone <your-github-repo> /opt/keyway && cd /opt/keyway`
5. `cp deploy/production.env.example .env` and fill in:
   - `KEYWAY_SECRET_KEY` -> `python3 -c "import secrets;print(secrets.token_urlsafe(48))"`
   - `KEYWAY_BOOTSTRAP_ADMIN_EMAIL` / `_PASSWORD` (>= 12 chars) - creates the first admin on the empty DB.
6. `docker compose up -d --build`
7. Open https://keyway.rogan.live and sign in with the bootstrap admin. Change the password.
   After the first login you may blank the two `BOOTSTRAP_ADMIN_*` values in `.env`.

## 2. Updating (push to GitHub, pull on the VPS)
```
cd /opt/keyway && git pull && docker compose up -d --build
docker compose logs -f --tail=50 api
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
- Troubleshooting: `docker compose ps`, `docker compose logs caddy` (certificate issues are almost always DNS
  or closed ports), `docker compose logs api`. A boot error about SECRET_KEY / bootstrap admin means `.env` is
  incomplete.
