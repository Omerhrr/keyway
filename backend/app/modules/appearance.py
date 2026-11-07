"""Business-editable look and feel: app theme, printed document layout, Excel export."""
import io
import re
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.core.db import get_db
from app.core.deps import get_current_user, require_perm
from app.core.audit import audit
from app.core.csvsafe import csv_safe
from app.modules.identity_models import User
from app.modules.appearance_models import AppSetting

router = APIRouter(prefix="/api", tags=["appearance"])

HEX = re.compile(r"^#[0-9a-fA-F]{6}$")

DEFAULT_THEME = {
    "brand_name": "Keyway",
    "tagline": "Logistics, delivered simply",
    "login_headline": "Your whole delivery business in one place.",
    "login_text": "Take orders from WhatsApp, keep each vendor's stock separate, confirm with customers, "
                  "send out deliveries, track cash collected and pay vendors with confidence.",
    "primary": "#059669",
    "radius": 0.55,
    "default_mode": "system",
}

DEFAULT_DOCS = {
    "template": "classic",
    "accent": "#059669",
    "company_name": "Keyway",
    "address": "",
    "phone": "",
    "email": "",
    "footer_text": "Thank you for doing business with us.",
    "paper": "A4",
    "orientation": "auto",
    "show_logo": True,
    "show_date": True,
    "show_prepared_by": True,
    "show_signatures": False,
    "show_row_numbers": True,
    "logo": "",
    "font": "sans",
    "header_style": "split",
    "table_style": "striped",
    "density": "comfortable",
    "watermark": "",
    "show_totals": True,
}

TEMPLATES = ("classic", "modern", "executive", "bold", "elegant", "ledger", "compact", "minimal", "receipt")
FONTS = ("sans", "serif", "mono", "rounded")
HEADERS = ("split", "centered", "banner", "stacked")
TABLE_STYLES = ("striped", "lines", "boxed", "clean")
DENSITIES = ("comfortable", "compact")
PAPERS = ("A4", "A5", "A3", "Letter", "Legal", "Receipt")
LOGO_MAX = 400_000  # characters of base64 text (about 300 KB of image)
LOGO_RE = re.compile(r"^data:image/(png|jpeg|webp);base64,[A-Za-z0-9+/=]+$")


def _load(db: Session, key: str, default: dict) -> dict:
    row = db.get(AppSetting, key)
    return {**default, **(row.value if row and isinstance(row.value, dict) else {})}


def _save(db: Session, key: str, value: dict, user: User) -> None:
    row = db.get(AppSetting, key)
    if row:
        row.value = value
        row.updated_by = user.full_name or user.email
    else:
        db.add(AppSetting(key=key, value=value, updated_by=user.full_name or user.email))


def _text(v, n: int, field: str) -> str:
    v = (v or "").strip() if isinstance(v, str) else ""
    if len(v) > n:
        raise HTTPException(400, f"{field} is too long (max {n} characters)")
    return v


class ThemeIn(BaseModel):
    brand_name: str | None = None
    tagline: str | None = None
    login_headline: str | None = None
    login_text: str | None = None
    primary: str | None = None
    radius: float | None = None
    default_mode: str | None = None


class DocsIn(BaseModel):
    template: str | None = None
    accent: str | None = None
    company_name: str | None = None
    address: str | None = None
    phone: str | None = None
    email: str | None = None
    footer_text: str | None = None
    paper: str | None = None
    orientation: str | None = None
    show_logo: bool | None = None
    show_date: bool | None = None
    show_prepared_by: bool | None = None
    show_signatures: bool | None = None
    show_row_numbers: bool | None = None
    show_totals: bool | None = None
    logo: str | None = None
    font: str | None = None
    header_style: str | None = None
    table_style: str | None = None
    density: str | None = None
    watermark: str | None = None


@router.get("/public/branding")
def public_branding(db: Session = Depends(get_db)):
    """Needed before sign-in so the login page wears the business's own theme."""
    return _load(db, "theme", DEFAULT_THEME)


@router.put("/settings/theme")
def save_theme(body: ThemeIn, user: User = Depends(require_perm("settings.manage")), db: Session = Depends(get_db)):
    cur = _load(db, "theme", DEFAULT_THEME)
    d = body.model_dump(exclude_unset=True)
    for f, n in (("brand_name", 40), ("tagline", 80), ("login_headline", 120), ("login_text", 400)):
        if f in d and d[f] is not None:
            cur[f] = _text(d[f], n, f)
    if cur["brand_name"] == "":
        raise HTTPException(400, "Business name cannot be empty")
    if d.get("primary") is not None:
        if not HEX.match(d["primary"]):
            raise HTTPException(400, "Colour must look like #059669")
        cur["primary"] = d["primary"].lower()
    if d.get("radius") is not None:
        if not (0 <= d["radius"] <= 1.25):
            raise HTTPException(400, "Corner roundness must be between 0 and 1.25")
        cur["radius"] = round(d["radius"], 2)
    if d.get("default_mode") is not None:
        if d["default_mode"] not in ("system", "light", "dark"):
            raise HTTPException(400, "Mode must be system, light or dark")
        cur["default_mode"] = d["default_mode"]
    _save(db, "theme", cur, user)
    audit(db, user, "update", "setting", "theme", "Changed the app theme")
    db.commit()
    return cur


@router.get("/settings/documents")
def get_docs(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _load(db, "documents", DEFAULT_DOCS)


@router.put("/settings/documents")
def save_docs(body: DocsIn, user: User = Depends(require_perm("settings.manage")), db: Session = Depends(get_db)):
    cur = _load(db, "documents", DEFAULT_DOCS)
    d = body.model_dump(exclude_unset=True)
    if d.get("template") is not None:
        if d["template"] not in TEMPLATES:
            raise HTTPException(400, f"Template must be one of {', '.join(TEMPLATES)}")
        cur["template"] = d["template"]
    if d.get("accent") is not None:
        if not HEX.match(d["accent"]):
            raise HTTPException(400, "Colour must look like #059669")
        cur["accent"] = d["accent"].lower()
    for f, n in (("company_name", 80), ("address", 200), ("phone", 40), ("email", 80), ("footer_text", 200)):
        if f in d and d[f] is not None:
            cur[f] = _text(d[f], n, f)
    if d.get("paper") is not None:
        if d["paper"] not in PAPERS:
            raise HTTPException(400, f"Paper must be one of {', '.join(PAPERS)}")
        cur["paper"] = d["paper"]
    for f, allowed in (("font", FONTS), ("header_style", HEADERS), ("table_style", TABLE_STYLES), ("density", DENSITIES)):
        if d.get(f) is not None:
            if d[f] not in allowed:
                raise HTTPException(400, f"{f.replace('_', ' ').title()} must be one of {', '.join(allowed)}")
            cur[f] = d[f]
    if "watermark" in d and d["watermark"] is not None:
        cur["watermark"] = _text(d["watermark"], 30, "Watermark")
    if "logo" in d and d["logo"] is not None:
        logo = d["logo"]
        if logo and (len(logo) > LOGO_MAX or not LOGO_RE.match(logo)):
            raise HTTPException(400, "Logo must be a PNG, JPG or WebP picture under 300 KB")
        cur["logo"] = logo
    if d.get("orientation") is not None:
        if d["orientation"] not in ("auto", "portrait", "landscape"):
            raise HTTPException(400, "Orientation must be auto, portrait or landscape")
        cur["orientation"] = d["orientation"]
    for f in ("show_logo", "show_date", "show_prepared_by", "show_signatures", "show_row_numbers", "show_totals"):
        if d.get(f) is not None:
            cur[f] = bool(d[f])
    _save(db, "documents", cur, user)
    audit(db, user, "update", "setting", "documents", "Changed the printed document layout")
    db.commit()
    return cur


# ---------------------------------------------------------------- Excel export

class XlsxIn(BaseModel):
    title: str = "Export"
    columns: list[str]
    rows: list[list]
    subtitle: str = ""


_MONEY = re.compile(r"^-?₦\s?-?[\d,]+(\.\d+)?$")
_THOUSANDS = re.compile(r"^-?\d{1,3}(,\d{3})+(\.\d+)?$")
_SMALL_INT = re.compile(r"^-?[1-9]\d{0,8}$|^0$")


def _cell(v):
    """Turn display text into real numbers where it is safely a number (money, counts)."""
    if v is None:
        return "", None
    if isinstance(v, bool):
        return ("Yes" if v else "No"), None
    if isinstance(v, (int, float)):
        return v, None
    s = str(v).strip()
    if _MONEY.match(s):
        return float(s.replace("₦", "").replace(",", "").replace(" ", "")), '"₦"#,##0.00'
    if _THOUSANDS.match(s):
        return float(s.replace(",", "")), "#,##0.##"
    if _SMALL_INT.match(s):
        return int(s), "0"
    return csv_safe(s), None  # never let text turn into a spreadsheet formula


@router.post("/export/xlsx")
def export_xlsx(body: XlsxIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.utils import get_column_letter
    if not body.columns or len(body.columns) > 60:
        raise HTTPException(400, "Between 1 and 60 columns are required")
    if len(body.rows) > 20000:
        raise HTTPException(400, "Too many rows for one export (max 20,000)")
    accent = _load(db, "documents", DEFAULT_DOCS)["accent"].lstrip("#").upper()
    wb = Workbook()
    ws = wb.active
    ws.title = (re.sub(r"[\\/*?:\[\]]", " ", body.title)[:31] or "Export")
    ws.append([csv_safe(body.title)])
    ws["A1"].font = Font(bold=True, size=14)
    ws.append([csv_safe(body.subtitle)] if body.subtitle else [])
    ws.append([])
    ws.append([csv_safe(str(c)) for c in body.columns])
    head_row = ws.max_row
    for c in ws[head_row]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor=accent)
        c.alignment = Alignment(vertical="center", wrap_text=True)
    widths = [len(str(c)) for c in body.columns]
    for r in body.rows:
        cells = []
        for i in range(len(body.columns)):
            val, fmt = _cell(r[i] if i < len(r) else None)
            cells.append((val, fmt))
            widths[i] = max(widths[i], min(len(str(val)), 60))
        ws.append([v for v, _ in cells])
        for i, (_, fmt) in enumerate(cells, start=1):
            if fmt:
                ws.cell(row=ws.max_row, column=i).number_format = fmt
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = max(10, min(w + 3, 50))
    ws.freeze_panes = ws.cell(row=head_row + 1, column=1)
    if body.rows:
        ws.auto_filter.ref = f"A{head_row}:{get_column_letter(len(body.columns))}{ws.max_row}"
    buf = io.BytesIO()
    wb.save(buf)
    return Response(buf.getvalue(),
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
