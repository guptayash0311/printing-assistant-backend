import uuid

from fastapi import APIRouter, Depends, File, Request, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.errors import DomainError
from app.models import OrderFile
from app.schemas.requests import CreateOrderIn, SegmentsIn
from app.schemas.serialize import file_dict, order_dict, quote_dict, rule_dict, tenant_dict
from app.services.accounts import active_rules
from app.services.orders import (
    calculate_order_price,
    create_order,
    find_idempotent,
    load_customer_order,
    place_order,
    public_tenant,
    remove_upload,
    replace_segments,
    save_upload,
    store_idempotent,
)

router = APIRouter(prefix="/public", tags=["public"])


def _token(request: Request) -> str | None:
    return request.headers.get("x-order-access-token")


@router.get("/shops/{slug}")
def get_shop(slug: str, db: Session = Depends(get_db)) -> dict:
    return tenant_dict(public_tenant(db, slug))


@router.get("/shops/{slug}/pricing")
def get_pricing(slug: str, db: Session = Depends(get_db)) -> dict:
    tenant = public_tenant(db, slug)
    rules = [rule_dict(rule) for rule in active_rules(db, tenant.id)]
    return {"currency": tenant.currency, "rules": rules}


@router.post("/shops/{slug}/orders", status_code=201)
def post_order(slug: str, body: CreateOrderIn, db: Session = Depends(get_db)) -> dict:
    tenant = public_tenant(db, slug)
    order, token = create_order(db, tenant, body.contact_name, body.contact_phone)
    db.commit()
    db.refresh(order)
    payload = order_dict(order)
    payload["access_token"] = token
    return payload


@router.get("/orders/{order_id}")
def get_order(order_id: uuid.UUID, request: Request, db: Session = Depends(get_db)) -> dict:
    order = load_customer_order(db, order_id, _token(request))
    return order_dict(order)


@router.post("/orders/{order_id}/files", status_code=201)
async def post_file(
    order_id: uuid.UUID,
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> dict:
    settings = request.app.state.settings
    if settings.rate_limit_enabled:
        ip = request.client.host if request.client else "unknown"
        request.app.state.limiter.check(
            f"upload:{ip}:{order_id}",
            settings.upload_rate_limit,
            settings.rate_limit_window_seconds,
        )
    order = load_customer_order(db, order_id, _token(request))
    data = await file.read()
    saved = save_upload(
        db,
        request.app.state.storage,
        order,
        file.filename or "file",
        data,
        settings.max_upload_bytes,
        settings.inline_file_processing,
    )
    db.commit()
    db.refresh(saved)
    return file_dict(saved)


@router.delete("/orders/{order_id}/files/{file_id}")
def delete_file(
    order_id: uuid.UUID,
    file_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
) -> dict:
    order = load_customer_order(db, order_id, _token(request))
    remove_upload(db, order, file_id)
    db.commit()
    db.refresh(order)
    return order_dict(order)


@router.get("/orders/{order_id}/files/{file_id}")
def get_file(
    order_id: uuid.UUID,
    file_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
) -> dict:
    order = load_customer_order(db, order_id, _token(request))
    return file_dict(_file_on_order(order.files, file_id))


@router.get("/orders/{order_id}/files/{file_id}/download")
def download_file(
    order_id: uuid.UUID,
    file_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
) -> Response:
    order = load_customer_order(db, order_id, _token(request))
    order_file = _file_on_order(order.files, file_id)
    data = request.app.state.storage.read(order_file.storage_key)
    return Response(
        content=data,
        media_type=order_file.mime_type,
        headers={"Content-Disposition": f'attachment; filename="{order_file.original_filename}"'},
    )


@router.put("/orders/{order_id}/segments")
def put_segments(
    order_id: uuid.UUID,
    body: SegmentsIn,
    request: Request,
    db: Session = Depends(get_db),
) -> dict:
    order = load_customer_order(db, order_id, _token(request))
    replace_segments(db, order, [item.model_dump() for item in body.segments])
    db.commit()
    db.refresh(order)
    return order_dict(order)


@router.post("/orders/{order_id}/calculate-price")
def post_price(order_id: uuid.UUID, request: Request, db: Session = Depends(get_db)) -> dict:
    order = load_customer_order(db, order_id, _token(request))
    quote = calculate_order_price(db, order)
    db.commit()
    return quote_dict(quote)


@router.post("/orders/{order_id}/place")
def post_place(order_id: uuid.UUID, request: Request, db: Session = Depends(get_db)) -> dict:
    order = load_customer_order(db, order_id, _token(request))
    key = request.headers.get("idempotency-key")
    found = find_idempotent(db, str(order.id), "POST", f"/orders/{order.id}/place", key, {})
    if found and "replay" in found:
        return found["replay"]
    place_order(db, order)
    db.flush()
    payload = order_dict(order)
    store_idempotent(db, str(order.id), "POST", f"/orders/{order.id}/place", key, {}, payload)
    db.commit()
    return payload


def _file_on_order(files: list[OrderFile], file_id: uuid.UUID) -> OrderFile:
    for order_file in files:
        if order_file.id == file_id and order_file.deleted_at is None:
            return order_file
    raise DomainError("FILE_NOT_FOUND", "File was not found.", 404)
