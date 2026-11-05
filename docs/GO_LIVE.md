# Keyway Go-Live Checklist

Everything that must be true before real vendors and real money flow through
Keyway. Tick items top to bottom; nothing here is optional for production.

## 1. Secrets & environment

Backend configuration is env-driven (`backend/.env`, prefix `KEYWAY_`,
see `.env.example`). In production:

- [ ] `KEYWAY_SECRET_KEY` — set a long random value (`python3 -c "import secrets;print(secrets.token_urlsafe(48))"`).
      The default `keyway-dev-secret-change-me` invalidates all JWTs and lets
      anyone forge tokens.
- [ ] `KEYWAY_ENV=production` — disables dev conveniences.
- [ ] `KEYWAY_CORS_ORIGINS` — set to your exact dashboard origin(s). The dev
      default `*` must never reach production.
- [ ] Never commit `.env`. Rotate any credential that has ever appeared in a
      chat, ticket or screenshot (this includes GitHub PATs — rotate at
      github.com/settings/tokens if one was ever pasted into a conversation).

## 2. WhatsApp Cloud API

The adapter (`backend/app/modules/whatsapp_cloud.py`) is complete: outbound
text/templates, inbound media download, webhook signature verification,
credential self-test. **Full step-by-step guide: `docs/WHATSAPP_SETUP.md`.**
What you must supply from Meta:

- [ ] Meta Business app with the **WhatsApp product** added; business verified.
- [ ] `KEYWAY_WHATSAPP_ACCESS_TOKEN` — permanent **System User token** with
      `whatsapp_business_messaging` + `whatsapp_business_management`.
- [ ] `KEYWAY_WHATSAPP_PHONE_NUMBER_ID` and `KEYWAY_WHATSAPP_WABA_ID`.
- [ ] `KEYWAY_WHATSAPP_APP_SECRET` — enables X-Hub-Signature-256 webhook
      verification. Webhook POSTs are **rejected** when this is set and the
      signature mismatches; unset, the webhook only accepts with a loud warning,
      so do not launch without it.
- [ ] `KEYWAY_WHATSAPP_VERIFY_TOKEN` — any random string; must match what you
      type into Meta's webhook subscription dialog.
- [ ] Meta App Dashboard → WhatsApp → Configuration → Webhook:
      callback URL `https://<your-domain>/api/whatsapp/webhook`, verify token
      as above, subscribe to the `messages` field.
- [ ] Submit message templates for approval (order confirmed, dispatched,
      delivered, delivery failed) — freeform replies only work inside the
      24-hour customer-service window; outside it Meta requires templates.
- [ ] In Keyway: Settings → WhatsApp → set mode to **CLOUD_API** and press
      **Test connection** (hits Graph `GET /{phone_number_id}` — no message sent).

## 3. Database

SQLite in WAL mode is fine for a single-node deployment with modest
concurrency (this is the intended launch shape).

- [ ] Backups: `bash scripts/backup.sh` (online-safe snapshot, sha256 sidecar,
      14-snapshot retention). Schedule it — e.g. hourly cron:
      `15 * * * * cd /srv/keyway && python3 scripts/db_backup.py --keep 48 >> /var/log/keyway-backup.log 2>&1`
- [ ] **Off-box storage**: snapshots default to `./backups/` on the same host.
      Point `BACKUP_DIR` at mounted/object storage (S3, volume) — a backup on
      the disk that can die is not a backup.
- [ ] Restore drill (performed once in dev, repeat on staging):
      `bash scripts/restore.sh backups/<snapshot>.db` — stops the API,
      verifies integrity, moves the current db **and its WAL sidecars** aside
      (a stale `-wal` would replay pre-restore transactions), restores, and
      restarts the stack. Verify data afterwards, then delete the
      `pre-restore-*.db*` pair.
- [ ] If you later scale to multiple API workers or heavier write load, move to
      PostgreSQL: set `KEYWAY_DATABASE_URL` and switch `create_all` to a real
      migration tool (Alembic) before doing so.
- [ ] First boot in production starts on an **empty** database by design — the
      rich demo seed only runs when the db is empty. Create the real owner
      account immediately and delete/staff the demo users if any were seeded.

## 4. Deployment

- [ ] Serve the dashboard as a production build (`bun run build`,
      `node .output/server/index.mjs`) behind a reverse proxy with TLS. The
      PWA service worker only registers on production builds — never run the
      dev server for real traffic.
- [ ] `X-Forwarded-Proto` handled by the proxy so cookies/OAuth stay https.
- [ ] Health checks: `GET /api/health` (API), `GET /health` (LLM service).
- [ ] LLM extraction service (port 8001) is optional — the API falls back to
      rules-only parsing when it is unreachable. Point
      `KEYWAY_LLM_SERVICE_URL` at it if enabled.
- [ ] Log rotation for the service logs; ship them somewhere searchable.

## 5. Financial integrity (non-negotiable)

- [ ] Ledger is append-only: corrections go through reversal entries, never
      UPDATE/DELETE. Confirm no migration or script ever writes to
      `journal_entries` outside the posting functions.
- [ ] Every verified COD collection must reconcile to an order and a ledger
      entry — run a reconciliation spot-check on day 1, then weekly.
- [ ] Vendor settlements require approval; check role assignments (Settings →
      Staff) so only finance roles can approve.
- [ ] Audit trail is on for destructive actions (Settings → Audit Trail).

## 6. Post-launch

- [ ] Review notification rules (Settings → Notifications) and tune targets
      after the first week of real traffic.
- [ ] Watch WhatsApp quality rating (Settings → WhatsApp shows it from the
      self-test) — poor quality limits messaging throughput.
- [ ] Rehearse the restore drill quarterly; a backup that has never been
      restored is a hypothesis.
