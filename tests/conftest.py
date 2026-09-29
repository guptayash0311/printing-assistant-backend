import base64
import io
import os

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfWriter

os.environ.setdefault("JWT_SECRET", "test-secret-key-must-be-32-chars")
os.environ.setdefault("SEED_SUPER_ADMIN", "false")
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")
os.environ.setdefault("INLINE_FILE_PROCESSING", "true")
os.environ.setdefault("AUTO_CREATE_SCHEMA", "true")

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def pdf_bytes(pages: int = 1) -> bytes:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=72, height=72)
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{tmp_path / 'test.db'}")
    monkeypatch.setenv("STORAGE_ROOT", str(tmp_path / "files"))
    monkeypatch.setenv("INLINE_FILE_PROCESSING", "true")
    monkeypatch.setenv("AUTO_CREATE_SCHEMA", "true")
    monkeypatch.setenv("JWT_SECRET", "test-secret-key-must-be-32-chars")
    monkeypatch.setenv("SEED_SUPER_ADMIN", "true")
    monkeypatch.setenv("SUPER_ADMIN_EMAIL", "root@example.com")
    monkeypatch.setenv("SUPER_ADMIN_PASSWORD", "root-password-1")
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "false")
    monkeypatch.setenv("LOGIN_RATE_LIMIT", "10")
    monkeypatch.setenv("UPLOAD_RATE_LIMIT", "30")
    monkeypatch.setenv("MAX_UPLOAD_BYTES", str(20 * 1024 * 1024))
    from app.main import create_app

    app = create_app()
    with TestClient(app) as test_client:
        yield test_client


def auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def login(client: TestClient, email: str, password: str) -> dict:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return response.json()


def create_shop(client: TestClient, slug: str, email: str | None = None) -> dict:
    root = login(client, "root@example.com", "root-password-1")
    response = client.post(
        "/api/v1/admin/tenants",
        headers=auth_header(root["access_token"]),
        json={
            "name": slug.replace("-", " ").title(),
            "slug": slug,
            "admin_email": email or f"{slug}@example.com",
            "admin_password": "shop-password-1",
            "phone": "9999999999",
            "currency": "INR",
        },
    )
    assert response.status_code == 201, response.text
    admin = login(client, email or f"{slug}@example.com", "shop-password-1")
    return {"root": root, "admin": admin, "tenant": response.json()}


def open_order(client: TestClient, slug: str) -> dict:
    response = client.post(
        f"/api/v1/public/shops/{slug}/orders",
        json={"contact_name": "Asha", "contact_phone": "+919876543210"},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert "access_token" in body
    return body


def order_headers(token: str) -> dict[str, str]:
    return {"X-Order-Access-Token": token}


def upload_pdf(client: TestClient, order_id: str, token: str, pages: int = 1) -> dict:
    response = client.post(
        f"/api/v1/public/orders/{order_id}/files",
        headers=order_headers(token),
        files={"file": ("notes.pdf", pdf_bytes(pages), "application/pdf")},
    )
    assert response.status_code == 201, response.text
    return response.json()
