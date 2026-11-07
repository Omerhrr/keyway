from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from app.core.db import get_db
from app.core.security import decode_token, pwd_fingerprint
from app.modules.identity_models import User, RolePermission

bearer = HTTPBearer(auto_error=False)


def get_current_user(creds: HTTPAuthorizationCredentials | None = Depends(bearer),
                     db: Session = Depends(get_db)) -> User:
    if creds is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = decode_token(creds.credentials, "access")
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    user = db.get(User, int(payload["sub"]))
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="Account inactive or not found")
    if payload.get("pv") != pwd_fingerprint(user.password_hash):
        raise HTTPException(status_code=401, detail="Session expired - please sign in again")
    return user


def get_user_permissions(db: Session, user: User) -> set[str]:
    if not user.role_id:
        return set()
    rows = (db.query(RolePermission)
            .filter(RolePermission.role_id == user.role_id).all())
    from app.modules.identity_models import Permission
    codes = []
    for rp in rows:
        p = db.get(Permission, rp.permission_id)
        if p:
            codes.append(p.codename)
    return set(codes)


def require_perm(code: str):
    """Dependency factory: user must hold the given permission (or be superuser)."""
    def _dep(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> User:
        if user.is_vendor:
            raise HTTPException(status_code=403, detail="Staff account required")
        if user.is_superuser:
            return user
        if code in get_user_permissions(db, user):
            return user
        raise HTTPException(status_code=403, detail=f"Missing permission: {code}")
    return _dep


def require_any_perm(*codes: str):
    """Dependency factory: user must hold at least one of the given permissions
    (or be superuser). Vendor-portal users are never staff."""
    def _dep(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> User:
        if user.is_vendor:
            raise HTTPException(status_code=403, detail="Staff account required")
        if user.is_superuser:
            return user
        held = get_user_permissions(db, user)
        if any(c in held for c in codes):
            return user
        raise HTTPException(status_code=403, detail=f"Missing permission: one of {', '.join(codes)}")
    return _dep


def require_staff(user: User = Depends(get_current_user)) -> User:
    """Staff-only endpoints (vendor portal users excluded)."""
    if user.is_vendor:
        raise HTTPException(status_code=403, detail="Staff account required")
    return user


def get_vendor_user(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> User:
    """Vendor portal user; guarantees vendor-level data isolation."""
    if not user.is_vendor or not user.vendor_id:
        raise HTTPException(status_code=403, detail="Vendor account required")
    return user
