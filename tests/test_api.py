from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "hidrosul-backend"}


def test_stations():
    response = client.get("/api/v1/stations")
    assert response.status_code == 200
    assert len(response.json()) >= 3


def test_sources_include_open_data():
    response = client.get("/api/v1/sources")
    assert response.status_code == 200
    data = response.json()
    assert "ons" in data["sources"]
    assert "open-meteo" in data["sources"]
    assert "inmet" in data["sources"]


def test_river_telemetry_is_disabled():
    response = client.get(
        "/api/v1/stations/87242000/observations",
        params={"days": 7},
    )
    assert response.status_code == 503
    assert "desativada" in response.json()["detail"]


def test_alert_subscription_requires_channel():
    response = client.post(
        "/api/v1/alerts/subscriptions",
        json={
            "city": "Porto Alegre",
            "latitude": -30.0346,
            "longitude": -51.2177,
            "email": None,
            "phone": None,
            "condition": "chuva intensa",
        },
    )
    assert response.status_code == 422


def test_alert_subscription_persists(tmp_path, monkeypatch):
    monkeypatch.setenv(
        "HIDROSUL_SUBSCRIPTION_FILE",
        str(tmp_path / "subscriptions.json"),
    )
    response = client.post(
        "/api/v1/alerts/subscriptions",
        json={
            "city": "Porto Alegre",
            "latitude": -30.0346,
            "longitude": -51.2177,
            "email": "user@example.com",
            "phone": None,
            "condition": "chuva intensa",
        },
    )
    assert response.status_code == 200
    assert response.json()["subscribed"] is True


def test_alarm_test_without_webhook(monkeypatch):
    monkeypatch.delenv("ALARM_WEBHOOK_URL", raising=False)
    response = client.post(
        "/api/v1/alarms/test",
        json={"station_code": "87242000", "level_m": 3.2},
    )
    assert response.status_code == 200
    assert response.json()["published"] is False
