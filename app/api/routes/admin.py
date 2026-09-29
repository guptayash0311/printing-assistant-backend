import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_super_admin
from app.core.database import get_db
from app.core.errors import DomainError
from app.models import Tenant, User
from app.schemas.requests import TenantCreate, TenantPatch
from app.schemas.serialize import tenant_dict
from app.services.accounts import create_tenant

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/tenants")
def list_tenants(
    _: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
) -> dict:
    tenants = db.scalars(select(Tenant).order_by(Tenant.created_at.desc())).all()
    return {"items": [tenant_dict(tenant) for tenant in tenants]}


@router.post("/tenants", status_code=201)
def post_tenant(
    body: TenantCreate,
    _: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
) -> dict:
    tenant, _admin = create_tenant(
        db,
        name=body.name,
        slug=body.slug,
        admin_email=body.admin_email,
        admin_password=body.admin_password,
        phone=body.phone,
        currency=body.currency,
        address=body.address,
    )
    db.commit()
    db.refresh(tenant)
    return tenant_dict(tenant)


@router.patch("/tenants/{tenant_id}")
def patch_tenant(
    tenant_id: uuid.UUID,
    body: TenantPatch,
    _: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
) -> dict:
    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        raise DomainError("SHOP_NOT_FOUND", "Shop was not found.", 404)
    if body.name is not None:
        tenant.name = body.name.strip()
    if body.phone is not None:
        tenant.phone = body.phone
    if body.address is not None:
        tenant.address = body.address
    db.commit()
    db.refresh(tenant)
    return tenant_dict(tenant)


@router.post("/tenants/{tenant_id}/suspend")
def suspend_tenant(
    tenant_id: uuid.UUID,
    _: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
) -> dict:
    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        raise DomainError("SHOP_NOT_FOUND", "Shop was not found.", 404)
    tenant.status = "suspended"
    db.commit()
    db.refresh(tenant)
    return tenant_dict(tenant)
