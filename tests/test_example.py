import pytest


@pytest.mark.unit
def test_example_endpoint_success(client):
    """Test example endpoint with valid item_id."""
    item_id = 1
    response = client.get(f"/api/v1/example/{item_id}")
    assert response.status_code == 200
    data = response.json()
    assert "request_id" in data
    assert "timestamp" in data
    assert "data" in data
    assert data["data"]["id"] == item_id
    assert data["data"]["name"] == f"Example Item {item_id}"
    assert data["data"]["status"] == "active"


@pytest.mark.unit
def test_example_endpoint_not_found(client):
    """Test example endpoint with invalid item_id."""
    item_id = 0
    response = client.get(f"/api/v1/example/{item_id}")
    assert response.status_code == 404
    data = response.json()
    assert "request_id" in data
    assert "timestamp" in data
    assert "error" in data
    assert data["error"]["code"] == "HTTP_404"
    assert "not found" in data["error"]["message"].lower()


@pytest.mark.unit
def test_example_endpoint_negative_id(client):
    """Test example endpoint with negative item_id."""
    item_id = -1
    response = client.get(f"/api/v1/example/{item_id}")
    assert response.status_code == 404
    data = response.json()
    assert "error" in data
    assert data["error"]["code"] == "HTTP_404"
