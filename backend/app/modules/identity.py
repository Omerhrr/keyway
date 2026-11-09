from collections import defaultdict, deque
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.core.db import get_db, utcnow
from app.core.security import (verify_password, hash_password, create_access_token,
                               create_refresh_token, decode_token, pwd_fingerprint)
from app.core.deps import get_current_user, require_staff, require_perm, get_user_permissions
from app.core.serialize import serialize, serialize_list
from app.core.audit import audit
from app.modules.identity_models import User, Role, Permission, RolePermission

router = APIRouter(prefix="/api", tags=["identity"])

# ---- lightweight login brute-force guard (per API process) -----------------
# Tracks failed attempts per (client IP, email). At MAX_LOGIN_FAILS within
# LOCK_WINDOW seconds the pair is locked out until the window rolls off.
# Deliberately in-memory: good enough for a single-node deployment; swap for
# a shared store if the API ever runs multi-process.
_LOGIN_FAILS: dict[str, deque[float]] = defaultdict(deque)
_MAX_LOGIN_FAILS = 8
_LOCK_WINDOW = 900.0  # 15 minutes


def _throttle_key(request: Request, email: str) -> str:
    ip = request.client.host if request.client else "unknown"
    return f"{ip}:{(email or '').strip().lower()[:120]}"


def _prune(dq: deque[float]) -> None:
    now = time.monotonic()
    while dq and now - dq[0] > _LOCK_WINDOW:
        dq.popleft()


def _assert_not_locked(key: str) -> None:
    dq = _LOGIN_FAILS.get(key)
    if dq is not None:
        _prune(dq)
        if len(dq) >= _MAX_LOGIN_FAILS:
            raise HTTPException(status_code=429,
                                detail="Too many failed login attempts - try again in 15 minutes")


def _register_failure(key: str) -> None:
    dq = _LOGIN_FAILS[key]
    _prune(dq)
    dq.append(time.monotonic())


class LoginIn(BaseModel):
    email: str
    password: str


class RefreshIn(BaseModel):
    refresh_token: str


class UserCreate(BaseModel):
    email: str
    password: str
    full_name: str
    phone: str = ""
    role_id: int | None = None
    department: str = ""
    job_title: str = ""
    warehouse_id: int | None = None
    is_vendor: bool = False
    vendor_id: int | None = None


class UserUpdate(BaseModel):
    full_name: str | None = None
    phone: str | None = None
    role_id: int | None = None
    department: str | None = None
    job_title: str | None = None
    warehouse_id: int | None = None
    is_active: bool | None = None
    is_vendor: bool | None = None
    vendor_id: int | None = None
    password: str | None = None


_DUMMY_HASH = hash_password("keyway-timing-equaliser")
MIN_PASSWORD_LEN = 8


def _tokens(user: User) -> dict:
    """Token pair bound to the user's current password (changing it revokes them)."""
    extra = {"pv": pwd_fingerprint(user.password_hash)}
    return {"access_token": create_access_token(user.id, extra),
            "refresh_token": create_refresh_token(user.id, extra)}


def _clean_email(email: str) -> str:
    e = (email or "").strip().lower()
    if "@" not in e or e.startswith("@") or e.endswith("@") or " " in e:
        raise HTTPException(400, "A valid email address is required")
    return e


def _check_password(pw: str) -> None:
    if len(pw or "") < MIN_PASSWORD_LEN:
        raise HTTPException(400, f"Password must be at least {MIN_PASSWORD_LEN} characters")


def _user_payload(db: Session, user: User) -> dict:
    role = db.get(Role, user.role_id) if user.role_id else None
    perms = sorted(get_user_permissions(db, user))
    return serialize(
        user, fields=["id", "email", "full_name", "phone", "role_id", "department", "job_title",
                      "warehouse_id", "is_active", "is_superuser", "is_vendor", "vendor_id", "last_login_at"],
        role_name=role.name if role else None,
        permissions=perms if not user.is_superuser else ["*"],
    )


@router.post("/auth/login")
def login(body: LoginIn, request: Request, db: Session = Depends(get_db)):
    key = _throttle_key(request, body.email)
    _assert_not_locked(key)
    user = db.query(User).filter(User.email == body.email.strip().lower()).first()
    if not user:
        verify_password(body.password, _DUMMY_HASH)  # equalise timing: no user enumeration
    if not user or not verify_password(body.password, user.password_hash):
        _register_failure(key)
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is suspended")
    if user.is_vendor and user.vendor_id:
        from app.modules.vendors_models import Vendor
        _v = db.get(Vendor, user.vendor_id)
        if _v and _v.status != "ACTIVE":
            raise HTTPException(status_code=403, detail="This vendor account is paused. Please contact the company.")
    _LOGIN_FAILS.pop(key, None)  # successful login clears the failure window
    user.last_login_at = utcnow()
    db.commit()
    return {**_tokens(user), "user": _user_payload(db, user)}


@router.post("/auth/refresh")
def refresh(body: RefreshIn, db: Session = Depends(get_db)):
    try:
        payload = decode_token(body.refresh_token, "refresh")
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    user = db.get(User, int(payload["sub"]))
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="Account inactive")
    if payload.get("pv") != pwd_fingerprint(user.password_hash):
        raise HTTPException(status_code=401, detail="Session expired - please sign in again")
    return {**_tokens(user), "user": _user_payload(db, user)}


@router.get("/auth/me")
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _user_payload(db, user)


@router.get("/users")
def list_users(user: User = Depends(require_staff), db: Session = Depends(get_db)):
    q = db.query(User).order_by(User.id)
    rows = q.all()
    out = []
    for u in rows:
        role = db.get(Role, u.role_id) if u.role_id else None
        out.append(serialize(u, fields=["id", "email", "full_name", "phone", "role_id", "department",
                                        "job_title", "warehouse_id", "is_active", "is_superuser",
                                        "is_vendor", "vendor_id", "last_login_at"],
                             role_name=role.name if role else None))
    return out


@router.post("/users")
def create_user(body: UserCreate, user: User = Depends(require_perm("settings.manage")), db: Session = Depends(get_db)):
    email = _clean_email(body.email)
    _check_password(body.password)
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(400, "Email already exists")
    if body.role_id is not None and not db.get(Role, body.role_id):
        raise HTTPException(400, "Unknown role")
    if body.is_vendor:
        from app.modules.vendors_models import Vendor
        if not body.vendor_id or not db.get(Vendor, body.vendor_id):
            raise HTTPException(400, "A vendor-portal user needs a valid vendor_id")
    if body.is_vendor and body.role_id is None:  # portal accounts always get the Vendor role
        _vr = db.query(Role).filter(Role.name == "Vendor").first()
        body.role_id = _vr.id if _vr else None
    u = User(email=email, password_hash=hash_password(body.password),
             full_name=body.full_name, phone=body.phone, role_id=body.role_id,
             department=body.department, job_title=body.job_title, warehouse_id=body.warehouse_id,
             is_vendor=body.is_vendor, vendor_id=body.vendor_id if body.is_vendor else None)
    db.add(u)
    db.commit()
    audit(db, user, "create", "user", u.id, f"Created user {u.email}")
    db.commit()
    return serialize(u)


@router.patch("/users/{user_id}")
def update_user(user_id: int, body: UserUpdate, user: User = Depends(require_perm("settings.manage")), db: Session = Depends(get_db)):
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(404, "User not found")
    data = body.model_dump(exclude_unset=True)
    if u.id == user.id and data.get("is_active") is False:
        raise HTTPException(400, "You cannot deactivate your own account")
    if data.get("role_id") is not None and not db.get(Role, data["role_id"]):
        raise HTTPException(400, "Unknown role")
    if "password" in data and data["password"]:
        _check_password(data["password"])
        u.password_hash = hash_password(data.pop("password"))  # also revokes existing sessions
    else:
        data.pop("password", None)
    for k, v in data.items():
        setattr(u, k, v)
    if not u.is_vendor:
        u.vendor_id = None
    elif not u.vendor_id:
        raise HTTPException(400, "A vendor-portal user needs a vendor_id")
    db.commit()
    audit(db, user, "update", "user", u.id, f"Updated user {u.email}")
    db.commit()
    return serialize(u)


@router.get("/roles")
def list_roles(user: User = Depends(require_staff), db: Session = Depends(get_db)):
    roles = db.query(Role).order_by(Role.id).all()
    perms = db.query(Permission).order_by(Permission.module, Permission.codename).all()
    matrix = db.query(RolePermission).all()
    perm_by_id = {p.id: p.codename for p in perms}
    role_perms: dict[int, list[str]] = {}
    for m in matrix:
        role_perms.setdefault(m.role_id, []).append(perm_by_id.get(m.permission_id, ""))
    return {
        "roles": [serialize(ro, fields=["id", "name", "description", "is_system"],
                            permissions=sorted([c for c in role_perms.get(ro.id, []) if c]))
                  for ro in roles],
        "permission_catalog": serialize_list(perms),
        "role_permissions": {str(r.id): sorted([c for c in role_perms.get(r.id, []) if c]) for r in roles},
    }


# ---------------------------------------------------------------- roles you can create and change

PROTECTED_ROLES = ("Business Owner", "Administrator", "Vendor")


class RoleIn(BaseModel):
    name: str | None = None
    description: str | None = None
    permissions: list[str] | None = None


def _set_role_permissions(db: Session, role: Role, codes: list[str]):
    known = {p.codename: p.id for p in db.query(Permission).all()}
    bad = [c for c in codes if c not in known]
    if bad:
        raise HTTPException(400, f"Unknown permission: {bad[0]}")
    db.query(RolePermission).filter(RolePermission.role_id == role.id).delete()
    for c in sorted(set(codes)):
        db.add(RolePermission(role_id=role.id, permission_id=known[c]))


@router.post("/roles", status_code=201)
def create_role(body: RoleIn, user: User = Depends(require_perm("settings.manage")), db: Session = Depends(get_db)):
    name = (body.name or "").strip()
    if not name or len(name) > 80:
        raise HTTPException(400, "Give the role a name (up to 80 characters)")
    if db.query(Role).filter(func.lower(Role.name) == name.lower()).first():
        raise HTTPException(400, "A role with this name already exists")
    r = Role(name=name, description=(body.description or "").strip()[:255], is_system=False)
    db.add(r)
    db.flush()
    _set_role_permissions(db, r, body.permissions or [])
    audit(db, user, "create", "role", r.id, f"Created role {r.name}")
    db.commit()
    return {"id": r.id}


@router.patch("/roles/{role_id}")
def update_role(role_id: int, body: RoleIn, user: User = Depends(require_perm("settings.manage")),
                db: Session = Depends(get_db)):
    r = db.get(Role, role_id)
    if not r:
        raise HTTPException(404, "Role not found")
    if r.name in PROTECTED_ROLES:
        raise HTTPException(400, f"The {r.name} role is fixed and cannot be changed")
    if body.name is not None:
        name = body.name.strip()
        if not name or len(name) > 80:
            raise HTTPException(400, "Give the role a name (up to 80 characters)")
        clash = db.query(Role).filter(func.lower(Role.name) == name.lower(), Role.id != r.id).first()
        if clash:
            raise HTTPException(400, "A role with this name already exists")
        r.name = name
    if body.description is not None:
        r.description = body.description.strip()[:255]
    if body.permissions is not None:
        if user.role_id == r.id and not user.is_superuser and "settings.manage" not in body.permissions:
            raise HTTPException(400, "You cannot remove settings access from your own role")
        _set_role_permissions(db, r, body.permissions)
    audit(db, user, "update", "role", r.id, f"Updated role {r.name}")
    db.commit()
    return {"id": r.id}


@router.delete("/roles/{role_id}")
def delete_role(role_id: int, user: User = Depends(require_perm("settings.manage")), db: Session = Depends(get_db)):
    r = db.get(Role, role_id)
    if not r:
        raise HTTPException(404, "Role not found")
    if r.name in PROTECTED_ROLES:
        raise HTTPException(400, f"The {r.name} role is fixed and cannot be deleted")
    n = db.query(User).filter(User.role_id == r.id).count()
    if n:
        raise HTTPException(400, f"{n} staff member(s) still have this role. Move them to another role first.")
    db.query(RolePermission).filter(RolePermission.role_id == r.id).delete()
    db.delete(r)
    audit(db, user, "delete", "role", role_id, f"Deleted role {r.name}")
    db.commit()
    return {"ok": True}
