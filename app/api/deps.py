import uuid
from collections.abc import Generator
from typing import NamedTuple

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.errors import DomainError
from app.models import Tenant, User
from app.security.passwords import decode_jwt

_bearer = HTTPBearer(auto_error=False)


class ShopContext(NamedTuple):
    user: User
    tenant: Tenant


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    if creds is None:
        raise DomainError("UNAUTHENTICATED", "Login is required.", 401)
    try:
        payload = decode_jwt(creds.credentials)
        user_id = uuid.UUID(payload["sub"])
    except (jwt.PyJWTError, ValueError, KeyError) as exc:
        raise DomainError("UNAUTHENTICATED", "Login is required.", 401) from exc
    user = db.get(User, user_id)
    if user is None or user.status != "active":
        raise DomainError("UNAUTHENTICATED", "Login is required.", 401)
    return user


def require_super_admin(user: User = Depends(get_current_user)) -> User:
    if user.role_name != "SUPER_ADMIN":
        raise DomainError("FORBIDDEN", "Platform admin access is required.", 403)
    return user


def require_shop_admin(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ShopContext:
    if user.role_name != "TENANT_ADMIN" or user.tenant_id is None:
        raise DomainError("FORBIDDEN", "Shop admin access is required.", 403)
    tenant = db.get(Tenant, user.tenant_id)
    if tenant is None or tenant.status != "active":
        raise DomainError("SHOP_UNAVAILABLE", "This shop is suspended.", 403)
    return ShopContext(user, tenant)


def db_session() -> Generator[Session, None, None]:
    yield from get_db()
