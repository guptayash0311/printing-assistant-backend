"""Seed the platform admin and a sample shop.

Run from the backend root:

    python scripts/seed.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from app.core.config import get_settings
from app.core.database import configure_engine, get_session
from app.core.errors import DomainError
from app.models import Tenant
from app.services.accounts import create_tenant, ensure_super_admin

SAMPLE_SHOPS = [
    {
        "name": "Green Leaf Prints",
        "slug": "green-leaf",
        "admin_email": "shop@example.com",
        "admin_password": "shop-password-1",
        "phone": "9876543210",
        "currency": "INR",
        "address": "12 Market Road, Kochi",
    },
]


def main() -> None:
    settings = get_settings()
    configure_engine()
    db = get_session()
    try:
        ensure_super_admin(db, settings)
        print(f"platform admin: {settings.super_admin_email}")

        for shop in SAMPLE_SHOPS:
            existing = db.scalar(select(Tenant).where(Tenant.slug == shop["slug"]))
            if existing is not None:
                print(f"shop exists: {shop['slug']}")
                continue
            try:
                tenant, admin = create_tenant(db, **shop)
            except DomainError as exc:
                print(f"skipped {shop['slug']}: {exc.message}")
                continue
            print(f"shop: /s/{tenant.slug}  admin: {admin.email}")

        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    main()
