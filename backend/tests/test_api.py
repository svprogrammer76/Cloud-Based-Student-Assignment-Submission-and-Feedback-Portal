from fastapi.testclient import TestClient
from app.main import app
from app.services.auth import current_user

client = TestClient(app)


def test_health_is_available_without_auth():
    assert client.get("/health").json() == {"status": "ok"}


def test_api_rejects_missing_firebase_token():
    assert client.get("/api/courses").status_code == 401


def test_student_cannot_create_course():
    app.dependency_overrides[current_user] = lambda: {"uid": "student-1", "email": "student@example.edu", "name": "Student", "role": "student"}
    try:
        response = client.post("/api/courses", json={"name": "Cloud", "description": ""})
        assert response.status_code == 403
    finally:
        app.dependency_overrides.clear()
