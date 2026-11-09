"""A vendor that is not ACTIVE is paused everywhere: nothing new can be created for them.
Their products, stock and history stay exactly as they were, so reactivating restores everything."""
from fastapi import HTTPException

_WORDS = {"SUSPENDED": "suspended", "INACTIVE": "inactive", "PENDING": "waiting for approval"}


def vendor_pause_message(vendor, action: str) -> str:
    return (f"{vendor.name} is {_WORDS.get(vendor.status, 'not active')}. "
            f"Reactivate the vendor on their vendor page before you {action}.")


def require_active_vendor(db, vendor_id: int | None, action: str):
    from app.modules.vendors_models import Vendor
    if not vendor_id:
        return
    v = db.get(Vendor, vendor_id)
    if v and v.status != "ACTIVE":
        raise HTTPException(400, vendor_pause_message(v, action))
