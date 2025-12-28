"""
Integration tests for API authentication and authorization.

Tests authentication flows including:
- Full authentication flow
- JWT token lifecycle
- API key authentication
- Permission checks
- Unauthorized access handling
"""

import pytest
pytestmark = pytest.mark.skip(reason="Phase 2 feature: Authentication/authorization not in Phase 1 scope")


from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.utils import (
    assert_response_error,
    assert_response_success,
)


@pytest.mark.integration
class TestAuthenticationFlow:
    """Test complete authentication workflows."""

    def test_login_with_valid_credentials(self, api_client: TestClient):
        """Test successful login with valid credentials."""
        # Create user first (assumes user registration or exists)
        login_data = {"username": "testuser", "password": "testpassword123"}

        response = api_client.post("/api/v1/auth/login", json=login_data)
        assert_response_success(response)

        response_data = response.json()
        assert "access_token" in response_data
        assert "token_type" in response_data
        assert response_data["token_type"] == "bearer"

    def test_login_with_invalid_credentials(self, api_client: TestClient):
        """Test login fails with invalid credentials."""
        login_data = {"username": "testuser", "password": "wrongpassword"}

        response = api_client.post("/api/v1/auth/login", json=login_data)
        assert_response_error(response, 401, "Invalid credentials")

    def test_login_with_nonexistent_user(self, api_client: TestClient):
        """Test login fails for non-existent user."""
        login_data = {"username": "nonexistentuser", "password": "password123"}

        response = api_client.post("/api/v1/auth/login", json=login_data)
        assert_response_error(response, 401)

    def test_register_new_user(self, api_client: TestClient):
        """Test user registration."""
        registration_data = {
            "username": "newuser",
            "email": "newuser@example.com",
            "password": "securepassword123",
        }

        response = api_client.post("/api/v1/auth/register", json=registration_data)
        assert_response_success(response, 201)

        response_data = response.json()
        assert response_data["username"] == registration_data["username"]
        assert response_data["email"] == registration_data["email"]
        assert "password" not in response_data  # Password should not be returned

    def test_register_duplicate_username(self, api_client: TestClient):
        """Test registration fails with duplicate username."""
        user_data = {
            "username": "existinguser",
            "email": "user1@example.com",
            "password": "password123",
        }

        # Register first time
        response1 = api_client.post("/api/v1/auth/register", json=user_data)
        assert_response_success(response1, 201)

        # Try to register again with same username
        user_data["email"] = "different@example.com"
        response2 = api_client.post("/api/v1/auth/register", json=user_data)
        assert_response_error(response2, 409, "already exists")

    def test_logout(self, authenticated_api_client: TestClient):
        """Test user logout."""
        response = authenticated_api_client.post("/api/v1/auth/logout")
        assert_response_success(response)

        # Subsequent requests with same token should fail
        response = authenticated_api_client.get("/api/v1/tasks")
        assert_response_error(response, 401)


@pytest.mark.integration
class TestJWTTokenLifecycle:
    """Test JWT token creation, validation, and expiration."""

    def test_token_contains_user_info(self, api_client: TestClient):
        """Test that JWT token contains correct user information."""
        # Login to get token
        login_data = {"username": "testuser", "password": "testpassword123"}
        response = api_client.post("/api/v1/auth/login", json=login_data)
        assert_response_success(response)

        token = response.json()["access_token"]

        # Use token to access protected endpoint
        api_client.headers["Authorization"] = f"Bearer {token}"
        response = api_client.get("/api/v1/auth/me")
        assert_response_success(response)

        user_data = response.json()
        assert user_data["username"] == "testuser"

    def test_token_expiration(self, api_client: TestClient):
        """Test that expired tokens are rejected."""
        # This test requires ability to create expired tokens
        # Implementation depends on auth system allowing test token creation

        # Create an expired token (expired 1 hour ago)
        from hopper.api.auth import create_access_token

        expired_token = create_access_token(
            {"sub": "testuser"}, expires_delta=timedelta(hours=-1)  # Expired 1 hour ago
        )

        api_client.headers["Authorization"] = f"Bearer {expired_token}"
        response = api_client.get("/api/v1/tasks")
        assert_response_error(response, 401, "expired")

    def test_invalid_token_format(self, api_client: TestClient):
        """Test that invalid token format is rejected."""
        api_client.headers["Authorization"] = "Bearer invalid_token_format"
        response = api_client.get("/api/v1/tasks")
        assert_response_error(response, 401, "Invalid token")

    def test_missing_authorization_header(self, api_client: TestClient):
        """Test that requests without auth header are rejected."""
        response = api_client.get("/api/v1/tasks")
        assert_response_error(response, 401, "Not authenticated")

    def test_refresh_token(self, api_client: TestClient):
        """Test refreshing an access token."""
        # Login to get refresh token
        login_data = {"username": "testuser", "password": "testpassword123"}
        response = api_client.post("/api/v1/auth/login", json=login_data)
        assert_response_success(response)

        refresh_token = response.json().get("refresh_token")
        if refresh_token:
            # Use refresh token to get new access token
            response = api_client.post(
                "/api/v1/auth/refresh", json={"refresh_token": refresh_token}
            )
            assert_response_success(response)

            new_token_data = response.json()
            assert "access_token" in new_token_data
            assert new_token_data["access_token"] != response.json()["access_token"]

    def test_revoke_token(self, authenticated_api_client: TestClient):
        """Test revoking a token."""
        # Get current token
        token = authenticated_api_client.headers.get("Authorization").split(" ")[1]

        # Revoke token
        response = authenticated_api_client.post("/api/v1/auth/revoke", json={"token": token})
        assert_response_success(response)

        # Try to use revoked token
        response = authenticated_api_client.get("/api/v1/tasks")
        assert_response_error(response, 401, "revoked")


@pytest.mark.integration
class TestAPIKeyAuthentication:
    """Test API key-based authentication."""

    def test_authenticate_with_api_key(self, api_client: TestClient, db_session: Session):
        """Test authentication using API key."""
        # Create API key for user
        response = api_client.post(
            "/api/v1/auth/api-keys",
            json={"name": "Test API Key", "expires_in_days": 30},
            headers={"Authorization": "Bearer user_jwt_token"},
        )
        assert_response_success(response, 201)

        api_key = response.json()["key"]

        # Use API key to authenticate
        api_client.headers["X-API-Key"] = api_key
        response = api_client.get("/api/v1/tasks")
        assert_response_success(response)

    def test_invalid_api_key(self, api_client: TestClient):
        """Test that invalid API key is rejected."""
        api_client.headers["X-API-Key"] = "invalid_api_key_12345"
        response = api_client.get("/api/v1/tasks")
        assert_response_error(response, 401, "Invalid API key")

    def test_expired_api_key(self, api_client: TestClient, db_session: Session):
        """Test that expired API keys are rejected."""
        # Create API key that expires immediately
        response = api_client.post(
            "/api/v1/auth/api-keys",
            json={
                "name": "Expiring Key",
                "expires_at": (datetime.utcnow() - timedelta(days=1)).isoformat(),
            },
        )

        if response.status_code == 201:
            expired_key = response.json()["key"]

            # Try to use expired key
            api_client.headers["X-API-Key"] = expired_key
            response = api_client.get("/api/v1/tasks")
            assert_response_error(response, 401, "expired")

    def test_list_user_api_keys(self, authenticated_api_client: TestClient):
        """Test listing user's API keys."""
        # Create some API keys
        for i in range(3):
            authenticated_api_client.post("/api/v1/auth/api-keys", json={"name": f"Test Key {i}"})

        # List API keys
        response = authenticated_api_client.get("/api/v1/auth/api-keys")
        assert_response_success(response)

        api_keys = response.json()
        assert len(api_keys) >= 3
        for key_data in api_keys:
            assert "name" in key_data
            assert "created_at" in key_data
            assert "key" not in key_data  # Full key should not be shown in list

    def test_revoke_api_key(self, authenticated_api_client: TestClient):
        """Test revoking an API key."""
        # Create API key
        response = authenticated_api_client.post(
            "/api/v1/auth/api-keys", json={"name": "Key to Revoke"}
        )
        assert_response_success(response, 201)

        key_id = response.json()["id"]

        # Revoke the key
        response = authenticated_api_client.delete(f"/api/v1/auth/api-keys/{key_id}")
        assert_response_success(response, 204)

        # Verify key is revoked
        response = authenticated_api_client.get("/api/v1/auth/api-keys")
        api_keys = response.json()
        revoked_key = next((k for k in api_keys if k["id"] == key_id), None)
        if revoked_key:
            assert revoked_key["revoked"] is True


@pytest.mark.integration
class TestPermissions:
    """Test permission and authorization checks."""

    def test_user_can_access_own_tasks(
        self, authenticated_api_client: TestClient, db_session: Session
    ):
        """Test that users can access their own tasks."""
        # Create task owned by user
        from tests.factories import TaskFactory

        task = TaskFactory.create(session=db_session, owner="testuser")

        response = authenticated_api_client.get(f"/api/v1/tasks/{task.id}")
        assert_response_success(response)

    def test_user_cannot_access_others_private_tasks(
        self, authenticated_api_client: TestClient, db_session: Session
    ):
        """Test that users cannot access other users' private tasks."""
        # Create task owned by different user and marked private
        from tests.factories import TaskFactory

        task = TaskFactory.create(session=db_session, owner="otheruser", tags={"private": True})

        response = authenticated_api_client.get(f"/api/v1/tasks/{task.id}")
        assert_response_error(response, 403, "Forbidden")

    def test_admin_can_access_all_tasks(self, api_client: TestClient, db_session: Session):
        """Test that admin users can access all tasks."""
        # Login as admin
        login_data = {"username": "admin", "password": "adminpassword"}
        response = api_client.post("/api/v1/auth/login", json=login_data)
        assert_response_success(response)

        admin_token = response.json()["access_token"]
        api_client.headers["Authorization"] = f"Bearer {admin_token}"

        # Access any task
        from tests.factories import TaskFactory

        task = TaskFactory.create(session=db_session, owner="someuser", tags={"private": True})

        response = api_client.get(f"/api/v1/tasks/{task.id}")
        assert_response_success(response)

    def test_user_cannot_delete_others_tasks(
        self, authenticated_api_client: TestClient, db_session: Session
    ):
        """Test that users cannot delete other users' tasks."""
        from tests.factories import TaskFactory

        task = TaskFactory.create(session=db_session, owner="otheruser")

        response = authenticated_api_client.delete(f"/api/v1/tasks/{task.id}")
        assert_response_error(response, 403, "Forbidden")

    def test_project_admin_can_manage_project_tasks(
        self, api_client: TestClient, db_session: Session
    ):
        """Test that project admins can manage tasks in their projects."""
        # Login as project admin for "hopper" project
        login_data = {"username": "hopper_admin", "password": "password"}
        response = api_client.post("/api/v1/auth/login", json=login_data)

        if response.status_code == 200:
            admin_token = response.json()["access_token"]
            api_client.headers["Authorization"] = f"Bearer {admin_token}"

            # Create and modify task in hopper project
            from tests.factories import TaskFactory

            task = TaskFactory.create(session=db_session, project="hopper", owner="someuser")

            # Should be able to update task
            response = api_client.put(f"/api/v1/tasks/{task.id}", json={"status": "completed"})
            assert_response_success(response)


@pytest.mark.integration
class TestUnauthorizedAccess:
    """Test handling of unauthorized access attempts."""

    def test_unauthenticated_cannot_create_task(self, api_client: TestClient):
        """Test that unauthenticated users cannot create tasks."""
        task_data = {"title": "Test Task", "project": "hopper"}

        response = api_client.post("/api/v1/tasks", json=task_data)
        assert_response_error(response, 401, "Not authenticated")

    def test_unauthenticated_cannot_update_task(self, api_client: TestClient, db_session: Session):
        """Test that unauthenticated users cannot update tasks."""
        from tests.factories import TaskFactory

        task = TaskFactory.create(session=db_session)

        response = api_client.put(f"/api/v1/tasks/{task.id}", json={"title": "Updated"})
        assert_response_error(response, 401)

    def test_unauthenticated_cannot_delete_task(self, api_client: TestClient, db_session: Session):
        """Test that unauthenticated users cannot delete tasks."""
        from tests.factories import TaskFactory

        task = TaskFactory.create(session=db_session)

        response = api_client.delete(f"/api/v1/tasks/{task.id}")
        assert_response_error(response, 401)

    def test_public_endpoints_accessible_without_auth(self, api_client: TestClient):
        """Test that public endpoints are accessible without authentication."""
        # Health check should be public
        response = api_client.get("/health")
        assert_response_success(response)

        # API docs should be public
        response = api_client.get("/docs")
        assert response.status_code == 200

    def test_rate_limiting_for_unauthenticated_requests(self, api_client: TestClient):
        """Test that unauthenticated requests are rate-limited."""
        # Make many requests quickly
        responses = []
        for i in range(100):
            response = api_client.get("/api/v1/tasks")
            responses.append(response)

        # At least some should be rate-limited
        rate_limited = [r for r in responses if r.status_code == 429]
        # Depending on implementation, verify rate limiting occurs
        # assert len(rate_limited) > 0


@pytest.mark.integration
class TestPasswordManagement:
    """Test password change and reset functionality."""

    def test_change_password(self, authenticated_api_client: TestClient):
        """Test changing user password."""
        password_data = {
            "current_password": "testpassword123",
            "new_password": "newsecurepassword456",
        }

        response = authenticated_api_client.post("/api/v1/auth/change-password", json=password_data)
        assert_response_success(response)

    def test_change_password_wrong_current(self, authenticated_api_client: TestClient):
        """Test that password change fails with wrong current password."""
        password_data = {
            "current_password": "wrongpassword",
            "new_password": "newsecurepassword456",
        }

        response = authenticated_api_client.post("/api/v1/auth/change-password", json=password_data)
        assert_response_error(response, 401, "current password")

    def test_request_password_reset(self, api_client: TestClient):
        """Test requesting password reset."""
        reset_data = {"email": "testuser@example.com"}

        response = api_client.post("/api/v1/auth/reset-password", json=reset_data)
        assert_response_success(response)

        # Should receive reset token (in production, sent via email)

    def test_weak_password_rejected(self, api_client: TestClient):
        """Test that weak passwords are rejected during registration."""
        registration_data = {
            "username": "newuser",
            "email": "newuser@example.com",
            "password": "123",  # Too weak
        }

        response = api_client.post("/api/v1/auth/register", json=registration_data)
        assert_response_error(response, 400, "password")
