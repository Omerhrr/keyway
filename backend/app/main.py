"""Keyway API - modular monolith entrypoint."""
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.core.config import settings
from app.core.db import Base, engine, SessionLocal
from app.core import audit as _audit  # noqa ensures module import

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("keyway")



@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Create the schema, then bootstrap (production) or seed demo data (development).
    Base.metadata.create_all(bind=engine)
    from app.seed import seed_if_empty, seed_notification_rules
    db = SessionLocal()
    try:
        seed_if_empty(db)
        seed_notification_rules(db)  # idempotent: upgrades default rules on existing databases
    finally:
        db.close()
    log.info("Keyway API ready (env=%s)", settings.ENV)
    yield


app = FastAPI(title=settings.APP_NAME, version="0.1.0", lifespan=lifespan)

_origins = [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    # Auth is a Bearer header, not a cookie; credentialed CORS with "*" is invalid anyway.
    allow_credentials="*" not in _origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---- routers (modular monolith: each module owns its boundary) ----
from app.modules.identity import router as identity_router  # noqa: E402
from app.modules.vendors import router as vendors_router  # noqa: E402
from app.modules.catalog import router as catalog_router  # noqa: E402
from app.modules.inventory import router as inventory_router  # noqa: E402
from app.modules.orders import (router as orders_router,  # noqa: E402
                                customers_router, confirmations_router)
from app.modules.conversations import router as conversations_router  # noqa: E402
from app.modules.whatsapp import router as whatsapp_router  # noqa: E402
from app.modules.delivery import router as delivery_router  # noqa: E402
from app.modules.cod import router as cod_router  # noqa: E402
from app.modules.charges import router as charges_router  # noqa: E402
from app.modules.settlements import router as settlements_router  # noqa: E402
from app.modules.ledger import router as ledger_router  # noqa: E402
from app.modules.reports import router as reports_router  # noqa: E402
from app.modules.activity import router as activity_router  # noqa: E402
from app.modules.appearance import router as appearance_router  # noqa: E402
from app.modules.portal import router as portal_router  # noqa: E402

for r in (identity_router, vendors_router, catalog_router, inventory_router, orders_router,
          customers_router, confirmations_router, conversations_router, whatsapp_router,
          delivery_router, cod_router, charges_router, settlements_router, ledger_router,
          reports_router, activity_router, portal_router, appearance_router):
    app.include_router(r)


@app.get("/api/health")
def health():
    return {"status": "ok", "app": settings.APP_NAME, "env": settings.ENV}


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    # Full detail goes to the log; the response body stays generic in production
    # so internal paths/SQL/errors never leak to clients.
    log.exception("Unhandled error: %s", exc)
    detail = "Internal server error" if settings.ENV == "production" else f"Internal error: {exc}"
    return JSONResponse(status_code=500, content={"detail": detail})
