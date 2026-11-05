from collections import defaultdict, deque
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.core.db import get_db, utcnow
from app.core.security import verify_password, hash_password, create_access_token, create_refresh_token, decode_token
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
    if not user or not verify_password(body.password, user.password_hash):
        _register_failure(key)
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is suspended")
    _LOGIN_FAILS.pop(key, None)  # successful login clears the failure window
    user.last_login_at = utcnow()
    db.commit()
    return {
        "access_token": create_access_token(user.id),
        "refresh_token": create_refresh_token(user.id),
        "user": _user_payload(db, user),
    }


@router.post("/auth/refresh")
def refresh(body: RefreshIn, db: Session = Depends(get_db)):
    try:
        payload = decode_token(body.refresh_token, "refresh")
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    user = db.get(User, int(payload["sub"]))
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="Account inactive")
    return {
        "access_token": create_access_token(user.id),
        "refresh_token": create_refresh_token(user.id),
        "user": _user_payload(db, user),
    }


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
    if db.query(User).filter(User.email == body.email.strip().lower()).first():
        raise HTTPException(400, "Email already exists")
    u = User(email=body.email.strip().lower(), password_hash=hash_password(body.password),
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
    if "password" in data and data["password"]:
        u.password_hash = hash_password(data.pop("password"))
    else:
        data.pop("password", None)
    for k, v in data.items():
        setattr(u, k, v)
    db.commit()
    audit(db, user, "update", "user", u.id, f"Updated user {u.email}")
    db.commit()
    return serialize(u)


@router.get("/roles")
def list_roles(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
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
