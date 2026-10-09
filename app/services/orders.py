import hashlib
import json
import uuid
from decimal import Decimal

from sqlalchemy import case, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import DomainError
from app.domain.states import assert_transition
from app.models import (
    IdempotencyKey,
    Order,
    OrderFile,
    OrderItem,
    Payment,
    PricingRule,
    PrintSegment,
    Tenant,
    User,
    utcnow,
)
from app.security.passwords import new_access_token, tokens_match
from app.services.accounts import (
    active_rules,
    add_event,
    get_or_create_customer,
    money_str,
    new_pickup_code,
    next_order_number,
)
from app.services.file_jobs import process_stored_file
from app.services.files import checksum, detect_mime, normalize_phone
from app.services.pricing import PriceRule, Quote, SegmentQuoteInput, calculate_quote, money
from app.services.storage import StorageService, safe_filename

MUTABLE = {"DRAFT", "UPLOADED", "PRICE_CALCULATED"}


def public_tenant(db: Session, slug: str) -> Tenant:
    tenant = db.scalar(select(Tenant).where(Tenant.slug == slug))
    if tenant is None:
        raise DomainError("SHOP_NOT_FOUND", "Shop was not found.", 404)
    if tenant.status != "active":
        raise DomainError("SHOP_UNAVAILABLE", "This shop is not accepting orders.", 403)
    return tenant


def create_order(
    db: Session, tenant: Tenant, name: str | None, phone: str | None
) -> tuple[Order, str]:
    contact = (name or "").strip() or None
    raw_phone = (phone or "").strip()
    normalized = normalize_phone(raw_phone) if raw_phone else None
    customer = get_or_create_customer(db, tenant.id, contact, normalized) if normalized else None
    token = new_access_token()
    order = Order(
        tenant_id=tenant.id,
        customer_id=customer.id if customer else None,
        order_number=next_order_number(db, tenant.id),
        access_token_hash=hashlib.sha256(token.encode("utf-8")).hexdigest(),
        status="DRAFT",
        currency=tenant.currency,
        contact_name=contact,
        contact_phone=normalized,
    )
    db.add(order)
    db.flush()
    add_event(db, order, "ORDER_CREATED", "customer", _customer_actor(order), {})
    return order, token


def _customer_actor(order: Order) -> str | None:
    if order.customer_id is None:
        return None
    return str(order.customer_id)


def load_customer_order(db: Session, order_id: uuid.UUID, raw_token: str | None) -> Order:
    order = db.get(Order, order_id)
    if order is None or not tokens_match(raw_token, order.access_token_hash):
        raise DomainError("ORDER_NOT_FOUND", "Order was not found.", 404)
    return order


def lock_shop_order(db: Session, tenant_id: uuid.UUID, order_id: uuid.UUID) -> Order:
    query = select(Order).where(Order.id == order_id, Order.tenant_id == tenant_id)
    if db.get_bind().dialect.name == "postgresql":
        query = query.with_for_update()
    order = db.scalar(query)
    if order is None:
        raise DomainError("ORDER_NOT_FOUND", "Order was not found.", 404)
    return order


def save_upload(
    db: Session,
    storage: StorageService,
    order: Order,
    filename: str,
    data: bytes,
    max_bytes: int,
    inline: bool,
) -> OrderFile:
    if order.status not in MUTABLE:
        raise DomainError("INVALID_ORDER_STATE", "Files cannot be added after the order is placed.", 409)
    if len(data) == 0:
        raise DomainError("INVALID_FILE", "The file is empty.", 400)
    if len(data) > max_bytes:
        raise DomainError("FILE_TOO_LARGE", "The file is larger than the upload limit.", 413)
    mime = detect_mime(data)
    order_file = OrderFile(
        tenant_id=order.tenant_id,
        order_id=order.id,
        original_filename=safe_filename(filename),
        storage_key="pending",
        mime_type=mime,
        size_bytes=len(data),
        checksum=checksum(data),
        status="PROCESSING",
    )
    db.add(order_file)
    db.flush()
    key = (
        f"tenants/{order.tenant_id}/orders/{order.id}/files/{order_file.id}/original/"
        f"{order_file.original_filename}"
    )
    order_file.storage_key = key
    storage.write(key, data)
    if order.status == "PRICE_CALCULATED":
        _clear_quote(order)
        order.status = "UPLOADED"
    db.flush()
    if inline:
        try:
            process_stored_file(db, storage, order_file.id)
        except DomainError:
            storage.delete(key)
            raise
    else:
        try:
            _enqueue(order_file.id)
        except Exception as exc:
            storage.delete(key)
            raise DomainError("FILE_QUEUE_UNAVAILABLE", "File processing is unavailable.", 503) from exc
    add_event(db, order, "FILE_UPLOADED", "customer", _customer_actor(order), {"file_id": str(order_file.id)})
    return order_file


def remove_upload(db: Session, order: Order, file_id: uuid.UUID) -> None:
    if order.status not in MUTABLE:
        raise DomainError("INVALID_ORDER_STATE", "Files cannot be removed after the order is placed.", 409)
    order_file = next((item for item in order.files if item.id == file_id and item.deleted_at is None), None)
    if order_file is None:
        raise DomainError("FILE_NOT_FOUND", "File was not found.", 404)
    order_file.deleted_at = utcnow()
    for segment in list(order.segments):
        if segment.file_id == order_file.id:
            db.delete(segment)
    if order.status == "PRICE_CALCULATED":
        _clear_quote(order)
        order.status = "UPLOADED"
    db.flush()
    db.expire(order, ["segments", "files"])
    add_event(db, order, "FILE_REMOVED", "customer", _customer_actor(order), {"file_id": str(order_file.id)})


def replace_segments(db: Session, order: Order, segments: list[dict]) -> None:
    if order.status not in MUTABLE:
        raise DomainError("INVALID_ORDER_STATE", "Print options are locked after the order is placed.", 409)
    files = {
        str(item.id): item
        for item in order.files
        if item.status == "READY" and item.deleted_at is None
    }
    if not segments:
        raise DomainError("INVALID_PRINT_CONFIGURATION", "Add at least one print range.", 400)
    grouped: dict[str, list[tuple[int, int]]] = {}
    built: list[PrintSegment] = []
    for raw in segments:
        file_id = str(raw["file_id"])
        order_file = files.get(file_id)
        if order_file is None or order_file.page_count is None:
            raise DomainError("FILE_NOT_READY", "Wait until every file has finished processing.", 409)
        start = int(raw["page_start"])
        end = int(raw["page_end"])
        if start < 1 or end < start or end > order_file.page_count:
            raise DomainError("INVALID_PRINT_CONFIGURATION", "Page range is outside the document.", 400)
        grouped.setdefault(file_id, []).append((start, end))
        built.append(
            PrintSegment(
                order_id=order.id,
                file_id=order_file.id,
                page_start=start,
                page_end=end,
                paper_size=raw["paper_size"],
                color_mode=raw["color_mode"],
                sides=raw["sides"],
                orientation=raw["orientation"],
                copies=int(raw["copies"]),
                paper_type="PLAIN",
            )
        )
    ready_ids = set(files)
    if ready_ids - set(grouped):
        raise DomainError(
            "INVALID_PRINT_CONFIGURATION",
            "Every uploaded file needs a print range.",
            400,
        )
    for ranges in grouped.values():
        ordered = sorted(ranges)
        for left, right in zip(ordered, ordered[1:], strict=False):
            if left[1] >= right[0]:
                raise DomainError("INVALID_PRINT_CONFIGURATION", "Page ranges on a file overlap.", 400)
    for existing in list(order.segments):
        db.delete(existing)
    db.flush()
    for segment in built:
        db.add(segment)
    if order.status == "PRICE_CALCULATED":
        _clear_quote(order)
        order.status = "UPLOADED"
    db.flush()


def calculate_order_price(db: Session, order: Order) -> Quote:
    if order.status not in {"UPLOADED", "PRICE_CALCULATED"}:
        raise DomainError("INVALID_ORDER_STATE", "Upload files and set print options before pricing.", 409)
    quote = _quote_order(db, order)
    _apply_quote(order, quote)
    if order.status == "UPLOADED":
        assert_transition(order.status, "PRICE_CALCULATED")
        order.status = "PRICE_CALCULATED"
    add_event(
        db,
        order,
        "PRICE_CALCULATED",
        "customer",
        _customer_actor(order),
        {"grand_total": money_str(quote.grand_total)},
    )
    return quote


def place_order(db: Session, order: Order) -> Order:
    if order.status != "PRICE_CALCULATED":
        raise DomainError("INVALID_ORDER_STATE", "Calculate the price before placing the order.", 409)
    quote = _quote_order(db, order)
    for existing in list(order.items):
        db.delete(existing)
    db.flush()
    for line in quote.line_items:
        db.add(
            OrderItem(
                tenant_id=order.tenant_id,
                order_id=order.id,
                item_type="print",
                description=line.description,
                quantity=line.quantity,
                unit_price=line.unit_price,
                total=line.total,
                metadata_json=line.metadata,
            )
        )
    _apply_quote(order, quote)
    order.pickup_code = new_pickup_code(db, order.tenant_id)
    assert_transition(order.status, "PENDING_APPROVAL")
    order.status = "PENDING_APPROVAL"
    add_event(
        db,
        order,
        "ORDER_PLACED",
        "customer",
        _customer_actor(order),
        {"pickup_code": order.pickup_code, "grand_total": money_str(order.grand_total)},
    )
    db.flush()
    db.expire(order, ["items", "events", "payments"])
    return order


def shop_orders(
    db: Session,
    tenant_id: uuid.UUID,
    status: str | None,
    page: int,
    page_size: int,
) -> tuple[list[Order], int]:
    query = select(Order).where(Order.tenant_id == tenant_id)
    if status:
        query = query.where(Order.status == status)
    total = len(db.scalars(query).all())
    rank = case((Order.status == "PENDING_APPROVAL", 0), else_=1)
    rows = db.scalars(
        query.order_by(rank, Order.created_at.asc()).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return list(rows), total


def lookup_pickup(db: Session, tenant_id: uuid.UUID, pickup_code: str) -> Order:
    order = db.scalar(
        select(Order).where(Order.tenant_id == tenant_id, Order.pickup_code == pickup_code.strip().upper())
    )
    if order is None:
        raise DomainError("ORDER_NOT_FOUND", "Order was not found.", 404)
    return order


def approve_order(db: Session, order: Order, user: User) -> Order:
    _move(db, order, "APPROVED", user, "APPROVED")
    return order


def reject_order(db: Session, order: Order, user: User, reason: str) -> Order:
    cleaned = reason.strip()
    if not cleaned:
        raise DomainError("REJECTION_REASON_REQUIRED", "Enter a reason for rejecting the order.", 400)
    order.rejection_reason = cleaned
    _move(db, order, "REJECTED", user, "REJECTED", {"reason": cleaned})
    return order


def mark_paid(db: Session, order: Order, user: User, amount: Decimal, currency: str) -> Order:
    if order.status != "APPROVED":
        raise DomainError("INVALID_ORDER_STATE", "Only an approved order can be marked paid.", 409)
    if currency.upper() != order.currency or money(amount) != money(order.grand_total):
        raise DomainError(
            "PAYMENT_AMOUNT_MISMATCH",
            "Amount must match the frozen order total.",
            400,
        )
    db.add(
        Payment(
            tenant_id=order.tenant_id,
            order_id=order.id,
            provider="counter",
            amount=money(order.grand_total),
            currency=order.currency,
            status="PAID",
            marked_by=user.id,
        )
    )
    _move(db, order, "PAID", user, "MARKED_PAID", {"amount": money_str(order.grand_total)})
    return order


def start_printing(db: Session, order: Order, user: User) -> Order:
    _move(db, order, "PRINTING", user, "PRINTING_STARTED")
    return order


def fail_printing(db: Session, order: Order, user: User, reason: str) -> Order:
    _move(db, order, "PRINT_FAILED", user, "PRINT_FAILED", {"reason": reason.strip()})
    return order


def mark_ready(db: Session, order: Order, user: User) -> Order:
    _move(db, order, "READY", user, "READY")
    return order


def complete_order(db: Session, order: Order, user: User) -> Order:
    _move(db, order, "COMPLETED", user, "COMPLETED")
    return order


def find_idempotent(
    db: Session, actor: str, method: str, path: str, key: str | None, body: dict
) -> dict | None:
    if not key:
        return None
    request_hash = hashlib.sha256(json.dumps(body, sort_keys=True, default=str).encode()).hexdigest()
    existing = db.scalar(
        select(IdempotencyKey).where(
            IdempotencyKey.actor == actor,
            IdempotencyKey.method == method,
            IdempotencyKey.path == path,
            IdempotencyKey.key == key,
        )
    )
    if existing is None:
        return {"pending_hash": request_hash}
    if existing.request_hash != request_hash:
        raise DomainError("IDEMPOTENCY_CONFLICT", "This idempotency key was already used.", 409)
    return {"replay": existing.response_body}


def store_idempotent(
    db: Session,
    actor: str,
    method: str,
    path: str,
    key: str | None,
    body: dict,
    response_body: dict,
) -> None:
    if not key:
        return
    request_hash = hashlib.sha256(json.dumps(body, sort_keys=True, default=str).encode()).hexdigest()
    db.add(
        IdempotencyKey(
            actor=actor,
            method=method,
            path=path,
            key=key,
            request_hash=request_hash,
            response_status=200,
            response_body=response_body,
        )
    )
    try:
        db.flush()
    except IntegrityError as exc:
        raise DomainError("IDEMPOTENCY_CONFLICT", "This idempotency key was already used.", 409) from exc


def _move(db: Session, order: Order, target: str, user: User, event_type: str, metadata: dict | None = None) -> None:
    assert_transition(order.status, target)
    order.status = target
    add_event(db, order, event_type, "user", str(user.id), metadata)
    db.flush()
    db.expire(order, ["items", "events", "payments"])


def _quote_order(db: Session, order: Order) -> Quote:
    ready = [item for item in order.files if item.status == "READY" and item.deleted_at is None]
    if any(item.status in {"UPLOADING", "PROCESSING"} and item.deleted_at is None for item in order.files):
        raise DomainError("FILE_NOT_READY", "Wait until every file has finished processing.", 409)
    if not ready:
        raise DomainError("FILE_NOT_READY", "Upload a PDF or image before pricing.", 409)
    if not order.segments:
        raise DomainError("INVALID_PRINT_CONFIGURATION", "Add at least one print range.", 400)
    files = {item.id: item for item in ready}
    inputs: list[SegmentQuoteInput] = []
    for segment in order.segments:
        order_file = files.get(segment.file_id)
        if order_file is None or order_file.page_count is None:
            raise DomainError("FILE_NOT_READY", "A print range points at a file that is not ready.", 409)
        inputs.append(
            SegmentQuoteInput(
                file_id=str(segment.file_id),
                page_start=segment.page_start,
                page_end=segment.page_end,
                paper_size=segment.paper_size,
                color_mode=segment.color_mode,
                sides=segment.sides,
                copies=segment.copies,
                page_count=order_file.page_count,
                filename=order_file.original_filename,
            )
        )
    rules = [
        PriceRule(
            code=rule.code,
            paper_size=rule.config_json["paper_size"],
            color_mode=rule.config_json["color_mode"],
            sides=rule.config_json["sides"],
            unit_price=Decimal(rule.config_json["unit_price"]),
            unit=rule.config_json["unit"],
            version=rule.version,
        )
        for rule in active_rules(db, order.tenant_id)
    ]
    return calculate_quote(rules, inputs, order.currency)


def _apply_quote(order: Order, quote: Quote) -> None:
    order.currency = quote.currency
    order.subtotal = quote.subtotal
    order.discount_total = quote.discount_total
    order.tax_total = quote.tax_total
    order.service_fee = quote.service_fee
    order.grand_total = quote.grand_total
    order.pricing_version = quote.pricing_version


def _clear_quote(order: Order) -> None:
    order.subtotal = Decimal("0.00")
    order.discount_total = Decimal("0.00")
    order.tax_total = Decimal("0.00")
    order.service_fee = Decimal("0.00")
    order.grand_total = Decimal("0.00")
    order.pricing_version = None


def _enqueue(file_id: uuid.UUID) -> None:
    from app.core.config import get_settings

    settings = get_settings()
    import redis

    client = redis.Redis.from_url(settings.redis_url)
    client.lpush("file_jobs", str(file_id))


def replace_pricing(db: Session, tenant_id: uuid.UUID, rules: list[dict]) -> list[PricingRule]:
    current = active_rules(db, tenant_id)
    version = max((rule.version for rule in current), default=0) + 1
    for rule in current:
        rule.active = False
    created: list[PricingRule] = []
    seen: set[tuple[str, str, str]] = set()
    for raw in rules:
        identity = (raw["paper_size"], raw["color_mode"], raw["sides"])
        if identity in seen:
            raise DomainError("INVALID_PRICING", "Each paper, color, and sides combination must be unique.", 400)
        seen.add(identity)
        row = PricingRule(
            tenant_id=tenant_id,
            code=raw["code"],
            config_json={
                "paper_size": raw["paper_size"],
                "color_mode": raw["color_mode"],
                "sides": raw["sides"],
                "unit_price": money_str(raw["unit_price"]),
                "unit": raw["unit"],
            },
            active=True,
            version=version,
        )
        db.add(row)
        created.append(row)
    db.flush()
    return created
