import secrets
import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import DomainError
from app.models import Customer, Order, OrderEvent, PricingRule, Role, Tenant, User, UserRole
from app.security.passwords import hash_password
from app.services.files import require_slug

DEFAULT_RULES = [
    ("A4_BW_SIMPLEX", "A4", "BW", "SIMPLEX", "2.00", "PAGE"),
    ("A4_BW_DUPLEX", "A4", "BW", "DUPLEX", "3.00", "SHEET"),
    ("A4_COLOR_SIMPLEX", "A4", "COLOR", "SIMPLEX", "10.00", "PAGE"),
    ("A4_COLOR_DUPLEX", "A4", "COLOR", "DUPLEX", "15.00", "SHEET"),
]

PICKUP_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def ensure_roles(db: Session) -> dict[str, Role]:
    existing = {role.name: role for role in db.scalars(select(Role)).all()}
    for name in ("SUPER_ADMIN", "TENANT_ADMIN"):
        if name not in existing:
            role = Role(name=name)
            db.add(role)
            db.flush()
            existing[name] = role
    return existing


def ensure_super_admin(db: Session, settings: Settings) -> None:
    roles = ensure_roles(db)
    email = settings.super_admin_email.lower()
    user = db.scalar(select(User).where(User.email == email))
    if user is not None:
        return
    user = User(
        email=email,
        password_hash=hash_password(settings.super_admin_password),
        status="active",
    )
    db.add(user)
    db.flush()
    db.add(UserRole(user_id=user.id, role_id=roles["SUPER_ADMIN"].id))


def create_tenant(
    db: Session,
    *,
    name: str,
    slug: str,
    admin_email: str,
    admin_password: str,
    phone: str | None,
    currency: str,
    address: str | None,
) -> tuple[Tenant, User]:
    slug = require_slug(slug)
    if db.scalar(select(Tenant).where(Tenant.slug == slug)):
        raise DomainError("SLUG_TAKEN", "That shop link is already in use.", 409)
    email = admin_email.lower().strip()
    if db.scalar(select(User).where(User.email == email)):
        raise DomainError("EMAIL_TAKEN", "That email is already in use.", 409)
    if len(admin_password) < 8:
        raise DomainError("WEAK_PASSWORD", "Password must be at least 8 characters.", 400)
    currency = currency.upper()
    if len(currency) != 3:
        raise DomainError("INVALID_CURRENCY", "Currency must be a 3-letter code.", 400)
    roles = ensure_roles(db)
    tenant = Tenant(
        name=name.strip(),
        slug=slug,
        phone=phone,
        currency=currency,
        address=address,
        status="active",
    )
    db.add(tenant)
    db.flush()
    admin = User(
        tenant_id=tenant.id,
        email=email,
        password_hash=hash_password(admin_password),
        status="active",
    )
    db.add(admin)
    db.flush()
    db.add(UserRole(user_id=admin.id, role_id=roles["TENANT_ADMIN"].id))
    for code, paper, color, sides, price, unit in DEFAULT_RULES:
        db.add(
            PricingRule(
                tenant_id=tenant.id,
                code=code,
                config_json={
                    "paper_size": paper,
                    "color_mode": color,
                    "sides": sides,
                    "unit_price": price,
                    "unit": unit,
                },
                version=1,
                active=True,
            )
        )
    db.flush()
    return tenant, admin


def next_order_number(db: Session, tenant_id: uuid.UUID) -> str:
    today = datetime.now(UTC).strftime("%Y%m%d")
    prefix = f"PR-{today}-"
    count = db.query(Order).filter(
        Order.tenant_id == tenant_id,
        Order.order_number.like(f"{prefix}%"),
    ).count()
    return f"{prefix}{count + 1:04d}"


def new_pickup_code(db: Session, tenant_id: uuid.UUID) -> str:
    for _ in range(8):
        code = "".join(secrets.choice(PICKUP_ALPHABET) for _ in range(4))
        taken = db.scalar(
            select(Order.id).where(Order.tenant_id == tenant_id, Order.pickup_code == code)
        )
        if taken is None:
            return code
    raise DomainError("PICKUP_CODE_FAILED", "Could not issue a pickup code.", 500)


def get_or_create_customer(db: Session, tenant_id: uuid.UUID, name: str, phone: str) -> Customer:
    customer = db.scalar(
        select(Customer).where(Customer.tenant_id == tenant_id, Customer.phone == phone)
    )
    if customer is None:
        customer = Customer(tenant_id=tenant_id, name=name, phone=phone)
        db.add(customer)
        db.flush()
        return customer
    customer.name = name
    return customer


def add_event(
    db: Session,
    order: Order,
    event_type: str,
    actor_type: str,
    actor_id: str | None,
    metadata: dict | None = None,
) -> None:
    db.add(
        OrderEvent(
            tenant_id=order.tenant_id,
            order_id=order.id,
            event_type=event_type,
            actor_type=actor_type,
            actor_id=actor_id,
            metadata_json=metadata or {},
        )
    )


def active_rules(db: Session, tenant_id: uuid.UUID) -> list[PricingRule]:
    return list(
        db.scalars(
            select(PricingRule).where(PricingRule.tenant_id == tenant_id, PricingRule.active.is_(True))
        ).all()
    )


def money_str(value: Decimal | str) -> str:
    return str(Decimal(value).quantize(Decimal("0.01")))
