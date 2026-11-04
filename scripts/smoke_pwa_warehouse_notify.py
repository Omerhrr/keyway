#!/usr/bin/env python3
"""Smoke tests for PWA polish / multi-warehouse / notification rules additions."""
import json
import urllib.request

BASE = "http://localhost:8000/api"
TOKEN = None
OK = FAIL = 0


def req(method, path, body=None, expect=200, silent=False):
    global TOKEN, OK, FAIL
    r = urllib.request.Request(BASE + path, method=method)
    r.add_header("Content-Type", "application/json")
    if TOKEN:
        r.add_header("Authorization", f"Bearer {TOKEN}")
    data = json.dumps(body).encode() if body is not None else None
    try:
        with urllib.request.urlopen(r, data) as res:
            code, payload = res.status, json.loads(res.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        code, payload = e.code, json.loads(e.read().decode() or "{}")
    label = f"{method} {path}"
    if isinstance(expect, int):
        good = code == expect
    else:
        good = code in expect
    if good:
        OK += 1
        if not silent:
            print(f"  ok  {label} -> {code}")
    else:
        FAIL += 1
        print(f" FAIL {label} -> {code} {json.dumps(payload)[:200]}")
    return code, payload


print("== auth ==")
_, r = req("POST", "/auth/login", {"email": "owner@keyway.ng", "password": "Keyway@2026"})
TOKEN = r.get("access_token", "")

print("== warehouses (multi-warehouse) ==")
import time
_ts = str(int(time.time()))[-6:]
NEW_CODE = f"WH-S{_ts}"
_, whs = req("GET", "/inventory/warehouses")
wh_lag = next(w for w in whs if w["code"] == "WH-LAG")
wh_kan = next(w for w in whs if w["code"] == "WH-KAN")
print(f"     warehouses: {[w['code'] for w in whs]}, default={[w['code'] for w in whs if w['is_default']]}")

# create a new warehouse
code, new_wh = req("POST", "/inventory/warehouses", {
    "code": NEW_CODE, "name": "Abuja Central", "city": "Abuja", "state": "FCT", "is_default": False})
# duplicate code must fail
req("POST", "/inventory/warehouses", {"code": NEW_CODE, "name": "Dup"}, expect=400)
# patch rename
req("PATCH", f"/inventory/warehouses/{new_wh['id']}", {"name": "Abuja Central Warehouse"})
# set default -> previous default cleared
req("PATCH", f"/inventory/warehouses/{new_wh['id']}", {"is_default": True})
_, whs = req("GET", "/inventory/warehouses")
defaults = [w["code"] for w in whs if w["is_default"]]
assert defaults == [NEW_CODE], f"expected single default {NEW_CODE}, got {defaults}"
print(f"     default after switch: {defaults} (exclusive OK)")
# cannot deactivate the default
req("PATCH", f"/inventory/warehouses/{new_wh['id']}", {"is_active": False}, expect=400)
# restore default to WH-LAG, then the test warehouse can be deactivated
req("PATCH", f"/inventory/warehouses/{wh_lag['id']}", {"is_default": True})
req("PATCH", f"/inventory/warehouses/{new_wh['id']}", {"is_active": False})
print("     default restored to WH-LAG; test warehouse deactivated OK")
# unused warehouse can be deleted; used ones cannot
req("DELETE", f"/inventory/warehouses/{new_wh['id']}")
req("DELETE", f"/inventory/warehouses/{wh_lag['id']}", expect=400)
print("     delete guard OK (unused deleted, default rejected)")
# add a location
req("POST", "/inventory/locations", {"warehouse_id": wh_kan["id"], "code": f"K{_ts[-2:]}-SHELF", "kind": "SHELF"})

print("== manual order with warehouse override ==")
_, vendors = req("GET", "/vendors")
vendor_kfh = next(v for v in vendors if v["code"] == "VD-1001")  # Kano Fashion Hub - stocked at WH-KAN
vid = vendor_kfh["id"]
_, prods = req("GET", f"/catalog/products?vendor_id={vid}")
prod = next(p for p in prods if p.get("qty_available", 0) > 0)
print(f"     product: {prod['sku']} avail={prod['qty_available']}")
# order pinned to Kano annex: WH-KAN stocks VD-1001 only; pick a product stocked there
code, order = req("POST", "/orders", {
    "vendor_id": vid, "customer_name": "Smoke Test", "customer_phone": "08011100099",
    "delivery_city": "Lagos", "delivery_state": "Lagos",
    "items": [{"product_id": prod["id"], "qty": 1}], "warehouse_id": wh_kan["id"]})
print(f"     order {order.get('reference')} warehouse_id={order.get('warehouse_id')} name={order.get('warehouse_name')}")
assert order.get("warehouse_id") == wh_kan["id"], "warehouse override not applied"
assert order.get("warehouse_name") == "Kano Annex", f"create response warehouse_name={order.get('warehouse_name')}"
code, order_detail = req("GET", f"/orders/{order['id']}")
assert order_detail.get("warehouse_name") == "Kano Annex", f"detail warehouse_name={order_detail.get('warehouse_name')}"
print("     detail warehouse_name OK:", order_detail["warehouse_name"])
# invalid warehouse rejected
req("POST", "/orders", {
    "vendor_id": vid, "customer_name": "Bad", "customer_phone": "08011100098",
    "items": [{"product_id": prod["id"], "qty": 1}], "warehouse_id": 99999}, expect=400)

print("== order status change -> notification ==")
code, _ = req("POST", f"/orders/{order['id']}/status", {"to_status": "PROCESSING", "note": "smoke"})
_, notifs = req("GET", "/notifications?limit=50")
sc = [n for n in notifs if n["event_type"] == "ORDER_STATUS_CHANGED" and n["entity_id"] == str(order["id"])]
print(f"     ORDER_STATUS_CHANGED rows for order: {len(sc)}; first title: {sc[0]['title'] if sc else 'NONE'}")
assert sc, "no ORDER_STATUS_CHANGED notification created"

print("== notification rules ==")
_, rules = req("GET", "/notification-rules")
events = [e["event_type"] for e in rules["events"]]
assert "ORDER_STATUS_CHANGED" in events, "ORDER_STATUS_CHANGED missing from catalog"
seeded = [r for r in rules["rules"] if r["name"] == "Order status changes -> ops"]
print(f"     catalog has ORDER_STATUS_CHANGED: True; seeded rule present: {bool(seeded)}")
# create + test + delete a rule
code, rule = req("POST", "/notification-rules", {
    "name": "smoke-rule-status", "event_type": "ORDER_STATUS_CHANGED",
    "target_scope": "ALL_STAFF", "channel": "IN_APP"})
code, res = req("POST", f"/notification-rules/{rule['id']}/test")
print(f"     rule test -> sent={res['sent']} failed={res['failed']} channel={res['channel']}")
assert res["sent"] >= 1
req("DELETE", f"/notification-rules/{rule['id']}")

print("== warehouse scoping on balances ==")
_, bal_all = req("GET", "/inventory/balances")
_, bal_kan = req("GET", f"/inventory/balances?warehouse_id={wh_kan['id']}")
assert all(b["warehouse_id"] == wh_kan["id"] for b in bal_kan)
print(f"     balances: total={len(bal_all)} kano-scoped={len(bal_kan)}")

print(f"\nRESULT: {OK} ok / {FAIL} failed")
raise SystemExit(1 if FAIL else 0)
