import logging
import uuid

import redis

from app.core.config import load_settings
from app.core.database import configure_engine, get_session
from app.core.errors import DomainError
from app.services.file_jobs import process_stored_file
from app.services.storage import StorageService

logger = logging.getLogger("printshop.worker")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    settings = load_settings()
    configure_engine()
    storage = StorageService(settings.storage_root)
    client = redis.Redis.from_url(settings.redis_url)
    logger.info("file worker listening")
    while True:
        item = client.brpop("file_jobs", timeout=5)
        if not item:
            continue
        file_id = uuid.UUID(item[1].decode())
        db = get_session()
        try:
            process_stored_file(db, storage, file_id)
            db.commit()
        except DomainError:
            db.commit()
            logger.info("file processing failed", extra={"file_id": str(file_id)})
        except Exception:
            db.rollback()
            logger.exception("file job crashed")
        finally:
            db.close()


if __name__ == "__main__":
    main()
