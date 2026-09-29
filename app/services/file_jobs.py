import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.errors import DomainError
from app.models import Order, OrderFile
from app.services.files import page_count_for
from app.services.storage import StorageService


def process_stored_file(db: Session, storage: StorageService, file_id: uuid.UUID) -> OrderFile:
    order_file = db.get(OrderFile, file_id)
    if order_file is None:
        raise DomainError("FILE_NOT_FOUND", "File was not found.", 404)
    if order_file.status == "READY":
        return order_file
    data = storage.read(order_file.storage_key)
    try:
        pages = page_count_for(data, order_file.mime_type)
    except DomainError as exc:
        order_file.status = "FAILED"
        order_file.error_message = exc.message
        order_file.processed_at = datetime.now(UTC)
        db.flush()
        raise
    order_file.page_count = pages
    order_file.status = "READY"
    order_file.error_message = None
    order_file.processed_at = datetime.now(UTC)
    order = db.get(Order, order_file.order_id)
    if order is not None and order.status == "DRAFT":
        order.status = "UPLOADED"
    db.flush()
    return order_file
