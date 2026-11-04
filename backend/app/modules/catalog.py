from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.core.db import get_db
from app.core.deps import require_staff, require_perm, get_vendor_user
from app.core.serialize import serialize, serialize_list
from app.core.audit import audit
from app.modules.identity_models import User
from app.modules.catalog_models import Product, ProductVariant, ProductAlias
from app.modules.inventory_models import InventoryBalance
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
def update_product(product_id: int, body: ProductIn, user: User = Depends(require_perm("catalog.manage")), db: Session = Depends(get_db)):
    p = db.get(Product, product_id)
    if not p:
        raise HTTPException(404, "Product not found")
    for k, v in body.model_dump(exclude_unset=True).items():
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
    v = ProductVariant(product_id=product_id, **body.model_dump())
    db.add(v)
    db.commit()
    return serialize(v)


@router.post("/products/{product_id}/aliases")
def add_alias(product_id: int, body: AliasIn, user: User = Depends(require_perm("catalog.manage")), db: Session = Depends(get_db)):
    p = db.get(Product, product_id)
    if not p:
        raise HTTPException(404, "Product not found")
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
