from fastapi.testclient import TestClient
from app.main import app


def test_health_ok():
    """Test health check endpoint"""
    client = TestClient(app)
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_root_endpoint():
    """Test root endpoint"""
    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "HR Platform Backend"
    assert data["status"] == "ok"
    assert "docs" in data
    assert "health" in data
