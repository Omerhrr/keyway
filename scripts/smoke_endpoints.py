"""Smoke-test every staff GET endpoint; report non-200s."""
import json
import urllib.request

BASE = "http://localhost:8000"

def req(path, token=None, method="GET"):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    r = urllib.request.Request(f"{BASE}{path}", headers=headers, method=method)
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            return resp.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception as e:
        return str(e)

login = urllib.request.Request(f"{BASE}/api/auth/login",
    data=json.dumps({"email": "owner@keyway.ng", "password": "Keyway@2026"}).encode(),
    headers={"Content-Type": "application/json"})
token = json.load(urllib.request.urlopen(login))["access_token"]

endpoints = [
    "/api/dashboard", "/api/users", "/api/roles", "/api/charges/rules",
    "/api/whatsapp/account", "/api/whatsapp/templates", "/api/vendors",
    "/api/catalog/products?breakdown=true", "/api/inventory/balances",
    "/api/customers", "/api/orders", "/api/orders/drafts",
    "/api/confirmations/queue", "/api/dispatch/riders", "/api/dispatch/deliveries",
    "/api/cod/collections", "/api/cod/handovers", "/api/settlements",
    "/api/ledger/accounts", "/api/ledger/journals", "/api/ledger/trial-balance",
    "/api/ledger/pnl", "/api/ledger/balance-sheet", "/api/ledger/expenses",
    "/api/reports/orders-by-status", "/api/reports/revenue-14d",
    "/api/reports/delivery-performance", "/api/reports/whatsapp-stats",
    "/api/reports/vendor-performance", "/api/reports/staff-performance",
    "/api/reports/operational", "/api/reports/financial",
    "/api/notifications", "/api/audit", "/api/conversations",
]
bad = []
for ep in endpoints:
    code = req(ep, token)
    if code != 200:
        bad.append((ep, code))
        print(f"  FAIL {code}  {ep}")
if not bad:
    print(f"all {len(endpoints)} endpoints OK")
else:
    print(f"{len(bad)}/{len(endpoints)} failing")
