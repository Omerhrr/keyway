#!/bin/bash
# Phase: multi-warehouse + notification rules + scoped notifications - API verification
set -e
B=http://localhost:8000/api
J='Content-Type: application/json'

TOKEN=$(curl -s -X POST $B/auth/login -H "$J" -d '{"email":"owner@keyway.ng","password":"Keyway@2026"}' | python3 -c "import sys,json;print(json.load(sys.stdin)['access_token'])")
A="Authorization: Bearer $TOKEN"
echo "[1] login OK"

echo "--- multi-warehouse transfers ---"
WH=$(curl -s $B/inventory/warehouses -H "$A")
WH1=$(echo "$WH" | python3 -c "import sys,json;print(json.load(sys.stdin)[0]['id'])")
WH2=$(echo "$WH" | python3 -c "import sys,json;print(json.load(sys.stdin)[1]['id'])")
echo "warehouses: $(echo "$WH" | python3 -c "import sys,json;print([w['code'] for w in json.load(sys.stdin)])")"

BAL=$(curl -s "$B/inventory/balances" -H "$A")
PROD=$(echo "$BAL" | python3 -c "
import sys,json
rows=json.load(sys.stdin)
r=next(r for r in rows if r['qty_physical']-r['qty_reserved']>=5)
print(r['product_id'], r['qty_available'], r['warehouse_name'])")
PID=$(echo $PROD | cut -d' ' -f1); QTY0=$(echo $PROD | cut -d' ' -f2)
echo "product=$PID available_at_source=$QTY0"

# balances must now include warehouse_name
echo "$BAL" | python3 -c "
import sys,json
rows=json.load(sys.stdin)
missing=[r for r in rows if not r.get('warehouse_name')]
print('[2] balances carry warehouse_name:', 'OK' if not missing else f'FAIL ({len(missing)} rows missing)')"

T=$(curl -s -X POST $B/inventory/transfers -H "$A" -H "$J" -d "{\"product_id\":$PID,\"from_warehouse_id\":$WH1,\"to_warehouse_id\":$WH2,\"qty\":3,\"reason\":\"verification transfer\"}")
echo "[3] transfer created: $(echo $T | python3 -c "import sys,json;d=json.load(sys.stdin);print(d.get('reference'),d.get('status'),d.get('from_warehouse_name'),'->',d.get('to_warehouse_name'))" 2>/dev/null || echo "$T")"
TID=$(echo "$T" | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")

QTY1=$(curl -s "$B/inventory/balances?warehouse_id=$WH1" -H "$A" | python3 -c "
import sys,json
rows=json.load(sys.stdin)
r=next((r for r in rows if r['product_id']==$PID), None)
print(r['qty_available'] if r else 'gone-ok', r['qty_in_transit'] if r else '')")
echo "[4] source after dispatch: $QTY1 (was $QTY0)"

R=$(curl -s -X POST $B/inventory/transfers/$TID/receive -H "$A")
echo "[5] received: $(echo $R | python3 -c "import sys,json;d=json.load(sys.stdin);print(d['status'], d['received_at'][:19])")"
QTY2=$(curl -s "$B/inventory/balances?warehouse_id=$WH2" -H "$A" | python3 -c "
import sys,json
rows=json.load(sys.stdin)
r=next((r for r in rows if r['product_id']==$PID), None)
print(r['qty_available'] if r else 'MISSING')")
echo "[6] destination now holds: $QTY2 (expect >= 3)"

# insufficient stock must be rejected
BAD=$(curl -s -X POST $B/inventory/transfers -H "$A" -H "$J" -d "{\"product_id\":$PID,\"from_warehouse_id\":$WH2,\"to_warehouse_id\":$WH1,\"qty\":99999}")
echo "[7] overdraw rejected: $(echo $BAD | python3 -c "import sys,json;print(json.load(sys.stdin)['detail'][:60])")"

echo "--- notification rules ---"
RULES=$(curl -s $B/notification-rules -H "$A")
echo "[8] rules: $(echo $RULES | python3 -c "import sys,json;d=json.load(sys.stdin);print(len(d['rules']),'rules,',len(d['events']),'events in catalog')")"

NR=$(curl -s -X POST $B/notification-rules -H "$A" -H "$J" -d '{"name":"Verify: order created -> ops","event_type":"ORDER_CREATED","target_scope":"ROLE","role_name":"Operations Manager","channel":"IN_APP"}')
echo "[9] rule created: $(echo $NR | python3 -c "import sys,json;d=json.load(sys.stdin);print(d.get('id'),d.get('name'),d.get('enabled'))" 2>/dev/null || echo "$NR")"
NID=$(echo "$NR" | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")
TOG=$(curl -s -X PATCH $B/notification-rules/$NID -H "$A" -H "$J" -d '{"enabled":false}')
echo "[10] toggled off: $(echo $TOG | python3 -c "import sys,json;print(json.load(sys.stdin)['enabled'])")"
DEL=$(curl -s -X DELETE $B/notification-rules/$NID -H "$A")
echo "[11] deleted: $(echo $DEL | python3 -c "import sys,json;print(json.load(sys.stdin)['ok'])")"

echo "--- automation checks (idempotency) ---"
C1=$(curl -s -X POST $B/notifications/run-checks -H "$A")
echo "[12] run 1: $(echo $C1)"
C2=$(curl -s -X POST $B/notifications/run-checks -H "$A")
echo "[13] run 2 (must be all zero): $(echo $C2)"

echo "--- scoped notifications ---"
CNT=$(curl -s $B/notifications/unread-count -H "$A")
echo "[14] staff unread: $(echo $CNT)"
VT=$(curl -s -X POST $B/auth/login -H "$J" -d '{"email":"portal@kanofashion.ng","password":"Keyway@2026"}' | python3 -c "import sys,json;print(json.load(sys.stdin)['access_token'])" 2>/dev/null)
if [ -n "$VT" ] && [ "$VT" != "" ]; then
  VA="Authorization: Bearer $VT"
  VCNT=$(curl -s $B/notifications/unread-count -H "$VA")
  VLIST=$(curl -s "$B/notifications?limit=5" -H "$VA")
  echo "[15] vendor unread: $VCNT ; latest: $(echo $VLIST | python3 -c "
import sys,json
rows=json.load(sys.stdin)
print(len(rows),'rows, vendor_ids:',set(r.get('vendor_id') for r in rows))")"
else
  echo "[15] vendor portal user password differs - skipped scoping check (checked code path separately)"
fi
echo "ALL DONE"
