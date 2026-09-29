import uuid

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.api.deps import ShopContext, require_shop_admin
from app.core.database import get_db
from app.core.errors import DomainError
from app.models import OrderFile
from app.schemas.requests import MarkPaidIn, PricingPut, ReasonIn, SettingsPut
from app.schemas.serialize import order_dict, rule_dict, tenant_dict
from app.services.accounts import active_rules
from app.services.files import clean_logo_url, require_color
from app.services.orders import (
    approve_order,
    complete_order,
    fail_printing,
    find_idempotent,
    lock_shop_order,
    lookup_pickup,
    mark_paid,
    mark_ready,
    reject_order,
    replace_pricing,
    shop_orders,
    start_printing,
    store_idempotent,
)

router = APIRouter(prefix="/shop", tags=["shop"])


@router.get("/orders")
def list_orders(
    status: str | None = None,
    page: int = 1,
    page_size: int = 20,
    shop: ShopContext = Depends(require_shop_admin),
    db: Session = Depends(get_db),
) -> dict:
    page = max(page, 1)
    page_size = min(max(page_size, 1), 100)
    rows, total = shop_orders(db, shop.tenant.id, status, page, page_size)
    return {
        "items": [order_dict(order) for order in rows],
        "page": page,
        "page_size": page_size,
        "total": total,
    }


@router.get("/orders/lookup")
def get_by_pickup(
    pickup_code: str,
    shop: ShopContext = Depends(require_shop_admin),
    db: Session = Depends(get_db),
) -> dict:
    return order_dict(lookup_pickup(db, shop.tenant.id, pickup_code))


@router.get("/orders/{order_id}")
def get_order(
    order_id: uuid.UUID,
    shop: ShopContext = Depends(require_shop_admin),
    db: Session = Depends(get_db),
) -> dict:
    return order_dict(lock_shop_order(db, shop.tenant.id, order_id))


@router.get("/orders/{order_id}/files/{file_id}/download")
def download(
    order_id: uuid.UUID,
    file_id: uuid.UUID,
    request: Request,
    shop: ShopContext = Depends(require_shop_admin),
    db: Session = Depends(get_db),
) -> Response:
    order = lock_shop_order(db, shop.tenant.id, order_id)
    order_file = _file_on_order(order.files, file_id)
    data = request.app.state.storage.read(order_file.storage_key)
    return Response(
        content=data,
        media_type=order_file.mime_type,
        headers={"Content-Disposition": f'attachment; filename="{order_file.original_filename}"'},
    )


@router.post("/orders/{order_id}/approve")
def approve(
    order_id: uuid.UUID,
    shop: ShopContext = Depends(require_shop_admin),
    db: Session = Depends(get_db),
) -> dict:
    order = lock_shop_order(db, shop.tenant.id, order_id)
    approve_order(db, order, shop.user)
    db.commit()
    db.refresh(order)
    return order_dict(order)


@router.post("/orders/{order_id}/reject")
def reject(
    order_id: uuid.UUID,
    body: ReasonIn,
    shop: ShopContext = Depends(require_shop_admin),
    db: Session = Depends(get_db),
) -> dict:
    order = lock_shop_order(db, shop.tenant.id, order_id)
    reject_order(db, order, shop.user, body.reason)
    db.commit()
    db.refresh(order)
    return order_dict(order)


@router.post("/orders/{order_id}/mark-paid")
def paid(
    order_id: uuid.UUID,
    body: MarkPaidIn,
    request: Request,
    shop: ShopContext = Depends(require_shop_admin),
    db: Session = Depends(get_db),
) -> dict:
    key = request.headers.get("idempotency-key")
    payload_body = {"amount": str(body.amount), "currency": body.currency.upper()}
    actor = str(shop.user.id)
    path = f"/shop/orders/{order_id}/mark-paid"
    found = find_idempotent(db, actor, "POST", path, key, payload_body)
    if found and "replay" in found:
        return found["replay"]
    order = lock_shop_order(db, shop.tenant.id, order_id)
    mark_paid(db, order, shop.user, body.amount, body.currency)
    db.flush()
    result = order_dict(order)
    store_idempotent(db, actor, "POST", path, key, payload_body, result)
    db.commit()
    return result


@router.post("/orders/{order_id}/start-printing")
def printing(
    order_id: uuid.UUID,
    shop: ShopContext = Depends(require_shop_admin),
    db: Session = Depends(get_db),
) -> dict:
    order = lock_shop_order(db, shop.tenant.id, order_id)
    start_printing(db, order, shop.user)
    db.commit()
    db.refresh(order)
    return order_dict(order)


@router.post("/orders/{order_id}/print-failed")
def print_failed(
    order_id: uuid.UUID,
    body: ReasonIn,
    shop: ShopContext = Depends(require_shop_admin),
    db: Session = Depends(get_db),
) -> dict:
    order = lock_shop_order(db, shop.tenant.id, order_id)
    fail_printing(db, order, shop.user, body.reason)
    db.commit()
    db.refresh(order)
    return order_dict(order)


@router.post("/orders/{order_id}/ready")
def ready(
    order_id: uuid.UUID,
    shop: ShopContext = Depends(require_shop_admin),
    db: Session = Depends(get_db),
) -> dict:
    order = lock_shop_order(db, shop.tenant.id, order_id)
    mark_ready(db, order, shop.user)
    db.commit()
    db.refresh(order)
    return order_dict(order)


@router.post("/orders/{order_id}/complete")
def complete(
    order_id: uuid.UUID,
    shop: ShopContext = Depends(require_shop_admin),
    db: Session = Depends(get_db),
) -> dict:
    order = lock_shop_order(db, shop.tenant.id, order_id)
    complete_order(db, order, shop.user)
    db.commit()
    db.refresh(order)
    return order_dict(order)


@router.get("/pricing")
def get_pricing(shop: ShopContext = Depends(require_shop_admin), db: Session = Depends(get_db)) -> dict:
    return {"currency": shop.tenant.currency, "rules": [rule_dict(rule) for rule in active_rules(db, shop.tenant.id)]}


@router.put("/pricing")
def put_pricing(
    body: PricingPut,
    shop: ShopContext = Depends(require_shop_admin),
    db: Session = Depends(get_db),
) -> dict:
    rules = replace_pricing(db, shop.tenant.id, [item.model_dump() for item in body.rules])
    db.commit()
    return {"currency": shop.tenant.currency, "rules": [rule_dict(rule) for rule in rules]}


@router.get("/settings")
def get_settings(shop: ShopContext = Depends(require_shop_admin)) -> dict:
    return tenant_dict(shop.tenant)


@router.put("/settings")
def put_settings(
    body: SettingsPut,
    shop: ShopContext = Depends(require_shop_admin),
    db: Session = Depends(get_db),
) -> dict:
    tenant = shop.tenant
    tenant.name = body.name.strip()
    tenant.phone = body.phone
    tenant.email = body.email
    tenant.address = body.address
    tenant.primary_color = require_color(body.primary_color)
    tenant.logo_url = clean_logo_url(body.logo_url)
    db.commit()
    db.refresh(tenant)
    return tenant_dict(tenant)


def _file_on_order(files: list[OrderFile], file_id: uuid.UUID) -> OrderFile:
    for order_file in files:
        if order_file.id == file_id and order_file.deleted_at is None:
            return order_file
    raise DomainError("FILE_NOT_FOUND", "File was not found.", 404)
