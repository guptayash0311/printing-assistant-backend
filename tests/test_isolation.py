from tests.conftest import auth_header, create_shop, login, open_order, order_headers, upload_pdf


def test_tenant_admin_cannot_open_platform_routes(client):
    shop = create_shop(client, "alpha")
    response = client.get("/api/v1/admin/tenants", headers=auth_header(shop["admin"]["access_token"]))
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def test_shop_admin_cannot_read_another_shops_order_or_file(client):
    create_shop(client, "alpha")
    beta = create_shop(client, "beta")
    created = open_order(client, "alpha")
    uploaded = upload_pdf(client, created["id"], created["access_token"])
    headers = auth_header(beta["admin"]["access_token"])
    order_response = client.get(f"/api/v1/shop/orders/{created['id']}", headers=headers)
    assert order_response.status_code == 404
    download = client.get(
        f"/api/v1/shop/orders/{created['id']}/files/{uploaded['id']}/download",
        headers=headers,
    )
    assert download.status_code == 404
    pricing = client.get("/api/v1/shop/pricing", headers=headers)
    assert pricing.status_code == 200
    assert all(rule["code"].startswith("A4_") for rule in pricing.json()["rules"])


def test_order_access_token_does_not_open_another_order(client):
    create_shop(client, "alpha")
    first = open_order(client, "alpha")
    second = open_order(client, "alpha")
    response = client.get(
        f"/api/v1/public/orders/{second['id']}",
        headers=order_headers(first["access_token"]),
    )
    assert response.status_code == 404


def test_suspended_shop_is_closed(client):
    shop = create_shop(client, "alpha")
    suspended = client.post(
        f"/api/v1/admin/tenants/{shop['tenant']['id']}/suspend",
        headers=auth_header(shop["root"]["access_token"]),
    )
    assert suspended.status_code == 200
    public = client.get("/api/v1/public/shops/alpha")
    assert public.status_code == 403
    denied = client.post(
        "/api/v1/auth/login",
        json={"email": "alpha@example.com", "password": "shop-password-1"},
    )
    assert denied.status_code == 403
    assert login(client, "root@example.com", "root-password-1")["user"]["role"] == "SUPER_ADMIN"
