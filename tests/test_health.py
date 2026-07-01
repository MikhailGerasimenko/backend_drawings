import pytest

from app.core.config import settings


@pytest.mark.unit
def test_health_endpoint(client):
    """Test health check endpoint."""
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "timestamp" in data
    assert data["service"] == settings.app_name


@pytest.mark.unit
def test_health_endpoint_response_structure(client):
    """Test health endpoint response structure."""
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data["status"], str)
    assert isinstance(data["timestamp"], str)
    assert isinstance(data["service"], str)
