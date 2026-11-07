#!/usr/bin/env python3
"""Static security scan: find FastAPI route handlers missing auth dependencies.

Flags any @router handler whose parameters lack one of the known auth
dependencies (get_current_user / require_staff / require_perm / get_vendor_user
/ any Depends(require_*)). Endpoints under /webhook and /health are exempt.
"""
import re
from pathlib import Path

APP = Path(__file__).resolve().parent.parent / "backend" / "app" / "modules"
AUTH_PATTERNS = ("get_current_user", "require_staff", "require_perm",
                 "get_vendor_user", "require_vendor", "Depends(require_")
EXEMPT = ("webhook", "health")

problems, checked = [], 0
for path in sorted(APP.glob("*.py")):
    src = path.read_text()
    for m in re.finditer(r'@router\.(get|post|put|patch|delete)\(([^)]*)\)\s*\ndef\s+(\w+)\s*\(([^)]*)\)', src, re.S):
        checked += 1
        deco_args, name, params = m.group(2), m.group(3), m.group(4)
        if any(x in deco_args or x in name for x in EXEMPT):
            continue
        if not any(p in params for p in AUTH_PATTERNS):
            line = src[:m.start()].count("\n") + 1
            problems.append(f"{path.name}:{line}  {name}({deco_args.strip()[:50]})")

print(f"checked {checked} route handlers")
if problems:
    print(f"\nNO-AUTH HANDLERS ({len(problems)}):")
    for p in problems:
        print(" ", p)
else:
    print("all handlers carry an auth dependency")
