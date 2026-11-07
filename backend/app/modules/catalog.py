import csv
import io
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Response
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.core.db import get_db
from app.core.deps import require_staff, require_perm, get_vendor_user
from app.core.serialize import serialize, serialize_list
from app.core.audit import audit
from app.core.csvsafe import csv_safe
from app.modules.identity_models import User
from app.modules.catalog_models import Product, ProductVariant, ProductAlias
from app.modules.inventory_models import InventoryBalance, InventoryMovement
from sqlalchemy import func

router = APIRouter(prefix="/api/catalog", tags=["catalog"])


class ProductIn(BaseModel):
    vendor_id: int
    sku: str
    name: str
    description: str = ""
    category: str = ""
    unit: str = "pcs"
    default_sell_price_kobo: int = 0
    reorder_level: int = 5
    status: str = "ACTIVE"


class ProductPatch(BaseModel):
    sku: str | None = None
    name: str | None = None
    description: str | None = None
    category: str | None = None
    unit: str | None = None
    default_sell_price_kobo: int | None = None
    reorder_level: int | None = None
    status: str | None = None


PRODUCT_STATUSES = ("ACTIVE", "INACTIVE", "ARCHIVED")


def _check_product_fields(d: dict):
    if d.get("default_sell_price_kobo") is not None and d["default_sell_price_kobo"] < 0:
        raise HTTPException(400, "Price cannot be negative")
    if d.get("reorder_level") is not None and d["reorder_level"] < 0:
        raise HTTPException(400, "Reorder level cannot be negative")
    if d.get("status") is not None and d["status"] not in PRODUCT_STATUSES:
        raise HTTPException(400, f"status must be one of {', '.join(PRODUCT_STATUSES)}")
    for f in ("sku", "name"):
        if f in d and not (d[f] or "").strip():
            raise HTTPException(400, f"{f} cannot be empty")


class VariantIn(BaseModel):
    sku: str
    name: str = ""
    barcode: str = ""
    attributes: dict = {}
    sell_price_kobo: int | None = None


class AliasIn(BaseModel):
    alias: str
    variant_id: int | None = None
    weight: int = 90


def _with_stock(db: Session, products: list[Product], variant_breakdown=False) -> list[dict]:
    ids = [p.id for p in products]
    agg = {}
    variants = {}
    if ids:
        q = db.query(InventoryBalance).filter(InventoryBalance.product_id.in_(ids))
        for b in q.all():
            t = agg.setdefault(b.product_id, {"physical": 0, "reserved": 0, "damaged": 0})
            t["physical"] += b.qty_physical
            t["reserved"] += b.qty_reserved
            t["damaged"] += b.qty_damaged
            if variant_breakdown:
                key = (b.product_id, b.variant_id)
                vt = variants.setdefault(key, 0)
                vt += b.qty_physical - b.qty_reserved
    out = []
    for p in products:
        a = agg.get(p.id, {"physical": 0, "reserved": 0, "damaged": 0})
        vs = db.query(ProductVariant).filter(ProductVariant.product_id == p.id).all() if variant_breakdown else []
        out.append(serialize(
            p,
            qty_physical=a["physical"], qty_reserved=a["reserved"], qty_damaged=a["damaged"],
            qty_available=a["physical"] - a["reserved"],
            low_stock=(a["physical"] - a["reserved"]) <= p.reorder_level,
            variants=serialize_list(vs) if variant_breakdown else [],
        ))
    return out


@router.get("/products")
def list_products(user: User = Depends(require_staff), db: Session = Depends(get_db),
                  vendor_id: int = 0, q: str = "", low_stock: bool = False, breakdown: bool = False):
    query = db.query(Product)
    if vendor_id:
        query = query.filter(Product.vendor_id == vendor_id)
    if q:
        like = f"%{q}%"
        query = query.filter((Product.name.ilike(like)) | (Product.sku.ilike(like)) | (Product.category.ilike(like)))
    products = query.order_by(Product.vendor_id, Product.name).all()
    rows = _with_stock(db, products, variant_breakdown=breakdown)
    if low_stock:
        rows = [r for r in rows if r["low_stock"]]
    return rows


@router.post("/products")
def create_product(body: ProductIn, user: User = Depends(require_perm("catalog.manage")), db: Session = Depends(get_db)):
    from app.modules.vendors_models import Vendor
    if not db.get(Vendor, body.vendor_id):
        raise HTTPException(404, "Vendor not found")
    _check_product_fields(body.model_dump())
    dup = db.query(Product).filter(Product.vendor_id == body.vendor_id, Product.sku == body.sku).first()
    if dup:
        raise HTTPException(400, "SKU already exists for this vendor")
    p = Product(**body.model_dump())
    db.add(p)
    db.commit()
    audit(db, user, "create", "product", p.id, f"Created product {p.name}")
    db.commit()
    return serialize(p)


@router.get("/products/{product_id}")
def get_product(product_id: int, user: User = Depends(require_staff), db: Session = Depends(get_db)):
    p = db.get(Product, product_id)
    if not p:
        raise HTTPException(404, "Product not found")
    variants = db.query(ProductVariant).filter(ProductVariant.product_id == product_id).all()
    aliases = db.query(ProductAlias).filter(ProductAlias.product_id == product_id).all()
    balances = db.query(InventoryBalance).filter(InventoryBalance.product_id == product_id).all()
    return serialize(p, variants=serialize_list(variants), aliases=serialize_list(aliases),
                     balances=serialize_list(balances))


@router.patch("/products/{product_id}")
def update_product(product_id: int, body: ProductPatch, user: User = Depends(require_perm("catalog.manage")), db: Session = Depends(get_db)):
    p = db.get(Product, product_id)
    if not p:
        raise HTTPException(404, "Product not found")
    data = {k: v for k, v in body.model_dump(exclude_unset=True).items() if v is not None}
    _check_product_fields(data)
    if "sku" in data and data["sku"] != p.sku:
        if db.query(Product).filter(Product.vendor_id == p.vendor_id, Product.sku == data["sku"],
                                    Product.id != p.id).first():
            raise HTTPException(400, "SKU already exists for this vendor")
    for k, v in data.items():
        setattr(p, k, v)
    db.commit()
    audit(db, user, "update", "product", p.id, f"Updated product {p.name}")
    db.commit()
    return serialize(p)


@router.post("/products/{product_id}/variants")
def add_variant(product_id: int, body: VariantIn, user: User = Depends(require_perm("catalog.manage")), db: Session = Depends(get_db)):
    p = db.get(Product, product_id)
    if not p:
        raise HTTPException(404, "Product not found")
    if not body.sku.strip():
        raise HTTPException(400, "Variant SKU is required")
    if body.sell_price_kobo is not None and body.sell_price_kobo < 0:
        raise HTTPException(400, "Price cannot be negative")
    if db.query(ProductVariant).filter(ProductVariant.product_id == product_id,
                                       ProductVariant.sku == body.sku).first():
        raise HTTPException(400, "A variant with this SKU already exists for the product")
    v = ProductVariant(product_id=product_id, **body.model_dump())
    db.add(v)
    db.commit()
    return serialize(v)


@router.post("/products/{product_id}/aliases")
def add_alias(product_id: int, body: AliasIn, user: User = Depends(require_perm("catalog.manage")), db: Session = Depends(get_db)):
    p = db.get(Product, product_id)
    if not p:
        raise HTTPException(404, "Product not found")
    if not body.alias.strip():
        raise HTTPException(400, "Alias is required")
    if body.variant_id:
        pv = db.get(ProductVariant, body.variant_id)
        if not pv or pv.product_id != p.id:
            raise HTTPException(400, "Variant does not belong to this product")
    a = ProductAlias(vendor_id=p.vendor_id, product_id=product_id, **body.model_dump())
    db.add(a)
    db.commit()
    return serialize(a)


@router.delete("/aliases/{alias_id}")
def delete_alias(alias_id: int, user: User = Depends(require_perm("catalog.manage")), db: Session = Depends(get_db)):
    a = db.get(ProductAlias, alias_id)
    if not a:
        raise HTTPException(404, "Alias not found")
    db.delete(a)
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Phase 6D: catalog import (CSV / XLSX) and export
# ---------------------------------------------------------------------------

IMPORT_TEMPLATE = [
    ["sku", "name", "category", "aliases", "sell_price", "opening_stock", "reorder_level"],
    ["ANK-BLU-01", "Ankara Gown - Blue", "Gowns", "blue gown|ankara blue", "12500", "10", "5"],
]


def _parse_upload(content: bytes, filename: str) -> list[dict]:
    """Parse CSV or XLSX into a list of row dicts with normalized headers."""
    name = (filename or "").lower()
    rows: list[list] = []
    if name.endswith((".xlsx", ".xlsm")):
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        ws = wb.active
        rows = [[("" if c is None else c) for c in row] for row in ws.iter_rows(values_only=True)]
        wb.close()
    else:
        text = content.decode("utf-8-sig", errors="replace")
        rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        return []
    headers = [str(h).strip().lower().replace(" ", "_") for h in rows[0]]
    out = []
    for r in rows[1:]:
        if not any(str(c).strip() for c in r):
            continue
        row = {}
        for i, h in enumerate(headers):
            if h and i < len(r):
                row[h] = r[i]
        out.append(row)
    return out


def _to_int(v, default=0) -> int:
    try:
        return int(round(float(str(v).replace(",", "").replace("\u20a6", "").strip() or default)))
    except (TypeError, ValueError):
        return default


@router.post("/import")
async def import_catalog(vendor_id: int, file: UploadFile = File(...),
                         user: User = Depends(require_perm("catalog.manage")),
                         db: Session = Depends(get_db)):
    """Bulk-import products from CSV/XLSX.

    Columns: sku*, name*, category, aliases (| separated), sell_price (naira),
    opening_stock, reorder_level. Existing SKUs are updated, new SKUs created;
    aliases are added (never duplicated); opening stock seeds inventory.
    """
    from app.modules.vendors_models import Vendor
    from app.modules.inventory_models import Warehouse
    vendor = db.get(Vendor, vendor_id)
    if not vendor:
        raise HTTPException(404, "Vendor not found")
    content = await file.read()
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(400, "File too large (max 5MB)")
    try:
        rows = _parse_upload(content, file.filename or "")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(400, f"Could not parse file: {e}")
    if not rows:
        raise HTTPException(400, "No data rows found")

    warehouse = (db.query(Warehouse).filter(Warehouse.is_default.is_(True), Warehouse.is_active.is_(True)).first()
                 or db.query(Warehouse).filter(Warehouse.is_active.is_(True)).order_by(Warehouse.id).first())
    created = updated = alias_count = stock_rows = 0
    errors: list[str] = []
    for i, row in enumerate(rows, start=2):  # start=2: row 1 is the header
        sku = str(row.get("sku") or row.get("sku_*") or "").strip()
        name = str(row.get("name") or row.get("product") or "").strip()
        if not sku and not name:
            continue
        if not sku:
            errors.append(f"Row {i}: missing sku - skipped")
            continue
        if not name:
            errors.append(f"Row {i}: missing name - skipped")
            continue
        raw_sell = row.get("sell_price") or row.get("price") or row.get("default_sell_price")
        try:
            sell = max(0, int(round(float(str(raw_sell).replace(",", "").replace("\u20a6", "").strip() or 0) * 100)))
        except (TypeError, ValueError):
            errors.append(f"Row {i}: unreadable price '{raw_sell}' - price left unchanged")
            sell = 0
        has_reorder = str(row.get("reorder_level", "")).strip() != ""
        reorder = max(0, _to_int(row.get("reorder_level"), 5))
        opening = max(0, _to_int(row.get("opening_stock") or row.get("qty") or row.get("stock"), 0))
        category = str(row.get("category") or "").strip()
        p = db.query(Product).filter(Product.vendor_id == vendor_id, Product.sku == sku).first()
        if p:
            p.name, p.category = name, category or p.category
            p.default_sell_price_kobo = sell or p.default_sell_price_kobo
            if has_reorder:  # a missing column must not reset a tuned reorder level
                p.reorder_level = reorder
            updated += 1
        else:
            p = Product(vendor_id=vendor_id, sku=sku, name=name, category=category,
                        default_sell_price_kobo=sell, reorder_level=reorder, status="ACTIVE")
            db.add(p)
            db.flush()
            created += 1
        # aliases: pipe-separated, attached to the product for fuzzy matching
        raw_aliases = str(row.get("aliases") or row.get("alias") or "")
        existing = {a.alias.lower() for a in db.query(ProductAlias).filter(
            ProductAlias.product_id == p.id).all()}
        for al in [a.strip() for a in raw_aliases.replace(";", "|").split("|") if a.strip()]:
            if al.lower() not in existing and al.lower() != name.lower():
                db.add(ProductAlias(vendor_id=vendor_id, product_id=p.id, alias=al, weight=90))
                existing.add(al.lower())
                alias_count += 1
        # opening stock (first warehouse, unvariant stock row)
        if opening > 0 and warehouse:
            bal = (db.query(InventoryBalance)
                   .filter(InventoryBalance.product_id == p.id, InventoryBalance.variant_id == 0,
                           InventoryBalance.warehouse_id == warehouse.id).first())
            if bal:
                # Existing stock is never overwritten by a re-import (use Adjust / Receipts for that).
                errors.append(f"Row {i}: {sku} already has stock records - opening_stock ignored")
            else:
                db.add(InventoryBalance(product_id=p.id, variant_id=0, warehouse_id=warehouse.id,
                                        location_id=0, qty_physical=opening))
                db.add(InventoryMovement(product_id=p.id, variant_id=0, warehouse_id=warehouse.id,
                                         movement_type="RECEIVE", qty=opening,
                                         reason="Opening stock from catalog import",
                                         ref_type="catalog_import", ref_id=str(vendor_id),
                                         actor_user_id=user.id))
                stock_rows += 1
    db.commit()
    audit(db, user, "import", "catalog", vendor_id,
          f"Catalog import for {vendor.name}: {created} created, {updated} updated, "
          f"{alias_count} aliases, {errors.__len__()} errors")
    db.commit()
    return {"created": created, "updated": updated, "aliases_added": alias_count,
            "stock_rows": stock_rows, "errors": errors[:20]}


@router.get("/export")
def export_catalog(vendor_id: int = 0, user: User = Depends(require_staff),
                   db: Session = Depends(get_db)):
    """Export the catalog (optionally one vendor) as CSV."""
    from urllib.parse import quote
    import io as _io
    q = db.query(Product)
    if vendor_id:
        q = q.filter(Product.vendor_id == vendor_id)
    buf = _io.StringIO()
    w = csv.writer(buf)
    w.writerow(["sku", "name", "category", "aliases", "sell_price", "reorder_level", "status"])
    for p in q.order_by(Product.vendor_id, Product.name).all():
        aliases = "|".join(a.alias for a in db.query(ProductAlias).filter(ProductAlias.product_id == p.id).all())
        w.writerow([csv_safe(p.sku), csv_safe(p.name), csv_safe(p.category), csv_safe(aliases),
                    (p.default_sell_price_kobo or 0) / 100, p.reorder_level, p.status])
    buf.seek(0)
    return Response(buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": f"attachment; filename={quote('keyway-catalog.csv')}"})
