from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .api import router
from .config import get_settings
from .db import SessionLocal, init_db

STATIC = Path(__file__).resolve().parent.parent / "static"
log = logging.getLogger("asesor")


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    s = get_settings()
    if s.seed_demo:
        from .seed import seed

        with SessionLocal() as db:
            seed(db)
    if s.environment == "production" and s.secret_key and len(s.secret_key) < 32:
        log.warning("SECRET_KEY es demasiado corta para producción")
    yield


app = FastAPI(title="Asesor Pedagógico Inteligente", version="1.0.0", lifespan=lifespan,
              docs_url="/api/docs", openapi_url="/api/openapi.json")
app.include_router(router)


@app.middleware("http")
async def cabeceras_seguridad(request: Request, call_next):
    resp = await call_next(request)
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "same-origin"
    if not request.url.path.startswith("/api/docs"):
        resp.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; script-src 'self'; connect-src 'self'; frame-ancestors 'none'"
        )
    return resp


@app.exception_handler(Exception)
async def error_no_controlado(request: Request, exc: Exception):  # pragma: no cover
    log.exception("Error no controlado en %s", request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Error interno. Consulte la auditoría o los logs del servidor."})


app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(STATIC / "index.html")
