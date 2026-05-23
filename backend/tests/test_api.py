from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_dashboard_shape():
    response = client.get("/api/dashboard")
    assert response.status_code == 200
    data = response.json()
    assert data["date"]
    assert data["signals"]
    assert data["portfolio"]["base_amount"] > 0
    for item in data["signals"]:
        assert "trend_score" in item
        assert "recommended_action" in item


def test_simulate_changes_hard_stop():
    base = client.get("/api/dashboard").json()
    response = client.post(
        "/api/simulate",
        json={"overrides": {"valuation": {"hard_stop_percentile": 60}}},
    )
    assert response.status_code == 200
    changed = response.json()["dashboard"]
    assert changed["signals"]
    base_zero = sum(1 for item in base["signals"] if item["multiplier"] == 0)
    changed_zero = sum(1 for item in changed["signals"] if item["multiplier"] == 0)
    assert changed_zero >= base_zero
