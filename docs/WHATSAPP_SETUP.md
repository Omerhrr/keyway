# WhatsApp Cloud API Setup Guide

How to connect Keyway to real WhatsApp (Meta Cloud API). Follow the parts in
order. You do the Meta steps in your browser; everything on the Keyway side is
Settings UI + one restart. Budget ~45 minutes plus Meta's approval waits.

**What you will collect from Meta (5 values):**

| # | Value | Example shape |
|---|-------|---------------|
| 1 | Access token (permanent system-user) | `EAAG...` long string |
| 2 | Phone number ID | `123456789012345` |
| 3 | WhatsApp Business Account ID (WABA) | `987654321098765` |
| 4 | App secret | 32 hex chars |
| 5 | Verify token | any string you invent, e.g. `keyway-<random>` |

---

## Part A - Meta side (browser)

### A1. Business portfolio
1. Go to **business.facebook.com** and create (or open) your Business Portfolio.
2. Business Settings → **Security Center** → start **business verification**.
   You can develop and test with up to 5 recipient numbers before it clears,
   but real vendor traffic needs it approved.

### A2. Create the app
1. **developers.facebook.com** → My Apps → **Create App**.
2. Use case: **Business** → later add the **WhatsApp** product from the
   dashboard sidebar.
3. App Settings → **Basic**: copy the **App Secret** (value #4). Keep this
   page open - you will also need the App ID for the dashboard.

### A3. Phone number
1. WhatsApp → **API Setup**: Meta gives you a **test number** instantly
   (limited to 5 verified recipient phones - perfect for staging).
2. For production: **WhatsApp → Phone numbers → Add phone number** and
   register a real SIM-less-capable number that is **not** registered on the
   consumer WhatsApp app. Complete the SMS/voice OTP.
3. From the same **API Setup** page copy:
   - **Phone number ID** (value #2)
   - **WhatsApp Business Account ID** (value #3)

### A4. Permanent access token
1. Business Settings → **Users → System users** → **Add** (role: **Admin**),
   name it `keyway`.
2. **Generate token** → select your app → tick permissions:
   - `whatsapp_business_messaging`
   - `whatsapp_business_management`
   - `business_management`
3. Copy the token (value #1). System-user tokens do **not** expire like the
   24-hour temporary tokens shown in the API Setup quickstart.

### A5. Message templates (do early - approval takes hours to a day)
WhatsApp → **Message templates → Create template**. Create these four with
**exactly these names** (Category: UTILITY, Language: English), body text may
be reworded but keep the variables:

| Template name | Body |
|---|---|
| `order_received` | Thank you! We received your order request: `{{1}}`. Our team is preparing it now. |
| `order_registered` | Order `{{1}}` has been registered. We will update you at every step. Thank you! |
| `delivery_update` | Update on order `{{1}}`: `{{2}}` |
| `settlement_notification` | A settlement of `{{1}}` has been processed to your account. Reference `{{2}}`. |

Keyway sends these by name with plain-text body parameters - the names must
match or Graph API rejects the send.

---

## Part B - Keyway side

### B1. Enter credentials (Settings UI)
1. Sign in as owner → **Settings → WhatsApp**.
2. **Mode** → `WhatsApp Cloud API (production)`.
3. Fill **Phone number ID** (#2), **WhatsApp Business Account ID** (#3),
   **Access token** (#1).
4. **Save**, then press **Test connection**. Success shows the WhatsApp
   business display name and quality rating - that is a live authenticated
   read of your phone number from Graph API.

> Tokens are stored server-side (encrypted column) and override env values;
> the Verify token and App secret are deliberately env-only.

### B2. Server env (the two secrets)
In `backend/.env` (or the deployment's environment):

```ini
KEYWAY_WHATSAPP_APP_SECRET=<value #4>
KEYWAY_WHATSAPP_VERIFY_TOKEN=<value #5>
```

then restart the API (`bash scripts/up.sh`). Without `APP_SECRET` the webhook
accepts unsigned posts with a loud warning - fine for local simulator testing,
**never** for production.

---

## Part C - Webhook subscription

1. Keyway **Settings → WhatsApp** shows the **Webhook callback URL** - copy it.
   It is always `<your-origin>/api/whatsapp/webhook`.
2. Meta App Dashboard → WhatsApp → **Configuration → Webhook → Edit**:
   - Callback URL: the URL above (must be public **HTTPS**)
   - Verify token: value #5
   - Meta calls `GET /api/whatsapp/webhook` and expects the echo of
     `hub.challenge` - Keyway does this automatically (already covered by a
     smoke test: correct token → challenge echoed; wrong token → HTTP 403).
3. Click **Verify and save**, then under **Webhook fields** subscribe to
   **`messages`** (covers both inbound messages and delivery statuses).
4. Where to host the public URL:
   - **Production:** your real domain behind TLS (see `docs/GO_LIVE.md` §4).
   - **Testing in this sandbox:** the preview URL works, but it changes on
     every sandbox restart - after each restart, re-save the webhook in Meta
     (one paste + click).

---

## Part D - Verify end-to-end

1. **Inbound:** WhatsApp your business number from your phone (any text, e.g.
   "I want to order 3 pieces of the ankara gown"). Within seconds it should
   appear in Keyway → **WhatsApp Inbox**, vendor-matched if the number is
   registered, otherwise parked in the unassigned queue.
2. **Outbound:** reply from the inbox; the message arrives on your phone.
3. **AI extraction:** send a realistic order message - the draft order appears
   in **Order Drafts** with extracted items/customer fields for review
   (conversation never auto-becomes an order; a human confirms).
4. **Statuses:** watch an outbound message tick delivered/read - statuses are
   recorded against the message row.
5. **Outside the 24-hour window?** Freeform sends will fail with error
   `131047`; that is by design - Keyway then sends via the approved templates
   (Part A5). Keep templates approved before launch.

---

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| **Test connection** fails `Unreachable` | Sandbox egress blocked or wrong token - check network, regenerate token |
| Test connection: `HTTP 401` / `Session expired` | Token lacks the two `whatsapp_business_*` permissions, or it was a temporary 24h token |
| Webhook verify fails in Meta | Verify token mismatch - the env value must equal exactly what you typed in Meta |
| Webhook saves but no messages arrive | `messages` field not subscribed; or sandbox restarted and URL changed |
| Sends fail `131047`/`131026` | Outside the 24-hour customer-service window → use approved template |
| Sends fail `(#131030)` recipient not on WhatsApp | Wrong number format - Keyway normalizes `0803...` → `234803...`; check the stored phone |
| Sends fail `470`/`133016` | Template name mismatch or not approved - names must match Part A5 |
| Messaging limit errors | Account tier (250/day initially) - quality rating lifts it; keep the rating visible via Test connection |

---

## What Keyway handles automatically

- Phone normalization to Graph format (`0803...` → `234803...`).
- Webhook signature enforcement (`X-Hub-Signature-256`, HMAC-SHA256,
  constant-time compare) once `KEYWAY_WHATSAPP_APP_SECRET` is set.
- Vendor identity resolution from verified phone numbers; unknown senders
  isolated in the unassigned queue.
- Delivery status recording (sent/delivered/read/failed) on the message row.
- Simulator mode stays available side-by-side - demo flows keep working with
  zero Meta credentials, so staging never burns your real number quota.
