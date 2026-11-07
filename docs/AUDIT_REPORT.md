# Keyway - pre-development audit

Scope: backend (FastAPI), frontend (Nuxt), security, ops scripts, docs.
Method: full code read, live behavioural probe (`scripts/audit_probe.py`, 37 checks, run against a
freshly seeded server), route auth scan, existing smoke suites, production-boot tests, Nuxt build.

Result: probe 7/37 -> **37/37**; `smoke_endpoints` 35/35; `smoke_pwa_warehouse_notify` 26/26;
`nuxt build` succeeds; production boot verified (fails closed without secrets/admin).

## Fixed - money & ledger
- Reversed journals were dropped from the trial balance, P&L, balance sheet, vendor and portal balances
  (reversal mirror lines counted, originals not). All reports now count POSTED + REVERSED.
- Balance sheet showed liabilities/equity negative and had no totals; now positive with a balanced check.
- P&L used abs() on expenses (credit-balance expenses looked like costs).
- Journals: negative/dual-sided/empty lines and inactive/unknown accounts rejected; reversals of
  reversals and of non-posted entries blocked.
- COD: verifying twice created duplicate journals; zero-collected verify returned 500; negative amounts
  accepted; verified collections could be re-recorded; collections accepted for undelivered orders.
- Settlements ignored discrepancy collections forever; builder could approve own batch; net <= 0 allowed.
- Expenses: an approved (already posted) expense could be rejected; creator could approve own expense.
- Charges: PATCH with date strings 500'd; PERCENT / PER_QTY bases were silently treated as zero.
- All `*_kobo` columns were 32-bit INTEGER (overflow at ~N21M on Postgres) -> BigInteger.

## Fixed - orders, stock, delivery
- Negative/zero quantities and prices accepted; variant/product mismatch; missing phone.
- Failed-delivery return double counted stock (released AND added to damaged); delivered-then-returned
  stock was lost. Adjustments could drive stock negative / below reserved units.
- A confirmation attempt (customer rejected) could cancel a dispatched or delivered order.
- Delivery events recorded "X -> X"; failed re-attempt left order in wrong state; silent `except: pass`
  around delivery charges (now recorded on the order event).
- Auto-confirmed WhatsApp orders that failed mid-way committed a ghost order (now a savepoint).
- Delivered-via-status-endpoint orders never got a pending COD collection.

## Fixed - security
- WhatsApp webhook accepted unsigned POSTs when no app secret was set (fail-open) -> fail-closed.
- Unverified vendor contacts were auto-matched as the vendor identity.
- Riders, warehouse staff etc. could read the ledger, settlements, COD, audit log and finance exports
  (any staff token) -> permission-gated; dashboard hides money figures without a finance/report perm.
- Vendor portal users could read the role/permission catalog and (via require_perm) staff endpoints.
- Password change/reset did not revoke existing sessions (tokens now bound to the password hash).
- Production could boot with the default JWT secret / CORS `*`, and seeded demo superusers with the
  public password `Keyway@2026`. Both now refuse/skip; first admin comes from env.
- Login prefilled owner credentials + demo panel in production builds; open redirect via `?next=`.
- Service worker cached authenticated HTML (shared-device leak); now network-only for navigations and
  cleared on logout.
- Caddy `XTransformPort` rule proxied ANY local port to the internet - removed; security headers added.
- CSV exports/imports vulnerable to spreadsheet formula injection; API bound to 0.0.0.0 by default.
- Phone numbers parsed as prices (N801,234), shoe sizes as quantities, LLM output unvalidated.

## Fixed - correctness / ops
- `vendors.add_contact` crashed (missing import); `else []` where a dict was needed; PATCH required
  every field.
- SQLite-only `julianday()` (breaks on Postgres) and the cycle time was in days labelled hours.
- Report status typo ("RETURNED" vs "RETURNED_TO_WAREHOUSE") hid every return.
- `dispatch.view` permission did not exist, so Dispatch was hidden from every non-superuser.
- Catalog import overwrote live stock and reset reorder levels; `openpyxl` missing from requirements.
- Scripts hardcoded `/home/z/my-project`; backup/restore ignored `KEYWAY_DATABASE_URL`, wrong table name.
- `.env.example` had an invalid URL and un-prefixed names the app ignores.
- Route permission guard added to the frontend; startup moved to a lifespan handler.

## Known gaps (not changed - decisions for development)
- Notification routing: staff rules are masked when `vendor_id` is passed; staff inbox shows vendor rows.
- Riders cannot update their own deliveries (dispatcher does it); no rider-scoped API yet.
- Auth tokens live in browser storage, not httpOnly cookies.
- Concurrent `settlements/build` for one vendor could double-settle (needs a DB unique constraint) and
  `create_all` should become Alembic migrations before Postgres.
- Failed-delivery fees are not billed; charges added after COD verification are not recognised in the ledger.
- LLM calls run synchronously inside the webhook request; media endpoint and message dedup have races.
- Reports financial view is open to anyone with `reports.view` (e.g. warehouse manager).
- Existing databases keep INTEGER money columns until migrated.
