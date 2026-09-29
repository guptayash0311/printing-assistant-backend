from app.models import (
    Order,
    OrderEvent,
    OrderFile,
    OrderItem,
    Payment,
    PricingRule,
    PrintSegment,
    Tenant,
    User,
)
from app.services.accounts import money_str
from app.services.pricing import Quote


def tenant_dict(tenant: Tenant) -> dict:
    return {
        "id": str(tenant.id),
        "name": tenant.name,
        "slug": tenant.slug,
        "status": tenant.status,
        "logo_url": tenant.logo_url,
        "primary_color": tenant.primary_color,
        "address": tenant.address,
        "phone": tenant.phone,
        "email": tenant.email,
        "timezone": tenant.timezone,
        "currency": tenant.currency,
    }


def user_dict(user: User) -> dict:
    return {
        "id": str(user.id),
        "email": user.email,
        "role": user.role_name,
        "tenant_id": str(user.tenant_id) if user.tenant_id else None,
    }


def file_dict(order_file: OrderFile) -> dict:
    return {
        "id": str(order_file.id),
        "original_filename": order_file.original_filename,
        "mime_type": order_file.mime_type,
        "size_bytes": order_file.size_bytes,
        "page_count": order_file.page_count,
        "status": order_file.status,
        "error_message": order_file.error_message,
    }


def segment_dict(segment: PrintSegment) -> dict:
    return {
        "id": str(segment.id),
        "file_id": str(segment.file_id),
        "page_start": segment.page_start,
        "page_end": segment.page_end,
        "paper_size": segment.paper_size,
        "color_mode": segment.color_mode,
        "sides": segment.sides,
        "orientation": segment.orientation,
        "copies": segment.copies,
        "paper_type": segment.paper_type,
        "notes": segment.notes,
    }


def item_dict(item: OrderItem) -> dict:
    return {
        "id": str(item.id),
        "item_type": item.item_type,
        "description": item.description,
        "quantity": money_str(item.quantity),
        "unit_price": money_str(item.unit_price),
        "total": money_str(item.total),
        "metadata": item.metadata_json,
    }


def payment_dict(payment: Payment) -> dict:
    return {
        "id": str(payment.id),
        "provider": payment.provider,
        "amount": money_str(payment.amount),
        "currency": payment.currency,
        "status": payment.status,
    }


def event_dict(event: OrderEvent) -> dict:
    return {
        "id": str(event.id),
        "event_type": event.event_type,
        "actor_type": event.actor_type,
        "actor_id": event.actor_id,
        "metadata": event.metadata_json,
        "created_at": event.created_at.isoformat(),
    }


def order_dict(order: Order) -> dict:
    return {
        "id": str(order.id),
        "tenant_id": str(order.tenant_id),
        "order_number": order.order_number,
        "pickup_code": order.pickup_code,
        "status": order.status,
        "currency": order.currency,
        "subtotal": money_str(order.subtotal),
        "discount_total": money_str(order.discount_total),
        "tax_total": money_str(order.tax_total),
        "service_fee": money_str(order.service_fee),
        "grand_total": money_str(order.grand_total),
        "pricing_version": order.pricing_version,
        "contact_name": order.contact_name,
        "contact_phone": order.contact_phone,
        "notes": order.notes,
        "rejection_reason": order.rejection_reason,
        "created_at": order.created_at.isoformat(),
        "files": [file_dict(item) for item in order.files if item.deleted_at is None],
        "segments": [segment_dict(item) for item in order.segments],
        "items": [item_dict(item) for item in order.items],
        "payments": [payment_dict(item) for item in order.payments],
        "events": [event_dict(item) for item in sorted(order.events, key=lambda event: event.created_at)],
    }


def quote_dict(quote: Quote) -> dict:
    return {
        "currency": quote.currency,
        "pricing_version": quote.pricing_version,
        "subtotal": money_str(quote.subtotal),
        "discount_total": money_str(quote.discount_total),
        "tax_total": money_str(quote.tax_total),
        "service_fee": money_str(quote.service_fee),
        "grand_total": money_str(quote.grand_total),
        "line_items": [
            {
                "description": line.description,
                "quantity": money_str(line.quantity),
                "unit_price": money_str(line.unit_price),
                "total": money_str(line.total),
                "metadata": line.metadata,
            }
            for line in quote.line_items
        ],
    }


def rule_dict(rule: PricingRule) -> dict:
    config = rule.config_json
    return {
        "id": str(rule.id),
        "code": rule.code,
        "paper_size": config["paper_size"],
        "color_mode": config["color_mode"],
        "sides": config["sides"],
        "unit_price": config["unit_price"],
        "unit": config["unit"],
        "version": rule.version,
        "active": rule.active,
    }
