"""HTTP client wrapper for Hopper API."""

from typing import Any

import httpx

from hopper.cli.config import Config


class APIError(Exception):
    """API request error."""

    def __init__(self, message: str, status_code: int | None = None):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class HopperClient:
    """HTTP client for Hopper API.

    Handles authentication, retries, and error handling for API requests.
    """

    def __init__(self, config: Config):
        """Initialize the client.

        Args:
            config: CLI configuration object
        """
        self.config = config
        self.profile = config.current_profile
        self.base_url = self.profile.api.endpoint.rstrip("/")
        self.timeout = self.profile.api.timeout

        # Build headers
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        # Add authentication
        if self.profile.auth.token:
            headers["Authorization"] = f"Bearer {self.profile.auth.token}"
        elif self.profile.auth.api_key:
            headers["X-API-Key"] = self.profile.auth.api_key

        self.client = httpx.Client(
            base_url=self.base_url,
            headers=headers,
            timeout=self.timeout,
        )

    def __enter__(self) -> "HopperClient":
        """Context manager entry."""
        return self

    def __exit__(self, *args: Any) -> None:
        """Context manager exit."""
        self.close()

    def close(self) -> None:
        """Close the HTTP client."""
        self.client.close()

    def _handle_response(self, response: httpx.Response) -> Any:
        """Handle API response.

        Args:
            response: HTTP response object

        Returns:
            Parsed JSON response

        Raises:
            APIError: If the request failed
        """
        if response.status_code >= 400:
            try:
                error_data = response.json()
                message = error_data.get("detail", response.text)
            except Exception:
                message = response.text

            raise APIError(message, response.status_code)

        if response.status_code == 204:
            return None

        try:
            return response.json()
        except Exception:
            return response.text

    def get(self, path: str, **kwargs: Any) -> Any:
        """Send GET request.

        Args:
            path: API endpoint path
            **kwargs: Additional request parameters

        Returns:
            Response data
        """
        response = self.client.get(path, **kwargs)
        return self._handle_response(response)

    def post(self, path: str, **kwargs: Any) -> Any:
        """Send POST request.

        Args:
            path: API endpoint path
            **kwargs: Additional request parameters

        Returns:
            Response data
        """
        response = self.client.post(path, **kwargs)
        return self._handle_response(response)

    def put(self, path: str, **kwargs: Any) -> Any:
        """Send PUT request.

        Args:
            path: API endpoint path
            **kwargs: Additional request parameters

        Returns:
            Response data
        """
        response = self.client.put(path, **kwargs)
        return self._handle_response(response)

    def patch(self, path: str, **kwargs: Any) -> Any:
        """Send PATCH request.

        Args:
            path: API endpoint path
            **kwargs: Additional request parameters

        Returns:
            Response data
        """
        response = self.client.patch(path, **kwargs)
        return self._handle_response(response)

    def delete(self, path: str, **kwargs: Any) -> Any:
        """Send DELETE request.

        Args:
            path: API endpoint path
            **kwargs: Additional request parameters

        Returns:
            Response data
        """
        response = self.client.delete(path, **kwargs)
        return self._handle_response(response)

    # Task API methods
    def create_task(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create a new task."""
        return self.post("/api/v1/tasks", json=data)

    def list_tasks(self, **params: Any) -> list[dict[str, Any]]:
        """List tasks with optional filters."""
        return self.get("/api/v1/tasks", params=params)

    def get_task(self, task_id: str) -> dict[str, Any]:
        """Get task by ID."""
        return self.get(f"/api/v1/tasks/{task_id}")

    def update_task(self, task_id: str, data: dict[str, Any]) -> dict[str, Any]:
        """Update task."""
        return self.patch(f"/api/v1/tasks/{task_id}", json=data)

    def delete_task(self, task_id: str) -> None:
        """Delete task."""
        return self.delete(f"/api/v1/tasks/{task_id}")

    def search_tasks(self, query: str, **params: Any) -> list[dict[str, Any]]:
        """Search tasks."""
        return self.get("/api/v1/tasks/search", params={"q": query, **params})

    # Project API methods
    def create_project(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create a new project."""
        return self.post("/api/v1/projects", json=data)

    def list_projects(self, **params: Any) -> list[dict[str, Any]]:
        """List projects."""
        return self.get("/api/v1/projects", params=params)

    def get_project(self, project_id: str) -> dict[str, Any]:
        """Get project by ID."""
        return self.get(f"/api/v1/projects/{project_id}")

    def update_project(self, project_id: str, data: dict[str, Any]) -> dict[str, Any]:
        """Update project."""
        return self.patch(f"/api/v1/projects/{project_id}", json=data)

    def delete_project(self, project_id: str) -> None:
        """Delete project."""
        return self.delete(f"/api/v1/projects/{project_id}")

    # Instance API methods
    def create_instance(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create a new Hopper instance."""
        return self.post("/api/v1/instances", json=data)

    def list_instances(self, **params: Any) -> list[dict[str, Any]]:
        """List Hopper instances."""
        return self.get("/api/v1/instances", params=params)

    def get_instance(self, instance_id: str) -> dict[str, Any]:
        """Get instance by ID."""
        return self.get(f"/api/v1/instances/{instance_id}")

    def start_instance(self, instance_id: str) -> dict[str, Any]:
        """Start a Hopper instance."""
        return self.post(f"/api/v1/instances/{instance_id}/start")

    def stop_instance(self, instance_id: str) -> dict[str, Any]:
        """Stop a Hopper instance."""
        return self.post(f"/api/v1/instances/{instance_id}/stop")

    def get_instance_status(self, instance_id: str) -> dict[str, Any]:
        """Get instance status."""
        return self.get(f"/api/v1/instances/{instance_id}/status")

    # Delegation API methods
    def delegate_task(self, task_id: str, data: dict[str, Any]) -> dict[str, Any]:
        """Delegate a task to another instance."""
        return self.post(f"/api/v1/tasks/{task_id}/delegate", json=data)

    def get_task_delegations(self, task_id: str) -> dict[str, Any]:
        """Get delegation chain for a task."""
        return self.get(f"/api/v1/tasks/{task_id}/delegations")

    def accept_delegation(self, delegation_id: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
        """Accept a delegation."""
        return self.post(f"/api/v1/delegations/{delegation_id}/accept", json=data or {})

    def reject_delegation(self, delegation_id: str, reason: str) -> dict[str, Any]:
        """Reject a delegation."""
        return self.post(f"/api/v1/delegations/{delegation_id}/reject", json={"reason": reason})

    def complete_delegation(self, delegation_id: str, result: dict[str, Any] | None = None) -> dict[str, Any]:
        """Complete a delegation."""
        return self.post(f"/api/v1/delegations/{delegation_id}/complete", json={"result": result})

    def get_instance_delegations(self, instance_id: str, **params: Any) -> list[dict[str, Any]]:
        """Get delegations for an instance."""
        return self.get(f"/api/v1/instances/{instance_id}/delegations", params=params)

    # Learning API methods
    def submit_feedback(self, task_id: str, data: dict[str, Any]) -> dict[str, Any]:
        """Submit feedback for a task's routing decision."""
        return self.post(f"/api/v1/tasks/{task_id}/feedback", json=data)

    def get_task_feedback(self, task_id: str) -> dict[str, Any]:
        """Get feedback for a specific task."""
        return self.get(f"/api/v1/tasks/{task_id}/feedback")

    def list_feedback(self, **params: Any) -> dict[str, Any]:
        """List feedback records."""
        return self.get("/api/v1/feedback", params=params)

    def get_routing_accuracy(self, days: int = 30) -> dict[str, Any]:
        """Get routing accuracy statistics."""
        return self.get("/api/v1/feedback/accuracy", params={"days": days})

    def create_pattern(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create a routing pattern."""
        return self.post("/api/v1/patterns", json=data)

    def list_patterns(self, **params: Any) -> dict[str, Any]:
        """List routing patterns."""
        return self.get("/api/v1/patterns", params=params)

    def get_pattern(self, pattern_id: str) -> dict[str, Any]:
        """Get pattern by ID."""
        return self.get(f"/api/v1/patterns/{pattern_id}")

    def update_pattern(self, pattern_id: str, data: dict[str, Any]) -> dict[str, Any]:
        """Update pattern."""
        return self.patch(f"/api/v1/patterns/{pattern_id}", json=data)

    def delete_pattern(self, pattern_id: str) -> None:
        """Delete pattern."""
        return self.delete(f"/api/v1/patterns/{pattern_id}")

    def match_patterns(self, **params: Any) -> list[dict[str, Any]]:
        """Find patterns matching criteria."""
        return self.post("/api/v1/patterns/match", params=params)

    def get_learning_statistics(self) -> dict[str, Any]:
        """Get overall learning statistics."""
        return self.get("/api/v1/learning/statistics")

    def run_consolidation(self, days: int = 7) -> dict[str, Any]:
        """Run pattern consolidation."""
        return self.post("/api/v1/learning/consolidate", params={"days": days})
