"""Rich demo seed. Idempotent: runs only on an empty database.

Deliberately exercises real code paths (ingestion pipeline, draft conversion,
collection verification, settlement build) so demo data is exactly what the
application would have produced.
"""
import json
from datetime import timedelta
from app.core.config import settings
from app.core.db import utcnow
from app.core.security import hash_password
from app.core.ids import next_ref
from app.core.ledger import post_journal
from app.modules.identity_models import Role, Permission, RolePermission, User
from app.modules.vendors_models import Vendor, VendorContact, VendorAgreement
from app.modules.catalog_models import Product, ProductVariant, ProductAlias
from app.modules.inventory_models import (Warehouse, WarehouseLocation, InventoryBalance,
                                          StockReceipt, StockReceiptLine)
from app.modules.delivery_models import DeliveryZone, Rider, Carrier
from app.modules.orders_models import Customer, Order, OrderItem
from app.modules.whatsapp_models import WhatsAppAccount, MessageTemplate
from app.modules.activity_models import Notification
from app.modules.ledger_models import Account, Expense, FinancialPeriod, BankTransaction
from app.modules.inventory import get_or_create_balance, _movement
from app.modules.orders import create_order_from_draft, upsert_customer, add_event
from app.modules.inventory import reserve_stock, consume_reservations
from app.modules.charges import apply_charge
from app.modules.whatsapp import ingest_message
from app.modules.notify import notify

DEMO_PASSWORD = "Keyway@2026"

PERMISSIONS = [
    # (codename, module)
    ("dashboard.view", "dashboard"),
    ("vendors.manage", "vendors"), ("vendors.view", "vendors"),
    ("catalog.manage", "catalog"), ("catalog.view", "catalog"),
    ("inventory.manage", "inventory"), ("inventory.view", "inventory"),
    ("orders.manage", "orders"), ("orders.view", "orders"),
    ("confirmations.manage", "confirmations"),
    ("conversations.manage", "conversations"), ("conversations.view", "conversations"),
    ("whatsapp.manage", "whatsapp"),
    ("dispatch.view", "dispatch"), ("dispatch.manage", "dispatch"),
    ("cod.manage", "cod"),
    ("charges.manage", "charges"),
    ("settlements.manage", "settlements"), ("settlements.approve", "settlements"),
    ("finance.manage", "finance"),
    ("reports.view", "reports"),
    ("settings.manage", "settings"),
    ("audit.view", "audit"),
]

ROLES = {
    "Business Owner": "*",
    "Administrator": "*",
    "Operations Manager": ["dashboard.view", "vendors.manage", "vendors.view", "catalog.manage", "catalog.view",
                           "inventory.view", "orders.manage", "orders.view", "confirmations.manage",
                           "conversations.manage", "conversations.view", "whatsapp.manage", "dispatch.view",
                           "dispatch.manage", "reports.view", "audit.view"],
    "Warehouse Manager": ["dashboard.view", "catalog.view", "inventory.manage", "inventory.view",
                          "orders.view", "reports.view"],
    "Warehouse Staff": ["catalog.view", "inventory.manage", "inventory.view", "orders.view"],
    "Order Processing Staff": ["dashboard.view", "catalog.view", "inventory.view", "orders.manage", "orders.view",
                               "confirmations.manage", "conversations.manage", "conversations.view", "reports.view"],
    "Customer Confirmation Agent": ["dashboard.view", "orders.view", "confirmations.manage"],
    "Dispatcher": ["dashboard.view", "orders.view", "dispatch.view", "dispatch.manage"],
    "Rider": ["dashboard.view"],
    "Finance Manager": ["dashboard.view", "cod.manage", "charges.manage", "settlements.manage",
                        "settlements.approve", "finance.manage", "reports.view", "audit.view"],
    "Accountant": ["dashboard.view", "cod.manage", "settlements.manage", "finance.manage", "reports.view"],
    "Auditor": ["dashboard.view", "vendors.view", "catalog.view", "inventory.view", "orders.view",
                "conversations.view", "dispatch.view", "reports.view", "audit.view", "finance.manage"],
    "Read Only Staff": ["dashboard.view", "vendors.view", "catalog.view", "inventory.view", "orders.view",
                        "conversations.view", "dispatch.view", "reports.view", "audit.view"],
    "Vendor": [],
}

VENDORS = [
    {"code": "VD-1001", "name": "Kano Fashion Hub", "email": "hello@kanofashion.ng", "city": "Kano",
     "state": "Kano", "phone": "08012345001",
     # | phone, name, primary
     "contacts": [("08012345001", "Aisha Bello", True), ("08012345002", "Musa Ali", False)]},
    {"code": "VD-1002", "name": "Zaria Gadgets", "email": "sales@zariagadgets.ng", "city": "Zaria",
     "state": "Kaduna", "phone": "08023456001",
     "contacts": [("08023456001", "Emeka Okafor", True), ("08023456002", "Ngozi Ade", False)]},
    {"code": "VD-1003", "name": "Abuja Home Essentials", "email": "info@abujahome.ng", "city": "Abuja",
     "state": "FCT", "phone": "08034567001",
     "contacts": [("08034567001", "Fatima Sule", True)]},
]

# vendor code -> [(sku, name, category, price_naira, qty, reorder, aliases, variants)]
PRODUCTS = {
    "VD-1001": [
        ("KFH-SNK-001", "Black Sneakers", "Footwear", 45000, 24, 5,
         ["sneakers", "sneaker", "shoes", "trainers", "black sneakers"],
         [("KFH-SNK-001-42", "Size 42"), ("KFH-SNK-001-44", "Size 44")]),
        ("KFH-ANK-002", "Ankara Gown", "Clothing", 18000, 40, 6,
         ["ankara", "gown", "ankara gown"], []),
        ("KFH-SLP-003", "Leather Slippers", "Footwear", 9500, 35, 8,
         ["slippers", "palm slippers"], []),
        ("KFH-HDJ-004", "Denim Hoodie", "Clothing", 15000, 18, 5,
         ["hoodie", "denim hoodie", "jacket"], []),
        ("KFH-KFT-005", "Embroidered Kaftan", "Clothing", 22000, 15, 4,
         ["kaftan", "kaftans"], []),
        ("KFH-BAG-006", "Leather Handbag", "Accessories", 27000, 12, 4,
         ["handbag", "bag", "purse"], []),
        ("KFH-CAP-007", "Face Cap", "Accessories", 6500, 50, 10,
         ["cap", "face cap", "hat"], []),
        ("KFH-NCK-008", "Beaded Necklace Set", "Accessories", 8000, 20, 5,
         ["necklace", "beads"], []),
        ("KFH-DNM-009", "Denim Jacket", "Clothing", 26000, 10, 4,
         ["denim jacket", "jean jacket"], []),
        ("KFH-SKT-010", "Ankara Skirt & Blouse", "Clothing", 20000, 14, 4,
         ["skirt", "blouse", "skirt and blouse"], []),
    ],
    "VD-1002": [
        ("ZRG-BLN-001", "Standing Blender 1.5L", "Appliances", 45000, 16, 4,
         ["blender", "blender 1.5l", "liquidiser"], []),
        ("ZRG-EAR-002", "Wireless Earbuds Pro", "Electronics", 28000, 30, 6,
         ["earbuds", "earphones", "buds", "airpods"], []),
        ("ZRG-PWB-003", "Power Bank 20000mAh", "Electronics", 22000, 25, 5,
         ["power bank", "powerbank"], []),
        ("ZRG-CHG-004", "Fast Charger 30W", "Electronics", 8500, 60, 12,
         ["charger", "fast charger", "adapter"], []),
        ("ZRG-WTC-005", "Smart Watch S8", "Electronics", 38000, 12, 4,
         ["smart watch", "smartwatch", "watch"], []),
        ("ZRG-HDR-006", "Hair Dryer 2000W", "Appliances", 16500, 14, 4,
         ["hair dryer", "dryer"], []),
        ("ZRG-KTL-007", "Electric Kettle 1.8L", "Appliances", 12000, 18, 5,
         ["kettle", "electric kettle"], []),
        ("ZRG-FAN-008", "Rechargeable Fan 12in", "Appliances", 31000, 9, 3,
         ["fan", "rechargeable fan"], []),
        ("ZRG-EXT-009", "Extension Box 4-Way", "Electronics", 7000, 40, 10,
         ["extension", "extension box", "socket"], []),
        ("ZRG-HDM-010", "HDMI Cable 2m", "Electronics", 4500, 45, 10,
         ["hdmi", "hdmi cable"], []),
    ],
    "VD-1003": [
        ("AHE-BED-001", "6x6 Bedding Set", "Home", 32000, 15, 4,
         ["bedding", "duvet", "bedsheet", "bedding set"], []),
        ("AHE-POT-002", "Non-stick Pot Set", "Kitchen", 41000, 10, 3,
         ["pot", "pots", "pot set", "nonstick pot"], []),
        ("AHE-CWK-003", "Cookware Set 7pc", "Kitchen", 55000, 8, 3,
         ["cookware", "cookware set"], []),
        ("AHE-CUR-004", "Blackout Curtains", "Home", 24000, 13, 4,
         ["curtain", "curtains"], []),
        ("AHE-MAT-005", "3D Floor Mat", "Home", 15000, 22, 6,
         ["mat", "floor mat", "carpet"], []),
        ("AHE-BTL-006", "Water Bottle Set", "Kitchen", 9000, 30, 8,
         ["bottle", "water bottle", "flask"], []),
        ("AHE-STB-007", "Storage Box Large", "Home", 7500, 35, 8,
         ["storage box", "box"], []),
        ("AHE-WCL-008", "Wall Clock Modern", "Decor", 6500, 18, 5,
         ["wall clock", "clock"], []),
        ("AHE-IRB-009", "Ironing Board", "Home", 19000, 7, 3,
         ["iron board", "ironing board"], []),
        ("AHE-DNS-010", "Dinner Set 24pc", "Kitchen", 48000, 6, 2,
         ["dinner set", "plates", "dish set"], []),
    ],
}

ZONES = [
    ("Z-LAG-MAIN", "Lagos Mainland", "Lagos", ["Surulere", "Yaba", "Ikeja"], 250000),
    ("Z-LAG-ISL", "Lagos Island", "Lagos", ["Lekki", "Victoria Island", "Ikoyi"], 400000),
    ("Z-ABJ", "Abuja Metro", "FCT", ["Abuja", "Gwarinpa", "Wuse", "Kubwa"], 600000),
    ("Z-KAD", "Kaduna Metro", "Kaduna", ["Kaduna", "Zaria"], 700000),
]

USERS = [
    ("owner@keyway.ng", "Adaeze Okafor", "Business Owner", True),
    ("admin@keyway.ng", "System Admin", "Administrator", True),
    ("ops@keyway.ng", "Bola Adeyemi", "Operations Manager", False),
    ("warehouse@keyway.ng", "Ibrahim Musa", "Warehouse Manager", False),
    ("whstaff@keyway.ng", "Chika Okeke", "Warehouse Staff", False),
    ("orders@keyway.ng", "Titi Alade", "Order Processing Staff", False),
    ("confirm@keyway.ng", "Segun Balogun", "Customer Confirmation Agent", False),
    ("dispatch@keyway.ng", "Kabir Lawal", "Dispatcher", False),
    ("rider@keyway.ng", "Sule Danjuma", "Rider", False),
    ("finance@keyway.ng", "Ngozi Eze", "Finance Manager", False),
    ("accountant@keyway.ng", "Yusuf Bala", "Accountant", False),
    ("auditor@keyway.ng", "Grace Nwosu", "Auditor", False),
    ("readonly@keyway.ng", "View Only", "Read Only Staff", False),
    ("portal@kanofashion.ng", "Aisha Bello (Portal)", "Vendor", False),
]

CUSTOMERS = [
    ("VD-1001", "Musa Alhassan", "08012345678", "Kaduna", "Kaduna", "Barnawa"),
    ("VD-1001", "Amina Yusuf", "08098765432", "FCT", "Abuja", "Gwarinpa"),
    ("VD-1001", "Grace Ade", "08033344455", "Lagos", "Surulere", "Adeniran Ogunsanya"),
    ("VD-1002", "Chinedu Okeke", "08044455566", "Lagos", "Lekki", "Admiralty Way"),
    ("VD-1002", "Blessing Eze", "08055566677", "Lagos", "Ikeja", "Allen Avenue"),
    ("VD-1002", "Tunde Bala", "08066677788", "Kaduna", "Kaduna", "Ungwan Rimi"),
    ("VD-1003", "Sani Garba", "08077788899", "FCT", "Abuja", "Wuse 2"),
    ("VD-1003", "Halima Idris", "08088899900", "Kano", "Kano", "Nassarawa GRA"),
]

CHART = [
    ("1000", "Cash on Hand", "ASSET", "CASH", True),
    ("1010", "Bank Account", "ASSET", "BANK", True),
    ("1200", "COD Clearing", "ASSET", "COD_CLEARING", False),
    ("2100", "Vendor Payables", "LIABILITY", "VENDOR_PAYABLE", False),
    ("3000", "Owner's Equity", "EQUITY", "EQUITY", False),
    ("4000", "Logistics Revenue", "REVENUE", "LOGISTICS_REVENUE", False),
    ("5000", "Operating Expenses", "EXPENSE", "OPERATING_EXPENSE", False),
]

TEMPLATES = [
    ("order_received", "Thank you! We received your order request: {{1}}. Our team is preparing it now."),
    ("order_registered", "Order {{1}} has been registered. We will update you at every step. Thank you!"),
    ("delivery_update", "Update on order {{1}}: {{2}}"),
    ("settlement_notification", "A settlement of {{1}} has been processed to your account. Reference {{2}}."),
]


def seed_notification_rules(db):
    """Idempotently install the default notification rules (runs on every startup,
    so existing databases get upgraded in place)."""
    from app.modules.activity_models import NotificationRule
    defaults = [
        ("WhatsApp order detected", "NEW_WHATSAPP_ORDER", "ALL_STAFF", "", None, "IN_APP"),
        ("Delivery failed -> managers", "DELIVERY_FAILED", "ROLE", "Operations Manager", None, "IN_APP"),
        ("COD discrepancy -> finance", "COD_DISCREPANCY", "ROLE", "Finance Manager", None, "IN_APP"),
        ("Unreconciled COD -> finance", "COD_RECORDED", "ROLE", "Finance Manager", None, "IN_APP"),
        ("Low stock -> warehouse", "LOW_STOCK", "ROLE", "Warehouse Manager", None, "IN_APP"),
        ("Order awaiting confirmation", "ORDER_UNCONFIRMED", "ALL_STAFF", "", None, "IN_APP"),
        ("Order status changes -> ops", "ORDER_STATUS_CHANGED", "ROLE", "Operations Manager", None, "IN_APP"),
        ("Settlement ready -> vendor (WhatsApp)", "SETTLEMENT_READY", "ALL_STAFF", "", None, "IN_APP"),
    ]
    created = 0
    for name, event, scope, role, user_id, channel in defaults:
        if db.query(NotificationRule).filter(NotificationRule.name == name).first():
            continue
        db.add(NotificationRule(name=name, event_type=event, target_scope=scope,
                                role_name=role, user_id=user_id, channel=channel, enabled=True))
        created += 1
    if created:
        db.commit()
        print(f"[seed] notification rules installed: {created}")
    return created


def _bootstrap_production(db):
    """Production first boot: reference data + ONE administrator, no demo data.

    Never creates demo users (known password), demo vendors, stock or opening balances.
    The admin comes from KEYWAY_BOOTSTRAP_ADMIN_EMAIL / _PASSWORD and should change the
    password after first login.
    """
    email = (settings.BOOTSTRAP_ADMIN_EMAIL or "").strip().lower()
    password = settings.BOOTSTRAP_ADMIN_PASSWORD or ""
    if not email or len(password) < 12:
        raise RuntimeError(
            "Empty production database: set KEYWAY_BOOTSTRAP_ADMIN_EMAIL and "
            "KEYWAY_BOOTSTRAP_ADMIN_PASSWORD (min 12 chars) in backend/.env for the first start.")
    now = utcnow()
    perms = {}
    for codename, module in PERMISSIONS:
        p = Permission(codename=codename, module=module, description=codename)
        db.add(p)
        db.flush()
        perms[codename] = p
    roles = {}
    for name, allowed in ROLES.items():
        r = Role(name=name, description=f"{name} role")
        db.add(r)
        db.flush()
        roles[name] = r
        for codename in (perms if allowed == "*" else allowed):
            if codename in perms:
                db.add(RolePermission(role_id=r.id, permission_id=perms[codename].id))
    db.flush()
    db.add(User(email=email, password_hash=hash_password(password),
                full_name=settings.BOOTSTRAP_ADMIN_NAME or "Administrator", phone="",
                role_id=roles["Administrator"].id, department="Management",
                job_title="Administrator", is_superuser=True))
    for code, name, typ, subtype, is_cash in CHART:
        db.add(Account(code=code, name=name, type=typ, subtype=subtype, is_cash=is_cash))
    db.add(Warehouse(code="WH-MAIN", name="Main Warehouse", is_default=True))
    db.add(FinancialPeriod(name=now.strftime("%Y-%m"), start_date=now.replace(day=1),
                           end_date=now, status="OPEN"))
    for name, body in TEMPLATES:
        db.add(MessageTemplate(name=name, category="UTILITY", body=body,
                               variables=[] if "{{1}}" not in body else ["1"]))
    db.add(WhatsAppAccount(display_name="Keyway Logistics", mode="SIMULATOR", status="DISCONNECTED"))
    db.commit()
    print(f"[bootstrap] production reference data created; administrator {email} ready.")


def seed_if_empty(db):
    if db.query(User).count() > 0:
        return False
    if settings.is_production:
        _bootstrap_production(db)
        return True
    print("[seed] empty database detected - seeding rich demo data...")
    _seed(db)
    print("[seed] done.")
    return True


def _seed(db):
    now = utcnow()

    # ---- permissions, roles, users ----------------------------------------
    perms = {}
    for codename, module in PERMISSIONS:
        p = Permission(codename=codename, module=module, description=codename)
        db.add(p)
        db.flush()
        perms[codename] = p
    roles = {}
    for name, allowed in ROLES.items():
        r = Role(name=name, description=f"{name} role")
        db.add(r)
        db.flush()
        roles[name] = r
        if allowed == "*":
            for p in perms.values():
                db.add(RolePermission(role_id=r.id, permission_id=p.id))
        else:
            for codename in allowed:
                if codename in perms:
                    db.add(RolePermission(role_id=r.id, permission_id=perms[codename].id))
    db.flush()

    role_by_name = {r.name: r for r in db.query(Role).all()}
    users = {}
    for email, full_name, role_name, _ in USERS:
        u = User(email=email, password_hash=hash_password(DEMO_PASSWORD), full_name=full_name,
                 phone="08000000000", role_id=role_by_name[role_name].id,
                 department="Operations" if role_name != "Vendor" else "Vendor",
                 job_title=role_name, is_superuser=role_name in ("Business Owner", "Administrator"))
        db.add(u)
        db.flush()
        users[email] = u
    owner = users["owner@keyway.ng"]

    # ---- vendors & contacts ------------------------------------------------
    vendors = {}
    for vdef in VENDORS:
        v = Vendor(code=vdef["code"], name=vdef["name"], email=vdef["email"], phone=vdef["phone"],
                   city=vdef["city"], state=vdef["state"], status="ACTIVE", settlement_frequency="WEEKLY")
        db.add(v)
        db.flush()
        vendors[vdef["code"]] = v
        for phone, cname, primary in vdef["contacts"]:
            db.add(VendorContact(vendor_id=v.id, name=cname, phone=phone, is_primary=primary,
                                 is_whatsapp=True, wa_verified=True, verification_method="PHONE_NUMBER",
                                 verified_at=now - timedelta(days=30)))
        db.add(VendorAgreement(vendor_id=v.id, title="Standard Storage & Fulfilment Agreement",
                               terms="Weekly settlement. Storage charged per pallet per week. COD handling fee applies per collection.",
                               effective_from=now - timedelta(days=30), status="ACTIVE"))
    # vendor portal user scoping
    users["portal@kanofashion.ng"].is_vendor = True
    users["portal@kanofashion.ng"].vendor_id = vendors["VD-1001"].id

    # ---- catalog ------------------------------------------------------------
    products_by_sku = {}
    for vcode, plist in PRODUCTS.items():
        v = vendors[vcode]
        for sku, name, cat, price, qty, reorder, aliases, variants in plist:
            p = Product(vendor_id=v.id, sku=sku, name=name, category=cat, unit="pcs",
                        default_sell_price_kobo=price * 100, reorder_level=reorder)
            db.add(p)
            db.flush()
            products_by_sku[sku] = p
            for al in aliases:
                db.add(ProductAlias(vendor_id=v.id, product_id=p.id, alias=al))
            for vsku, vname in variants:
                db.add(ProductVariant(product_id=p.id, sku=vsku, name=vname))
    db.commit()

    # ---- warehouses, zones, riders, carriers --------------------------------
    wh1 = Warehouse(code="WH-LAG", name="Lagos Main Warehouse", address="12 Oshodi-Apapa Rd",
                    city="Lagos", state="Lagos", is_default=True)
    wh2 = Warehouse(code="WH-KAN", name="Kano Annex", address="5 Zoo Rd", city="Kano", state="Kano")
    db.add_all([wh1, wh2])
    db.flush()
    for w, codes in ((wh1, ["A01-SHELF", "A02-SHELF", "B01-STAGING", "DMG-DAMAGED", "RET-RETURNS"]),
                     (wh2, ["K01-SHELF", "K02-SHELF", "KDMG-DAMAGED"])):
        for code in codes:
            kind = "DAMAGED" if "DAMAGED" in code else ("RETURNS" if "RETURNS" in code else
                   ("STAGING" if "STAGING" in code else "SHELF"))
            db.add(WarehouseLocation(warehouse_id=w.id, code=code, kind=kind))

    zones = {}
    for code, name, state, cities, fee in ZONES:
        z = DeliveryZone(name=name, state=state, cities=cities, base_fee_kobo=fee)
        db.add(z)
        db.flush()
        zones[name] = z

    rider_user = users["rider@keyway.ng"]
    r1 = Rider(full_name="Sule Danjuma", phone="08099887766", vehicle="Boxer Bike", zone_id=zones["Lagos Mainland"].id,
               user_id=rider_user.id)
    r2 = Rider(full_name="Emmanuel Ada", phone="08099887711", vehicle="Tricycle", zone_id=zones["Lagos Island"].id)
    r3 = Rider(full_name="Bashir Umar", phone="08099887722", vehicle="Motorcycle", zone_id=zones["Abuja Metro"].id)
    db.add_all([r1, r2, r3])
    db.add_all([
        Carrier(name="GIG Logistics", kind="INTERSTATE", contact_phone="0700GIGL123", tracking_url="https://gigl-go.com/track/"),
        Carrier(name="ABC Transport", kind="INTERSTATE", contact_phone="0700ABC456"),
    ])
    db.flush()

    # ---- stock receipts -> balances ----------------------------------------
    for vcode, plist in PRODUCTS.items():
        v = vendors[vcode]
        wh = wh2 if vcode == "VD-1001" else wh1
        rc = StockReceipt(reference="PENDING", vendor_id=v.id, warehouse_id=wh.id,
                          batch_ref=f"BATCH-{vcode[-4:]}", status="DRAFT",
                          created_by_user_id=users["whstaff@keyway.ng"].id,
                          created_at=now - timedelta(days=20))
        db.add(rc)
        db.flush()
        rc.reference = next_ref(db, StockReceipt, "reference", "RCV")
        for sku, name, cat, price, qty, reorder, aliases, variants in plist:
            p = products_by_sku[sku]
            received = max(2, qty - 3) if qty <= 12 else qty  # leave headroom for low-stock demos
            db.add(StockReceiptLine(receipt_id=rc.id, product_id=p.id, expected_qty=qty,
                                    received_qty=received, damaged_qty=1 if qty < 10 else 0))
        rc.status = "CONFIRMED"
        rc.confirmed_at = now - timedelta(days=19)
        db.flush()  # lines were added in this transaction (session autoflush is off)
        for line in db.query(StockReceiptLine).filter(StockReceiptLine.receipt_id == rc.id).all():
            b = get_or_create_balance(db, line.product_id, 0, wh.id)
            b.qty_physical += line.received_qty
            b.qty_damaged += line.damaged_qty
            _movement(db, line.product_id, line.variant_id, wh.id, "RECEIVE", line.received_qty,
                      f"Opening receipt {rc.reference}", "stock_receipt", rc.id, None)
        db.commit()

    # Manually set a few low-stock items
    for sku in ("ZRG-FAN-008", "AHE-IRB-009", "AHE-DNS-010"):
        p = products_by_sku[sku]
        b = db.query(InventoryBalance).filter(InventoryBalance.product_id == p.id).first()
        if b:
            b.qty_physical = max(2, p.reorder_level)

    # ---- chart of accounts, opening balances --------------------------------
    accounts = {}
    for code, name, typ, subtype, is_cash in CHART:
        a = Account(code=code, name=name, type=typ, subtype=subtype, is_cash=is_cash)
        db.add(a)
        db.flush()
        accounts[subtype] = a
    post_journal(db, memo="Opening balances - capital injection",
                 source_type="OPENING", source_id=None,
                 lines=[{"account_id": accounts["BANK"].id, "debit_kobo": 5_000_000 * 100},
                        {"account_id": accounts["EQUITY"].id, "credit_kobo": 5_000_000 * 100}],
                 posted_by=owner)
    db.add(FinancialPeriod(name=now.strftime("%Y-%m"), start_date=now.replace(day=1),
                           end_date=now, status="OPEN"))
    db.add(BankTransaction(account_id=accounts["BANK"].id, txn_date=now - timedelta(days=15),
                           direction="CREDIT", amount_kobo=5_000_000 * 100,
                           bank_ref="TRF-OPENING-001", narration="Capital injection"))

    # ---- message templates, whatsapp account ---------------------------------
    for name, body in TEMPLATES:
        db.add(MessageTemplate(name=name, category="UTILITY", body=body,
                               variables=[] if "{{1}}" not in body else ["1"]))
    db.add(WhatsAppAccount(display_name="Keyway Logistics", mode="SIMULATOR", status="CONNECTED"))

    # ---- pricing rules --------------------------------------------------------
    from app.modules.charges_models import ChargeRule
    db.add(ChargeRule(name="Order processing fee (default)", charge_type="ORDER_PROCESSING", scope="GLOBAL",
                      basis="FIXED", amount_kobo=30000, effective_from=now - timedelta(days=30), version=1))
    db.add(ChargeRule(name="COD handling fee (default)", charge_type="COD_HANDLING", scope="GLOBAL",
                      basis="FIXED", amount_kobo=20000, effective_from=now - timedelta(days=30), version=1))
    db.add(ChargeRule(name="Storage fee per pallet (default)", charge_type="STORAGE", scope="GLOBAL",
                      basis="FIXED", amount_kobo=150000, effective_from=now - timedelta(days=30), version=1))
    db.add(ChargeRule(name="Kano Fashion Hub delivery override", charge_type="LOCAL_DELIVERY", scope="VENDOR",
                      vendor_id=vendors["VD-1001"].id, basis="FIXED", amount_kobo=250000,
                      effective_from=now - timedelta(days=30), version=1))
    db.commit()

    # ---- customers -------------------------------------------------------------
    customers = {}
    for vcode, cname, phone, state, city, area in CUSTOMERS:
        customers[(vcode, phone)] = upsert_customer(db, vendors[vcode].id, cname, phone)
        from app.modules.orders_models import CustomerAddress
        db.add(CustomerAddress(customer_id=customers[(vcode, phone)].id, state=state, city=city,
                               area=area, is_default=True))
    db.commit()

    # ---- WhatsApp conversations via the real ingestion pipeline -----------------
    ingest_message(db, from_phone="08012345001", wa_message_id="SEED-MSG-001",
                   text="Good morning! Do you have the black sneakers in stock?", msg_type="text")
    db.commit()
    ingest_message(db, from_phone="08023456001", wa_message_id="SEED-MSG-002",
                   text="Another order. Amina, 08098765432, Abuja. One blender. 45000.", msg_type="text")
    db.commit()
    ingest_message(db, from_phone="08012345001", wa_message_id="SEED-MSG-003",
                   text="Send hoodie to Abuja", msg_type="text")
    db.commit()
    ingest_message(db, from_phone="08099900011", wa_message_id="SEED-MSG-004",
                   text="hello, I want to join", msg_type="text")
    db.commit()

    # ---- orders (built through the same service functions as the app) ----------
    wh_default = wh1

    def make_order(vcode, cust_phone, sku, qty, status, unit_price=None, source="PORTAL", created_days_ago=3):
        v = vendors[vcode]
        p = products_by_sku[sku]
        cust = customers[(vcode, cust_phone)]
        price = unit_price if unit_price is not None else p.default_sell_price_kobo
        # reserve from the warehouse that actually holds this vendor's stock
        from app.modules.inventory_models import InventoryBalance as IB
        bal = db.query(IB).filter(IB.product_id == p.id).first()
        wh = db.get(Warehouse, bal.warehouse_id) if bal else wh_default
        o = Order(reference="PENDING", vendor_id=v.id, customer_id=cust.id, warehouse_id=wh.id,
                  status="CONFIRMED", payment_method="COD", source=source,
                  items_total_kobo=price * qty, cod_amount_kobo=price * qty,
                  created_at=now - timedelta(days=created_days_ago))
        # resolve address from the customers table
        from app.modules.orders_models import CustomerAddress
        addr = db.query(CustomerAddress).filter(CustomerAddress.customer_id == cust.id).first()
        if addr:
            o.delivery_state, o.delivery_city, o.delivery_area = addr.state, addr.city, addr.area
        db.add(o)
        db.flush()
        o.reference = next_ref(db, Order, "reference", "KW")
        db.add(OrderItem(order_id=o.id, product_id=p.id, variant_id=0, name_snapshot=p.name,
                         sku_snapshot=p.sku, qty=qty, unit_price_kobo=price,
                         line_total_kobo=price * qty, price_source="DEFAULT"))
        if status not in ("CANCELLED",):
            reserve_stock(db, o.id, p.id, 0, wh.id, qty, None)
        add_event(db, o, "CREATED", to_status="CONFIRMED", note=f"Seed order ({source})",
                  actor=None)
        o.created_at = now - timedelta(days=created_days_ago)
        return o, p, qty, price * qty

    # KW-1001: delivered, COD verified, settlement built
    o1, p1, q1, tot1 = make_order("VD-1001", "08012345678", "KFH-SNK-001", 2, "DELIVERED", created_days_ago=6)
    o1.status = "DELIVERED"
    consume_reservations(db, o1.id, None)
    apply_charge(db, vendor_id=o1.vendor_id, order_id=o1.id, charge_type="ORDER_PROCESSING", reason="Processing fee")
    apply_charge(db, vendor_id=o1.vendor_id, order_id=o1.id, charge_type="LOCAL_DELIVERY", reason="Delivery fee")
    from app.modules.delivery_models import Delivery
    d1 = Delivery(order_id=o1.id, mode="IN_HOUSE_RIDER", rider_id=r1.id, zone_id=zones["Lagos Mainland"].id,
                  fee_kobo=250000, status="DELIVERED", dispatch_at=now - timedelta(days=5),
                  delivered_at=now - timedelta(days=5), proof_ref="POD-001")
    db.add(d1)
    db.flush()
    o1.delivered_at = d1.delivered_at

    # KW-1002: in transit with rider
    o2, *_ = make_order("VD-1001", "08098765432", "KFH-KFT-005", 1, "IN_TRANSIT", created_days_ago=2)
    o2.status = "IN_TRANSIT"
    apply_charge(db, vendor_id=o2.vendor_id, order_id=o2.id, charge_type="ORDER_PROCESSING", reason="Processing fee")
    from app.modules.delivery_models import Delivery as D2
    db.add(D2(order_id=o2.id, mode="IN_HOUSE_RIDER", rider_id=r3.id, zone_id=zones["Abuja Metro"].id,
              fee_kobo=600000, status="IN_TRANSIT", dispatch_at=now - timedelta(days=1)))
    add_event(db, o2, "DISPATCH", to_status="DISPATCHED", note="Dispatched to Abuja")

    # KW-1003: ready for dispatch
    o3, *_ = make_order("VD-1002", "08044455566", "ZRG-EAR-002", 1, "READY_FOR_DISPATCH", created_days_ago=1)
    o3.status = "READY_FOR_DISPATCH"
    apply_charge(db, vendor_id=o3.vendor_id, order_id=o3.id, charge_type="ORDER_PROCESSING", reason="Processing fee")

    # KW-1004: awaiting customer confirmation
    o4, *_ = make_order("VD-1002", "08055566677", "ZRG-PWB-003", 2, "PENDING_CUSTOMER_CONFIRMATION", created_days_ago=1)
    o4.status = "PENDING_CUSTOMER_CONFIRMATION"
    from app.modules.orders_models import CustomerConfirmation
    db.add(CustomerConfirmation(order_id=o4.id, status="NOT_STARTED", attempts_count=0))

    # KW-1005: processing, customer confirmed
    o5, *_ = make_order("VD-1003", "08077788899", "AHE-CWK-003", 1, "PROCESSING", created_days_ago=2)
    o5.status = "PROCESSING"
    db.add(CustomerConfirmation(order_id=o5.id, status="CUSTOMER_CONFIRMED", attempts_count=1,
                                confirmed_at=now - timedelta(days=1)))

    # KW-1006: delivery failed
    o6, *_ = make_order("VD-1001", "08033344455", "KFH-BAG-006", 1, "DELIVERY_FAILED", created_days_ago=4)
    o6.status = "DELIVERY_FAILED"
    apply_charge(db, vendor_id=o6.vendor_id, order_id=o6.id, charge_type="ORDER_PROCESSING", reason="Processing fee")
    db.add(Delivery(order_id=o6.id, mode="IN_HOUSE_RIDER", rider_id=r1.id, fee_kobo=250000,
                    status="FAILED", failure_reason="Customer unreachable at address",
                    dispatch_at=now - timedelta(days=3)))
    add_event(db, o6, "DISPATCH", to_status="DISPATCHED", note="First attempt")
    add_event(db, o6, "STATUS_CHANGE", from_status="IN_TRANSIT", to_status="DELIVERY_FAILED",
              note="Customer unreachable at address")

    # KW-1007: cancelled (reservation released)
    o7, *_ = make_order("VD-1002", "08066677788", "ZRG-WTC-005", 1, "CANCELLED", created_days_ago=3)
    o7.status = "CANCELLED"
    o7.cancelled_at = now - timedelta(days=2)
    o7.cancel_reason = "Vendor requested cancellation - product no longer available"
    from app.modules.inventory import release_reservations
    release_reservations(db, o7.id, None)
    add_event(db, o7, "STATUS_CHANGE", from_status="CONFIRMED", to_status="CANCELLED",
              note=o7.cancel_reason)

    # KW-1008: return requested after delivery
    o8, *_ = make_order("VD-1003", "08088899900", "AHE-CUR-004", 1, "RETURN_REQUESTED", created_days_ago=8)
    o8.status = "RETURN_REQUESTED"
    o8.delivered_at = now - timedelta(days=5)
    consume_reservations(db, o8.id, None)
    apply_charge(db, vendor_id=o8.vendor_id, order_id=o8.id, charge_type="ORDER_PROCESSING", reason="Processing fee")
    db.commit()

    # ---- COD collections: one verified (drives ledger + settlement), one pending
    from app.modules.cod_models import CODCollection
    from app.modules.cod import verify_collection
    from app.modules.cod import CollectionIn, VerifyIn

    c1 = CODCollection(order_id=o1.id, delivery_id=d1.id, expected_kobo=o1.cod_amount_kobo,
                       collected_kobo=o1.cod_amount_kobo, method="CASH", rider_id=r1.id,
                       collected_at=now - timedelta(days=5), status="PENDING_VERIFICATION",
                       collected_by_user_id=rider_user.id)
    db.add(c1)
    db.flush()
    verify_collection(c1.id, VerifyIn(note="Verified against rider handover HDV-1000"), user=owner, db=db)

    c8 = CODCollection(order_id=o8.id, expected_kobo=o8.cod_amount_kobo, collected_kobo=o8.cod_amount_kobo,
                       method="BANK_TRANSFER", collected_at=now - timedelta(days=4),
                       status="PENDING_VERIFICATION")
    db.add(c8)

    # ---- cash handover ----------------------------------------------------------
    from app.modules.cod_models import CashHandover
    h = CashHandover(reference="PENDING", rider_id=r1.id, user_id=rider_user.id,
                     amount_expected_kobo=o1.cod_amount_kobo, status="CONFIRMED",
                     amount_counted_kobo=o1.cod_amount_kobo, handed_at=now - timedelta(days=5),
                     confirmed_at=now - timedelta(days=5), note="Confirmed at counter")
    db.add(h)
    db.flush()
    h.reference = next_ref(db, CashHandover, "reference", "HDV")
    c1.handover_id = h.id

    # ---- settlement for VD-1001 (built through the real function) ----------------
    from app.modules.settlements import build_settlement, BuildIn
    try:
        build_settlement(BuildIn(vendor_id=vendors["VD-1001"].id), user=owner, db=db)
    except Exception as e:
        print(f"[seed] settlement build skipped: {e}")

    # ---- expenses -----------------------------------------------------------------
    db.add(Expense(category="Fuel", description="Bike fuel weekly top-up", amount_kobo=4500000,
                   payment_method="CASH", payee="NNPC Station", status="PENDING_APPROVAL",
                   requested_by_user_id=users["ops@keyway.ng"].id))
    e2 = Expense(category="Packaging", description="Nylon bags and tape", amount_kobo=2800000,
                 payment_method="CASH", payee="Trade Fair Mart", status="PENDING_APPROVAL",
                 paid_from_account_id=accounts["CASH"].id,
                 requested_by_user_id=users["ops@keyway.ng"].id)
    db.add(e2)
    db.flush()
    # fund the cash account from the bank so cash never goes negative
    post_journal(db, memo="Cash withdrawal from bank for operations",
                 source_type="OPENING", source_id=None,
                 lines=[{"account_id": accounts["CASH"].id, "debit_kobo": 2_000_000 * 100},
                        {"account_id": accounts["BANK"].id, "credit_kobo": 2_000_000 * 100}],
                 posted_by=owner)
    from app.modules.ledger import approve_expense
    approve_expense(e2.id, user=owner, db=db)

    # ---- notifications & audit ------------------------------------------------------
    notify(db, event_type="WELCOME", title="Welcome to Keyway",
           body="Your workspace is seeded with demo data. Explore the WhatsApp inbox and simulator.",
           user_id=owner.id)
    db.commit()
    print(f"[seed] vendors={len(vendors)} products={len(products_by_sku)} users={len(users)}")
