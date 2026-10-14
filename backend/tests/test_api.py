from fastapi.testclient import TestClient

from app.api.main import app


def test_health_endpoint():
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_memory_profile_can_be_disabled_and_read_back():
    user_id = "api-memory-test-user"
    with TestClient(app) as client:
        response = client.patch(
            f"/api/memory/profile/{user_id}/settings", json={"enabled": False}
        )
        assert response.status_code == 200

        profile = client.get(f"/api/memory/profile/{user_id}")
        assert profile.status_code == 200
        assert profile.json()["enabled"] is False

        client.delete(f"/api/memory/profile/{user_id}")
        client.patch(f"/api/memory/profile/{user_id}/settings", json={"enabled": True})
