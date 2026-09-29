from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.errors import DomainError
from app.models import User
from app.schemas.requests import LoginIn
from app.schemas.serialize import user_dict
from app.security.passwords import create_jwt, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login")
def login(body: LoginIn, request: Request, db: Session = Depends(get_db)) -> dict:
    settings = request.app.state.settings
    if settings.rate_limit_enabled:
        ip = request.client.host if request.client else "unknown"
        request.app.state.limiter.check(
            f"login:{ip}:{body.email.lower()}",
            settings.login_rate_limit,
            settings.rate_limit_window_seconds,
        )
    user = db.scalar(select(User).where(User.email == body.email.lower().strip()))
    if user is None or not verify_password(body.password, user.password_hash):
        raise DomainError("INVALID_CREDENTIALS", "Email or password is incorrect.", 401)
    if user.status != "active":
        raise DomainError("ACCOUNT_DISABLED", "This account is disabled.", 403)
    if user.role_name == "TENANT_ADMIN":
        from app.models import Tenant

        tenant = db.get(Tenant, user.tenant_id)
        if tenant is None or tenant.status != "active":
            raise DomainError("SHOP_UNAVAILABLE", "This shop is suspended.", 403)
    user.last_login_at = datetime.now(UTC)
    db.commit()
    return {"access_token": create_jwt(str(user.id)), "token_type": "bearer", "user": user_dict(user)}


@router.get("/me")
def me(user: User = Depends(get_current_user)) -> dict:
    return user_dict(user)
