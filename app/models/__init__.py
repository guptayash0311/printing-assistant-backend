import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import JSON


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(20), default="active")
    logo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    primary_color: Mapped[str] = mapped_column(String(7), default="#1f4b3a")
    address: Mapped[str | None] = mapped_column(String(300), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    email: Mapped[str | None] = mapped_column(String(200), nullable=True)
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Kolkata")
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(40), unique=True)


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("tenants.id"), nullable=True)
    email: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(20), default="active")
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    roles: Mapped[list[Role]] = relationship(secondary="user_roles")

    @property
    def role_name(self) -> str | None:
        if not self.roles:
            return None
        return self.roles[0].name


class UserRole(Base):
    __tablename__ = "user_roles"
    __table_args__ = (UniqueConstraint("user_id", "role_id"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    role_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("roles.id"))


class Customer(Base):
    __tablename__ = "customers"
    __table_args__ = (UniqueConstraint("tenant_id", "phone"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tenants.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    phone: Mapped[str] = mapped_column(String(30))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (
        UniqueConstraint("tenant_id", "order_number"),
        UniqueConstraint("tenant_id", "pickup_code"),
        Index("ix_orders_tenant_status_created", "tenant_id", "status", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tenants.id"), index=True)
    customer_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("customers.id"), nullable=True)
    order_number: Mapped[str] = mapped_column(String(32))
    pickup_code: Mapped[str | None] = mapped_column(String(8), nullable=True)
    access_token_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), default="DRAFT")
    currency: Mapped[str] = mapped_column(String(3))
    subtotal: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    discount_total: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    tax_total: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    service_fee: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    grand_total: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    pricing_version: Mapped[int | None] = mapped_column(nullable=True)
    contact_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    contact_phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    files: Mapped[list["OrderFile"]] = relationship(back_populates="order", cascade="all, delete-orphan")
    segments: Mapped[list["PrintSegment"]] = relationship(
        back_populates="order", cascade="all, delete-orphan"
    )
    items: Mapped[list["OrderItem"]] = relationship(back_populates="order", cascade="all, delete-orphan")
    events: Mapped[list["OrderEvent"]] = relationship(back_populates="order", cascade="all, delete-orphan")
    payments: Mapped[list["Payment"]] = relationship(back_populates="order", cascade="all, delete-orphan")


class OrderFile(Base):
    __tablename__ = "order_files"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tenants.id"), index=True)
    order_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("orders.id"), index=True)
    original_filename: Mapped[str] = mapped_column(String(255))
    storage_key: Mapped[str] = mapped_column(String(500), unique=True)
    mime_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int]
    checksum: Mapped[str] = mapped_column(String(64))
    page_count: Mapped[int | None] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="UPLOADING")
    error_message: Mapped[str | None] = mapped_column(String(300), nullable=True)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    order: Mapped[Order] = relationship(back_populates="files")


class PrintSegment(Base):
    __tablename__ = "print_segments"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    order_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("orders.id"), index=True)
    file_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("order_files.id"))
    page_start: Mapped[int]
    page_end: Mapped[int]
    paper_size: Mapped[str] = mapped_column(String(20))
    color_mode: Mapped[str] = mapped_column(String(20))
    sides: Mapped[str] = mapped_column(String(20))
    orientation: Mapped[str] = mapped_column(String(20))
    copies: Mapped[int]
    paper_type: Mapped[str] = mapped_column(String(20), default="PLAIN")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    order: Mapped[Order] = relationship(back_populates="segments")


class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tenants.id"), index=True)
    order_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("orders.id"), index=True)
    item_type: Mapped[str] = mapped_column(String(40))
    description: Mapped[str] = mapped_column(String(300))
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    total: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)

    order: Mapped[Order] = relationship(back_populates="items")


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tenants.id"), index=True)
    order_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("orders.id"), index=True)
    provider: Mapped[str] = mapped_column(String(40))
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(3))
    status: Mapped[str] = mapped_column(String(20))
    marked_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    order: Mapped[Order] = relationship(back_populates="payments")


class PricingRule(Base):
    __tablename__ = "pricing_rules"
    __table_args__ = (Index("ix_pricing_rules_tenant_active", "tenant_id", "active"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tenants.id"), index=True)
    code: Mapped[str] = mapped_column(String(80))
    rule_type: Mapped[str] = mapped_column(String(40), default="print")
    config_json: Mapped[dict] = mapped_column(JSON)
    active: Mapped[bool] = mapped_column(default=True)
    effective_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(default=1)


class OrderEvent(Base):
    __tablename__ = "order_events"
    __table_args__ = (Index("ix_order_events_order_created", "tenant_id", "order_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tenants.id"))
    order_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("orders.id"))
    event_type: Mapped[str] = mapped_column(String(40))
    actor_type: Mapped[str] = mapped_column(String(20))
    actor_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    order: Mapped[Order] = relationship(back_populates="events")


class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"
    __table_args__ = (UniqueConstraint("actor", "method", "path", "key"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    actor: Mapped[str] = mapped_column(String(80))
    method: Mapped[str] = mapped_column(String(10))
    path: Mapped[str] = mapped_column(String(200))
    key: Mapped[str] = mapped_column(String(80))
    request_hash: Mapped[str] = mapped_column(String(64))
    response_status: Mapped[int]
    response_body: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
