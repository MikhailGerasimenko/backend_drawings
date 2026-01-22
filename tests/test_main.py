import pytest


@pytest.mark.unit
def test_root_endpoint(client):
    """Test root endpoint."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "message" in data
    assert "version" in data
    assert "docs" in data
    assert data["message"] == "Welcome to FastAPI Template"


@pytest.mark.unit
def test_root_endpoint_response_structure(client):
    """Test root endpoint response structure."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data["message"], str)
    assert isinstance(data["version"], str)
    assert isinstance(data["docs"], str)
