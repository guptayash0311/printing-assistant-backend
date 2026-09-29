from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api.router import api_router
from app.core.config import load_settings
from app.core.database import configure_engine, get_engine, get_session
from app.core.errors import DomainError
from app.core.logging import RequestContextMiddleware, configure_logging
from app.core.rate_limit import RateLimiter
from app.models import Base
from app.services.accounts import ensure_super_admin
from app.services.storage import StorageService


def create_app() -> FastAPI:
    settings = load_settings()
    configure_logging()
    engine = configure_engine()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if settings.auto_create_schema:
            Base.metadata.create_all(engine)
        if settings.seed_super_admin:
            db = get_session()
            try:
                ensure_super_admin(db, settings)
                db.commit()
            finally:
                db.close()
        yield

    app = FastAPI(title="Print shop API", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.limiter = RateLimiter()
    app.state.storage = StorageService(settings.storage_root)
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(DomainError)
    async def domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {"code": exc.code, "message": exc.message, "details": exc.details},
                "request_id": getattr(request.state, "request_id", None),
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": "Request validation failed.",
                    "details": {"errors": jsonable_encoder(exc.errors())},
                },
                "request_id": getattr(request.state, "request_id", None),
            },
        )

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    @app.get("/health/live")
    def live() -> dict:
        return {"status": "ok"}

    @app.get("/health/ready")
    def ready() -> dict:
        with get_engine().connect() as connection:
            connection.execute(text("SELECT 1"))
        app.state.storage.root.mkdir(parents=True, exist_ok=True)
        return {"status": "ok"}

    app.include_router(api_router, prefix="/api/v1")
    return app


app = create_app()
