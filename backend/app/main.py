"""Keyway API - modular monolith entrypoint."""
import logging
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.core.config import settings
from app.core.db import Base, engine, SessionLocal
from app.core import audit as _audit  # noqa ensures module import

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("keyway")

app = FastAPI(title=settings.APP_NAME, version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.CORS_ORIGINS.split(",")],
    allow_credentials=True,
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
from app.modules.portal import router as portal_router  # noqa: E402

for r in (identity_router, vendors_router, catalog_router, inventory_router, orders_router,
          customers_router, confirmations_router, conversations_router, whatsapp_router,
          delivery_router, cod_router, charges_router, settlements_router, ledger_router,
          reports_router, activity_router, portal_router):
    app.include_router(r)


@app.get("/api/health")
def health():
    return {"status": "ok", "app": settings.APP_NAME, "env": settings.ENV}


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    log.exception("Unhandled error: %s", exc)
    return JSONResponse(status_code=500, content={"detail": f"Internal error: {exc}"})


@app.on_event("startup")
def startup():
    # SQLite dev database: create schema, then seed demo data on first boot.
    Base.metadata.create_all(bind=engine)
    from app.seed import seed_if_empty
    db = SessionLocal()
    try:
        seed_if_empty(db)
    finally:
        db.close()
    log.info("Keyway API ready")
