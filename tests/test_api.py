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


def test_alarm_test_without_webhook(monkeypatch):
    monkeypatch.delenv("ALARM_WEBHOOK_URL", raising=False)
    response = client.post(
        "/api/v1/alarms/test",
        json={"station_code": "87242000", "level_m": 3.2},
    )
    assert response.status_code == 200
    assert response.json()["published"] is False
