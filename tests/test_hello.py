import pytest


@pytest.mark.unit
def test_hello_world_endpoint(client):
    """Test hello world endpoint."""
    response = client.get("/api/v1/")
    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "Hello, World!"


@pytest.mark.unit
def test_hello_name_endpoint(client):
    """Test personalized hello endpoint."""
    name = "TestUser"
    response = client.get(f"/api/v1/hello/{name}")
    assert response.status_code == 200
    data = response.json()
    assert data["message"] == f"Hello, {name}!"


@pytest.mark.unit
def test_hello_formatted_endpoint(client):
    """Test formatted hello endpoint with unified response format."""
    name = "TestUser"
    response = client.get(f"/api/v1/hello-formatted/{name}")
    assert response.status_code == 200
    data = response.json()
    assert "request_id" in data
    assert "timestamp" in data
    assert "data" in data
    assert data["data"]["message"] == f"Hello, {name}!"
    assert isinstance(data["request_id"], str)
    assert isinstance(data["timestamp"], str)


@pytest.mark.unit
def test_hello_formatted_endpoint_with_request_id(client):
    """Test formatted hello endpoint preserves custom request_id."""
    name = "TestUser"
    custom_request_id = "custom-request-id-123"
    response = client.get(
        f"/api/v1/hello-formatted/{name}",
        headers={"X-Request-ID": custom_request_id},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["request_id"] == custom_request_id
    assert response.headers["X-Request-ID"] == custom_request_id
