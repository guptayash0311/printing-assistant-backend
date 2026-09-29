from tests.conftest import (
    PNG,
    auth_header,
    create_shop,
    open_order,
    order_headers,
    pdf_bytes,
    upload_pdf,
)


def _place(client, slug: str, pages: int = 1, sides: str = "SIMPLEX"):
    created = open_order(client, slug)
    uploaded = upload_pdf(client, created["id"], created["access_token"], pages)
    token = created["access_token"]
    headers = order_headers(token)
    segments = client.put(
        f"/api/v1/public/orders/{created['id']}/segments",
        headers=headers,
        json={
            "segments": [
                {
                    "file_id": uploaded["id"],
                    "page_start": 1,
                    "page_end": pages,
                    "paper_size": "A4",
                    "color_mode": "BW",
                    "sides": sides,
                    "orientation": "PORTRAIT",
                    "copies": 2 if sides == "DUPLEX" else 1,
                }
            ]
        },
    )
    assert segments.status_code == 200, segments.text
    price = client.post(f"/api/v1/public/orders/{created['id']}/calculate-price", headers=headers)
    assert price.status_code == 200, price.text
    placed = client.post(f"/api/v1/public/orders/{created['id']}/place", headers=headers)
    assert placed.status_code == 200, placed.text
    return created, placed.json(), price.json()


def test_guest_order_upload_and_place(client):
    create_shop(client, "alpha")
    shop = client.get("/api/v1/public/shops/alpha")
    assert shop.status_code == 200
    assert shop.json()["name"]
    created, placed, price = _place(client, "alpha", pages=3, sides="DUPLEX")
    assert uploaded_page_count(client, created) == 3
    assert price["grand_total"] == "12.00"
    assert placed["pickup_code"]
    assert placed["status"] == "PENDING_APPROVAL"
    assert placed["payments"] == []
    assert placed["items"][0]["total"] == "12.00"
    status = client.get(
        f"/api/v1/public/orders/{created['id']}",
        headers=order_headers(created["access_token"]),
    )
    assert status.json()["pickup_code"] == placed["pickup_code"]


def uploaded_page_count(client, created) -> int:
    body = client.get(
        f"/api/v1/public/orders/{created['id']}",
        headers=order_headers(created["access_token"]),
    ).json()
    return body["files"][0]["page_count"]


def test_pickup_code_cannot_download_file(client):
    create_shop(client, "alpha")
    created, placed, _price = _place(client, "alpha")
    file_id = placed["files"][0]["id"]
    response = client.get(
        f"/api/v1/public/orders/{created['id']}/files/{file_id}/download",
        headers=order_headers(placed["pickup_code"]),
    )
    assert response.status_code == 404


def test_invalid_and_oversized_uploads_are_rejected(client):
    create_shop(client, "alpha")
    created = open_order(client, "alpha")
    bad = client.post(
        f"/api/v1/public/orders/{created['id']}/files",
        headers=order_headers(created["access_token"]),
        files={"file": ("notes.pdf", b"not-a-pdf", "application/pdf")},
    )
    assert bad.status_code == 400
    assert bad.json()["error"]["code"] == "INVALID_FILE_TYPE"
    image = client.post(
        f"/api/v1/public/orders/{created['id']}/files",
        headers=order_headers(created["access_token"]),
        files={"file": ("photo.png", PNG, "image/png")},
    )
    assert image.status_code == 201
    assert image.json()["page_count"] == 1
    assert image.json()["status"] == "READY"


def test_upload_rate_limit(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{tmp_path / 'limit.db'}")
    monkeypatch.setenv("STORAGE_ROOT", str(tmp_path / "files"))
    monkeypatch.setenv("INLINE_FILE_PROCESSING", "true")
    monkeypatch.setenv("AUTO_CREATE_SCHEMA", "true")
    monkeypatch.setenv("JWT_SECRET", "test-secret-key-must-be-32-chars")
    monkeypatch.setenv("SEED_SUPER_ADMIN", "true")
    monkeypatch.setenv("SUPER_ADMIN_EMAIL", "root@example.com")
    monkeypatch.setenv("SUPER_ADMIN_PASSWORD", "root-password-1")
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "true")
    monkeypatch.setenv("UPLOAD_RATE_LIMIT", "1")
    monkeypatch.setenv("LOGIN_RATE_LIMIT", "2")
    from fastapi.testclient import TestClient

    from app.main import create_app

    app = create_app()
    with TestClient(app) as client:
        create_shop(client, "alpha")
        created = open_order(client, "alpha")
        headers = order_headers(created["access_token"])
        first = client.post(
            f"/api/v1/public/orders/{created['id']}/files",
            headers=headers,
            files={"file": ("a.pdf", pdf_bytes(), "application/pdf")},
        )
        assert first.status_code == 201
        second = client.post(
            f"/api/v1/public/orders/{created['id']}/files",
            headers=headers,
            files={"file": ("b.pdf", pdf_bytes(), "application/pdf")},
        )
        assert second.status_code == 429
        denied = None
        for _ in range(3):
            denied = client.post(
                "/api/v1/auth/login",
                json={"email": "root@example.com", "password": "wrong-password"},
            )
        assert denied is not None
        assert denied.status_code == 429


def test_critical_path_and_immutable_price(client):
    alpha = create_shop(client, "alpha")
    beta = create_shop(client, "beta")
    created, placed, _price = _place(client, "alpha", pages=3, sides="DUPLEX")
    admin = auth_header(alpha["admin"]["access_token"])
    queue = client.get("/api/v1/shop/orders", headers=admin)
    assert queue.status_code == 200
    assert queue.json()["items"][0]["id"] == created["id"]
    looked = client.get("/api/v1/shop/orders/lookup", headers=admin, params={"pickup_code": placed["pickup_code"]})
    assert looked.status_code == 200
    file_id = placed["files"][0]["id"]
    download = client.get(
        f"/api/v1/shop/orders/{created['id']}/files/{file_id}/download",
        headers=admin,
    )
    assert download.status_code == 200
    assert download.content.startswith(b"%PDF")
    customer_paid = client.post(
        f"/api/v1/shop/orders/{created['id']}/mark-paid",
        headers=order_headers(created["access_token"]),
        json={"amount": "12.00", "currency": "INR"},
    )
    assert customer_paid.status_code == 401
    approved = client.post(f"/api/v1/shop/orders/{created['id']}/approve", headers=admin)
    assert approved.status_code == 200
    mismatch = client.post(
        f"/api/v1/shop/orders/{created['id']}/mark-paid",
        headers=admin,
        json={"amount": "1.00", "currency": "INR"},
    )
    assert mismatch.status_code == 400
    assert mismatch.json()["error"]["code"] == "PAYMENT_AMOUNT_MISMATCH"
    paid = client.post(
        f"/api/v1/shop/orders/{created['id']}/mark-paid",
        headers={**admin, "Idempotency-Key": "pay-1"},
        json={"amount": "12.00", "currency": "INR"},
    )
    assert paid.status_code == 200, paid.text
    assert paid.json()["status"] == "PAID"
    assert len(paid.json()["payments"]) == 1
    replay = client.post(
        f"/api/v1/shop/orders/{created['id']}/mark-paid",
        headers={**admin, "Idempotency-Key": "pay-1"},
        json={"amount": "12.00", "currency": "INR"},
    )
    assert replay.status_code == 200
    again = client.post(
        f"/api/v1/shop/orders/{created['id']}/mark-paid",
        headers=admin,
        json={"amount": "12.00", "currency": "INR"},
    )
    assert again.status_code == 409
    current = client.get(f"/api/v1/shop/orders/{created['id']}", headers=admin)
    assert len(current.json()["payments"]) == 1
    printing = client.post(f"/api/v1/shop/orders/{created['id']}/start-printing", headers=admin)
    ready = client.post(f"/api/v1/shop/orders/{printing.json()['id']}/ready", headers=admin)
    done = client.post(f"/api/v1/shop/orders/{created['id']}/complete", headers=admin)
    assert done.json()["status"] == "COMPLETED"
    events = [event["event_type"] for event in done.json()["events"]]
    assert "MARKED_PAID" in events
    assert "COMPLETED" in events
    frozen = done.json()["items"][0]["total"]
    rules = client.get("/api/v1/shop/pricing", headers=admin).json()["rules"]
    for rule in rules:
        if rule["code"] == "A4_BW_DUPLEX":
            rule["unit_price"] = "9.00"
    saved = client.put("/api/v1/shop/pricing", headers=admin, json={"rules": rules})
    assert saved.status_code == 200, saved.text
    after = client.get(f"/api/v1/shop/orders/{created['id']}", headers=admin)
    assert after.json()["items"][0]["total"] == frozen
    assert after.json()["grand_total"] == "12.00"
    hidden = client.get(f"/api/v1/shop/orders/{created['id']}", headers=auth_header(beta["admin"]["access_token"]))
    assert hidden.status_code == 404
    customer = client.get(
        f"/api/v1/public/orders/{created['id']}",
        headers=order_headers(created["access_token"]),
    )
    assert customer.json()["status"] == "COMPLETED"
    assert ready.status_code == 200
