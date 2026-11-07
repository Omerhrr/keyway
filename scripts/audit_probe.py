#!/usr/bin/env python3
"""Behavioural probe for the Keyway API. Each check prints PASS (behaves correctly)
or BUG (confirms a defect). Run against a freshly seeded server:  probe.py [base_url]"""
import json
import sys
import urllib.request
import urllib.error

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
PW = "Keyway@2026"
results = []


def call(method, path, token=None, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method,
                                 headers={"Content-Type": "application/json",
                                          **({"Authorization": f"Bearer {token}"} if token else {})})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw and raw[:1] in b"[{" else raw.decode())
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, raw.decode()


def login(email):
    s, b = call("POST", "/api/auth/login", body={"email": email, "password": PW})
    assert s == 200, (email, s, b)
    return b["access_token"]


def check(name, ok, detail=""):
    results.append((name, ok))
    print(f"{'PASS' if ok else 'BUG '}  {name}" + (f"   -> {detail}" if detail and not ok else ""))


T = login("owner@keyway.ng")
WH = {"id": None}


def tb():
    s, b = call("GET", "/api/ledger/trial-balance", T)
    return {l["code"]: l["balance_kobo"] for l in b["lines"]}, b


# ---------------------------------------------------------------- vendors
s, vendors = call("GET", "/api/vendors", T)
v1 = vendors[0]["id"]
s, b = call("POST", f"/api/vendors/{v1}/contacts", T, {"name": "Probe", "phone": "08055500001"})
check("vendors: add contact works (wa_verified default)", s == 200, f"{s} {str(b)[:80]}")

# ---------------------------------------------------------------- ledger
s, accts = call("GET", "/api/ledger/accounts", T)
by_sub = {a["subtype"]: a for a in accts}
cash, opex = by_sub["CASH"], by_sub["OPERATING_EXPENSE"]
s, b = call("POST", "/api/ledger/journals", T, {"memo": "neg probe", "lines": [
    {"account_id": cash["id"], "debit_kobo": -500, "credit_kobo": 0},
    {"account_id": opex["id"], "debit_kobo": 0, "credit_kobo": -500}]})
check("ledger: negative-amount journal is rejected", s == 400, f"{s} accepted")
s, b = call("POST", "/api/ledger/journals", T, {"memo": "both-sides probe", "lines": [
    {"account_id": cash["id"], "debit_kobo": 100, "credit_kobo": 100},
    {"account_id": opex["id"], "debit_kobo": 50, "credit_kobo": 50}]})
check("ledger: line with both debit and credit is rejected", s == 400, f"{s} accepted")

before, _ = tb()
s, j = call("POST", "/api/ledger/journals", T, {"memo": "rev probe", "lines": [
    {"account_id": opex["id"], "debit_kobo": 100000},
    {"account_id": cash["id"], "credit_kobo": 100000}]})
mid, _ = tb()
s, r = call("POST", f"/api/ledger/journals/{j['id']}/reverse", T, {"reason": "probe"})
after, _ = tb()
check("ledger: reversing a journal nets account balances back to zero",
      after[opex["code"]] == before[opex["code"]] and after[cash["code"]] == before[cash["code"]],
      f"opex before={before[opex['code']]} mid={mid[opex['code']]} after={after[opex['code']]}")
s, r2 = call("POST", f"/api/ledger/journals/{r['id']}/reverse", T, {"reason": "re-reverse"})
check("ledger: a reversal entry cannot itself be reversed", s == 400, f"{s}")

s, e = call("POST", "/api/ledger/expenses", T, {"category": "Fuel", "description": "probe",
                                                  "amount_kobo": 1000})
call("POST", f"/api/ledger/expenses/{e['id']}/approve", T)
s, b = call("POST", f"/api/ledger/expenses/{e['id']}/reject", T)
check("ledger: an approved (already posted) expense cannot be rejected", s == 400, f"{s}")
s, b = call("POST", "/api/ledger/expenses", T, {"category": "Fuel", "amount_kobo": -5})
check("ledger: negative expense rejected", s == 400, f"{s}")
s, p = call("GET", "/api/ledger/pnl", T)
check("pnl: expense accounts report non-negative expense on debit balance",
      all(x["net_kobo"] >= 0 for x in p["expenses"]))
s, bs = call("GET", "/api/ledger/balance-sheet", T)
check("balance sheet: liabilities reported as positive credit balances",
      all(x["net_kobo"] >= 0 for x in bs["liabilities"]), str([x["net_kobo"] for x in bs["liabilities"]]))

# ---------------------------------------------------------------- orders / inventory
s, prods = call("GET", f"/api/catalog/products?vendor_id={v1}", T)
prod = next(p for p in prods if p["qty_available"] > 10)
s, whs = call("GET", "/api/inventory/warehouses", T)


def manual_order(qty=1, phone="08031112222", payment="COD", price=None):
    item = {"product_id": prod["id"], "qty": qty}
    if price is not None:
        item["unit_price_kobo"] = price
    return call("POST", "/api/orders", T, {
        "vendor_id": v1, "customer_name": "Probe Cust", "customer_phone": phone,
        "delivery_state": "Kano", "delivery_city": "Kano", "payment_method": payment, "items": [item]})


s, b = manual_order(qty=-3)
check("orders: negative quantity rejected", s == 400, f"{s} accepted")
s, b = manual_order(qty=0)
check("orders: zero quantity rejected", s == 400, f"{s} accepted")

s, o = manual_order(qty=2)
assert s == 200, o
oid = o["id"]
WH["id"] = o["warehouse_id"]


def bal():
    s, rows = call("GET", f"/api/inventory/balances?vendor_id={v1}", T)
    row = next(r for r in rows if r["product_id"] == prod["id"] and r["warehouse_id"] == WH["id"])
    return row["qty_physical"], row["qty_reserved"], row["qty_damaged"]


p0, r0, d0 = bal()
call("POST", f"/api/orders/{oid}/status", T, {"to_status": "READY_FOR_DISPATCH", "note": "probe skip confirm"})
s, zones = call("GET", "/api/dispatch/zones", T)
s, d = call("POST", "/api/dispatch/deliveries", T, {"order_id": oid, "mode": "INTERSTATE", "zone_id": zones[0]["id"]})
check("dispatch: create dispatch works", s == 200, f"{s} {str(d)[:100]}")
did = d["id"]
call("POST", f"/api/dispatch/deliveries/{did}/status", T, {"to_status": "DISPATCHED"})
s, b = call("POST", f"/api/dispatch/deliveries/{did}/status", T, {"to_status": "DELIVERED"})
check("dispatch: delivery can be marked delivered", s == 200, f"{s} {str(b)[:90]}")
s, ordr = call("GET", f"/api/orders/{oid}", T)
ev = [e for e in ordr["events"] if e["event_type"] == "STATUS_CHANGE"]
p1, r1, d1 = bal()
check("inventory: delivery deducts physical stock", p1 == p0 - 2, f"{p0}->{p1}")

# confirmation attempt on a DELIVERED order must not cancel it
s, b = call("POST", f"/api/confirmations/{oid}/attempt", T, {"outcome": "CUSTOMER_REJECTED", "note": "probe"})
s, ordr = call("GET", f"/api/orders/{oid}", T)
check("confirmations: a delivered order cannot be cancelled via a confirmation attempt",
      ordr["status"] == "DELIVERED", f"status now {ordr['status']}")

# COD flow
s, cols = call("GET", "/api/cod/collections?status=PENDING_VERIFICATION", T)
col = next((c for c in cols if c["order_id"] == oid), None)
check("cod: delivery auto-creates pending collection", col is not None)
if col:
    # zero-collected verification on its own delivered order
    s, oz = manual_order(qty=1, phone="08031112299")
    ozid = oz["id"]
    call("POST", f"/api/orders/{ozid}/status", T, {"to_status": "READY_FOR_DISPATCH", "note": "skip"})
    s, dz = call("POST", "/api/dispatch/deliveries", T, {"order_id": ozid, "mode": "INTERSTATE", "zone_id": zones[0]["id"]})
    call("POST", f"/api/dispatch/deliveries/{dz['id']}/status", T, {"to_status": "DISPATCHED"})
    call("POST", f"/api/dispatch/deliveries/{dz['id']}/status", T, {"to_status": "DELIVERED"})
    s, cz = call("GET", "/api/cod/collections?status=PENDING_VERIFICATION", T)
    colz = next((c for c in cz if c["order_id"] == ozid), None)
    s, b = call("POST", f"/api/cod/collections/{colz['id']}/verify", T, {"note": "nothing collected"})
    check("cod: verifying a zero-collected record does not 500", s != 500, f"{s} {str(b)[:80]}")
    s, b = call("POST", "/api/cod/collections", T, {"order_id": oid, "collected_kobo": -100})
    check("cod: negative collected amount rejected", s == 400, f"{s}")
    s, b = call("POST", "/api/cod/collections", T, {"order_id": oid, "collected_kobo": col["expected_kobo"] - 5000})
    s, c2 = call("GET", "/api/cod/collections", T)
    col = next(c for c in c2 if c["order_id"] == oid)
    je0 = len(call("GET", "/api/ledger/journals?limit=300", T)[1])
    s, b = call("POST", f"/api/cod/collections/{col['id']}/verify", T, {"note": "short 50 NGN"})
    je1 = len(call("GET", "/api/ledger/journals?limit=300", T)[1])
    s, b = call("POST", f"/api/cod/collections/{col['id']}/verify", T, {"note": "again"})
    je2 = len(call("GET", "/api/ledger/journals?limit=300", T)[1])
    check("cod: a discrepancy collection can only be verified once (no duplicate journals)",
          je2 == je1, f"journals {je0}->{je1}->{je2}")
    s, st = call("POST", "/api/settlements/build", T, {"vendor_id": v1})
    check("settlements: a verified-with-discrepancy collection is settleable",
          s == 200 and any(i["collection_id"] == col["id"] for i in call("GET", f"/api/settlements/{st['id']}", T)[1]["items"]),
          f"{s} {str(st)[:100]}")

# returns: delivered then returned must restock
s, o2 = manual_order(qty=1, phone="08031112223")
o2id = o2["id"]
call("POST", f"/api/orders/{o2id}/status", T, {"to_status": "READY_FOR_DISPATCH", "note": "skip"})
s, d2 = call("POST", "/api/dispatch/deliveries", T, {"order_id": o2id, "mode": "INTERSTATE", "zone_id": zones[0]["id"]})
call("POST", f"/api/dispatch/deliveries/{d2['id']}/status", T, {"to_status": "FAILED", "failure_reason": "no one home"})
pA, rA, dA = bal()
call("POST", f"/api/dispatch/deliveries/{d2['id']}/status", T, {"to_status": "RETURNING"})
call("POST", f"/api/dispatch/deliveries/{d2['id']}/status", T, {"to_status": "RETURNED"})
pB, rB, dB = bal()
check("inventory: failed-delivery return frees reservation without double counting stock",
      dB == dA and rB == rA - 1, f"physical {pA}->{pB} reserved {rA}->{rB} damaged {dA}->{dB}")
s, ordr2 = call("GET", f"/api/orders/{o2id}", T)
evs = [(e["from_status"], e["to_status"]) for e in ordr2["events"] if e["event_type"] == "STATUS_CHANGE"]
check("dispatch: order events record the real previous status", all(f != t for f, t in evs), str(evs))

# manual stock adjust cannot silently clamp
s, balrows = call("GET", f"/api/inventory/balances?vendor_id={v1}", T)
brow = next(r for r in balrows if r["product_id"] == prod["id"])
s, b = call("POST", "/api/inventory/adjust", T, {"balance_id": brow["id"], "delta_physical": -10_000, "reason": "probe"})
check("inventory: adjustment below zero/reserved is rejected", s == 400, f"{s} accepted")

# ---------------------------------------------------------------- charges
s, b = call("POST", "/api/charges/rules", T, {"name": "probe rule", "charge_type": "WAYBILL", "amount_kobo": 777})
s, rules = call("GET", "/api/charges/rules", T)
rr = next((r for r in rules if r["name"] == "probe rule"), None)
check("charges: rule created without effective_from is effective immediately",
      rr is not None and rr["effective_from"] is not None, str(rr and rr["effective_from"]))
if rr:
    s, b = call("PATCH", f"/api/charges/rules/{rr['id']}", T, {"name": "probe rule", "charge_type": "WAYBILL",
                                                                  "effective_from": "2026-01-01T00:00:00"})
    check("charges: rule update with an ISO date string works", s == 200, f"{s} {str(b)[:80]}")

# ---------------------------------------------------------------- access control
TR = login("rider@keyway.ng")
for path in ("/api/ledger/trial-balance", "/api/reports/financial", "/api/audit", "/api/settlements",
             "/api/cod/collections", "/api/reports/export/ledger"):
    s, b = call("GET", path, TR)
    check(f"authz: rider (dashboard.view only) cannot read {path}", s == 403, f"{s}")
TW = login("warehouse@keyway.ng")
s, b = call("GET", "/api/reports/export/orders", TW)
s2, b2 = call("GET", "/api/ledger/journals", TW)
check("authz: warehouse manager cannot read ledger journals", s2 == 403, f"{s2}")

# ---------------------------------------------------------------- recognition
s, conv = call("POST", "/api/whatsapp/simulator/send", T, {
    "from_phone": "08012345001", "wa_message_id": "PROBE-1",
    "text": "Send 1 black sneakers to Musa, Benin 08012345678"})
s, drafts = call("GET", "/api/orders/drafts", T)
dr = next(d for d in drafts if d["id"] == conv["draft_id"])
s, dd = call("GET", f"/api/orders/drafts/{dr['id']}", T)
price = (dd["extracted"] or {}).get("unit_price_kobo")
check("recognition: a phone number is never parsed as a price", not price, f"unit_price_kobo={price}")
s, conv = call("POST", "/api/whatsapp/simulator/send", T, {
    "from_phone": "08012345001", "wa_message_id": "PROBE-2",
    "text": "Send black sneakers size 42 to Musa, 08012345678, Kano"})
s, dd = call("GET", f"/api/orders/drafts/{conv['draft_id']}", T)
q = (dd["extracted"] or {}).get("quantity")
check("recognition: a shoe size is not read as quantity", q != 42, f"quantity={q}")

# webhook forgery
s, wa = call("PUT", "/api/whatsapp/account", T, {"mode": "CLOUD_API"})
s, b = call("POST", "/api/whatsapp/webhook", None, {"entry": []})
check("webhook: unsigned POST rejected in CLOUD_API mode when no app secret configured", s in (401, 403, 503), f"{s}")
call("PUT", "/api/whatsapp/account", T, {"mode": "SIMULATOR"})

# unverified contact must not be trusted
s, vlist = call("GET", "/api/vendors", T)
s, b = call("POST", f"/api/vendors/{v1}/contacts", T, {"name": "Unverified", "phone": "08055500077", "wa_verified": False})
s, conv = call("POST", "/api/whatsapp/simulator/send", T, {
    "from_phone": "08055500077", "wa_message_id": "PROBE-3", "text": "Send 1 black sneakers to Ada, 08099999999, Kano"})
check("whatsapp: sender with an UNVERIFIED contact is not auto-matched to the vendor",
      conv.get("vendor_id") is None, f"matched vendor {conv.get('vendor_id')}")

# ---------------------------------------------------------------- identity
TV = login("portal@kanofashion.ng")
s, b = call("GET", "/api/roles", TV)
check("authz: vendor portal user cannot read the staff role/permission catalog", s == 403, f"{s}")

print()
bugs = [n for n, ok in results if not ok]
print(f"{len(results) - len(bugs)}/{len(results)} checks passed; {len(bugs)} confirmed bug(s)")
sys.exit(1 if bugs else 0)
