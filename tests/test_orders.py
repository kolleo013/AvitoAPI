import pytest
from fastapi.testclient import TestClient

from app import main


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "test.db")
    with TestClient(main.app) as client:
        yield client


def payload(items=None):
    return {
        "customer_id": "demo-user",
        "address": "Пермь, Ленина, 1",
        "items": items if items is not None else [{"dish_id": 1, "quantity": 2}],
    }


def test_order_lifecycle(client):
    response = client.post("/orders", json=payload())
    assert response.status_code == 201
    order = response.json()
    assert order["total_kopecks"] == 70000
    assert order["status"] == "pending"
    headers = {"X-Cafe-Token": main.CAFE_TOKEN}
    assert client.get("/partner/orders").status_code == 401
    assert len(client.get("/partner/orders", headers=headers).json()) == 1
    for _ in range(2):
        result = client.post(f"/partner/orders/{order['id']}/accept", headers=headers)
        assert result.status_code == 200
        assert result.json()["status"] == "accepted"
    assert client.get(f"/orders/{order['id']}").json()["status"] == "accepted"
    assert client.get("/partner/orders", headers=headers).json() == []


@pytest.mark.parametrize(
    "items,status",
    [
        ([], 422),
        ([{"dish_id": 1, "quantity": 0}], 422),
        ([{"dish_id": 999, "quantity": 1}], 404),
        ([{"dish_id": 3, "quantity": 1}], 409),
        ([{"dish_id": 1, "quantity": 1}, {"dish_id": 999, "quantity": 1}], 404),
        ([{"dish_id": 1, "quantity": 1}, {"dish_id": 1, "quantity": 1}], 422),
    ],
)
def test_invalid_order_leaves_database_unchanged(client, items, status):
    assert client.post("/orders", json=payload(items)).status_code == status
    with main.database() as db:
        assert db.execute("SELECT count(*) FROM orders").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM order_items").fetchone()[0] == 0


def test_unknown_order(client):
    assert client.get("/orders/unknown").status_code == 404


def test_cafe_integration(client, monkeypatch):
    import httpx

    from app import cafe

    original_client = httpx.AsyncClient

    def local_client(**kwargs):
        return original_client(**kwargs, transport=httpx.ASGITransport(app=main.app))

    monkeypatch.setattr(cafe.httpx, "AsyncClient", local_client)
    order = client.post("/orders", json=payload()).json()
    with TestClient(cafe.app) as restaurant:
        assert restaurant.get("/orders").status_code == 401
        headers = {"X-Cafe-Token": cafe.CAFE_TOKEN}
        assert restaurant.get("/orders", headers=headers).json()[0]["id"] == order["id"]
        response = restaurant.post(f"/orders/{order['id']}/accept", headers=headers)
        assert response.status_code == 200
    assert client.get(f"/orders/{order['id']}").json()["status"] == "accepted"


def test_data_survives_restart(client):
    order = client.post("/orders", json=payload()).json()
    with TestClient(main.app) as restarted:
        assert restarted.get(f"/orders/{order['id']}").json()["total_kopecks"] == 70000
