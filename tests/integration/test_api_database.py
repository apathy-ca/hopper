"""
Integration tests for API with database layer.

Tests API endpoints with real database operations including:
- Task CRUD operations
- Project CRUD operations
- Instance CRUD operations
- Data persistence
- Transaction handling
- Concurrent requests
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.factories import (
    TaskFactory,
    ProjectFactory,
    HopperInstanceFactory,
)
from tests.utils import (
    assert_response_success,
    assert_response_error,
    assert_timestamp_recent,
    validate_task_schema,
    validate_project_schema,
)


@pytest.mark.integration
class TestTaskCRUDAPI:
    """Test task CRUD operations through API with database persistence."""

    def test_create_task(self, api_client: TestClient, db_session: Session):
        """Test creating a task via API and verifying database persistence."""
        task_data = {
            "title": "Test API Task",
            "description": "Task created via API",
            "project": "hopper",
            "priority": "high",
            "tags": {"api": True, "test": True},
        }

        # Create task via API
        response = api_client.post("/api/v1/tasks", json=task_data)
        assert_response_success(response, 201)

        # Verify response
        response_data = response.json()
        validate_task_schema(response_data)
        assert response_data["title"] == task_data["title"]
        assert response_data["description"] == task_data["description"]
        assert response_data["project"] == task_data["project"]
        assert response_data["priority"] == task_data["priority"]
        assert response_data["status"] == "pending"  # Default status

        # Verify database persistence
        task_id = response_data["id"]
        from hopper.models.task import Task
        db_task = db_session.query(Task).filter(Task.id == task_id).first()
        assert db_task is not None
        assert db_task.title == task_data["title"]
        assert db_task.project == task_data["project"]

    def test_get_task(self, api_client: TestClient, db_session: Session):
        """Test retrieving a task via API from database."""
        # Create task in database
        task = TaskFactory.create(
            session=db_session,
            title="Test Get Task",
            project="hopper"
        )

        # Retrieve via API
        response = api_client.get(f"/api/v1/tasks/{task.id}")
        assert_response_success(response)

        # Verify response
        response_data = response.json()
        assert response_data["id"] == task.id
        assert response_data["title"] == task.title
        assert response_data["project"] == task.project

    def test_get_nonexistent_task(self, api_client: TestClient):
        """Test retrieving a non-existent task returns 404."""
        response = api_client.get("/api/v1/tasks/nonexistent-task-id")
        assert_response_error(response, 404, "not found")

    def test_list_tasks(self, api_client: TestClient, db_session: Session):
        """Test listing tasks via API from database."""
        # Create multiple tasks in database
        tasks = TaskFactory.create_batch(5, session=db_session, project="hopper")

        # List via API
        response = api_client.get("/api/v1/tasks")
        assert_response_success(response)

        # Verify response
        response_data = response.json()
        assert "items" in response_data
        assert len(response_data["items"]) >= 5  # At least the tasks we created

        # Verify pagination metadata
        assert "page" in response_data
        assert "page_size" in response_data
        assert "total" in response_data

    def test_list_tasks_with_filters(self, api_client: TestClient, db_session: Session):
        """Test listing tasks with filters applied."""
        # Create tasks with different projects
        TaskFactory.create_batch(3, session=db_session, project="hopper")
        TaskFactory.create_batch(2, session=db_session, project="czarina")

        # Filter by project
        response = api_client.get("/api/v1/tasks?project=hopper")
        assert_response_success(response)

        response_data = response.json()
        assert len([t for t in response_data["items"] if t["project"] == "hopper"]) >= 3

    def test_list_tasks_pagination(self, api_client: TestClient, db_session: Session):
        """Test task listing pagination."""
        # Create many tasks
        TaskFactory.create_batch(25, session=db_session)

        # Get first page
        response = api_client.get("/api/v1/tasks?page=1&page_size=10")
        assert_response_success(response)

        response_data = response.json()
        assert len(response_data["items"]) == 10
        assert response_data["page"] == 1
        assert response_data["page_size"] == 10

        # Get second page
        response = api_client.get("/api/v1/tasks?page=2&page_size=10")
        assert_response_success(response)

        response_data = response.json()
        assert len(response_data["items"]) == 10
        assert response_data["page"] == 2

    def test_update_task(self, api_client: TestClient, db_session: Session):
        """Test updating a task via API and verifying database changes."""
        # Create task
        task = TaskFactory.create(
            session=db_session,
            title="Original Title",
            status="pending"
        )

        # Update via API
        update_data = {
            "title": "Updated Title",
            "status": "in_progress",
            "priority": "high"
        }
        response = api_client.put(f"/api/v1/tasks/{task.id}", json=update_data)
        assert_response_success(response)

        # Verify response
        response_data = response.json()
        assert response_data["title"] == update_data["title"]
        assert response_data["status"] == update_data["status"]
        assert response_data["priority"] == update_data["priority"]

        # Verify database persistence
        db_session.refresh(task)
        assert task.title == update_data["title"]
        assert task.status == update_data["status"]
        assert task.priority == update_data["priority"]

    def test_update_nonexistent_task(self, api_client: TestClient):
        """Test updating a non-existent task returns 404."""
        update_data = {"title": "Updated"}
        response = api_client.put("/api/v1/tasks/nonexistent", json=update_data)
        assert_response_error(response, 404)

    def test_delete_task(self, api_client: TestClient, db_session: Session):
        """Test deleting (soft delete) a task via API."""
        # Create task
        task = TaskFactory.create(session=db_session)

        # Delete via API
        response = api_client.delete(f"/api/v1/tasks/{task.id}")
        assert_response_success(response, 204)

        # Verify soft delete (task still exists but marked as deleted or archived)
        db_session.refresh(task)
        assert task.status == "archived"  # Assuming soft delete sets status to archived

    def test_update_task_status(self, api_client: TestClient, db_session: Session):
        """Test updating task status via dedicated endpoint."""
        task = TaskFactory.create(session=db_session, status="pending")

        # Update status
        response = api_client.post(
            f"/api/v1/tasks/{task.id}/status",
            json={"status": "completed"}
        )
        assert_response_success(response)

        # Verify database
        db_session.refresh(task)
        assert task.status == "completed"


@pytest.mark.integration
class TestProjectCRUDAPI:
    """Test project CRUD operations through API with database persistence."""

    def test_create_project(self, api_client: TestClient, db_session: Session):
        """Test creating a project via API."""
        project_data = {
            "name": "Test Project",
            "slug": "test-project",
            "description": "A test project",
            "configuration": {
                "routing_rules": ["keyword_match"],
                "default_priority": "medium"
            }
        }

        response = api_client.post("/api/v1/projects", json=project_data)
        assert_response_success(response, 201)

        response_data = response.json()
        validate_project_schema(response_data)
        assert response_data["name"] == project_data["name"]
        assert response_data["slug"] == project_data["slug"]

        # Verify database
        from hopper.models.project import Project
        db_project = db_session.query(Project).filter(
            Project.slug == project_data["slug"]
        ).first()
        assert db_project is not None
        assert db_project.name == project_data["name"]

    def test_get_project(self, api_client: TestClient, db_session: Session):
        """Test retrieving a project via API."""
        project = ProjectFactory.create(session=db_session, name="Test Project")

        response = api_client.get(f"/api/v1/projects/{project.id}")
        assert_response_success(response)

        response_data = response.json()
        assert response_data["id"] == project.id
        assert response_data["name"] == project.name

    def test_list_projects(self, api_client: TestClient, db_session: Session):
        """Test listing projects via API."""
        ProjectFactory.create_batch(3, session=db_session)

        response = api_client.get("/api/v1/projects")
        assert_response_success(response)

        response_data = response.json()
        assert len(response_data) >= 3  # At least the projects we created

    def test_update_project(self, api_client: TestClient, db_session: Session):
        """Test updating a project via API."""
        project = ProjectFactory.create(session=db_session, name="Original Name")

        update_data = {"name": "Updated Name"}
        response = api_client.put(f"/api/v1/projects/{project.id}", json=update_data)
        assert_response_success(response)

        # Verify database
        db_session.refresh(project)
        assert project.name == update_data["name"]

    def test_delete_project(self, api_client: TestClient, db_session: Session):
        """Test deleting a project via API."""
        project = ProjectFactory.create(session=db_session)

        response = api_client.delete(f"/api/v1/projects/{project.id}")
        assert_response_success(response, 204)

        # Verify deletion
        from hopper.models.project import Project
        db_project = db_session.query(Project).filter(
            Project.id == project.id
        ).first()
        assert db_project is None

    def test_get_project_tasks(self, api_client: TestClient, db_session: Session):
        """Test getting all tasks for a project."""
        project = ProjectFactory.create(session=db_session, slug="hopper")
        TaskFactory.create_batch(5, session=db_session, project="hopper")
        TaskFactory.create_batch(2, session=db_session, project="other")

        response = api_client.get(f"/api/v1/projects/{project.id}/tasks")
        assert_response_success(response)

        response_data = response.json()
        assert len(response_data) >= 5
        for task in response_data:
            assert task["project"] == "hopper"


@pytest.mark.integration
class TestInstanceCRUDAPI:
    """Test Hopper instance CRUD operations through API."""

    def test_create_instance(self, api_client: TestClient, db_session: Session):
        """Test creating a Hopper instance via API."""
        instance_data = {
            "name": "Test Instance",
            "scope": "global",
            "configuration": {
                "routing_engine": "rules",
                "llm_fallback": True
            }
        }

        response = api_client.post("/api/v1/instances", json=instance_data)
        assert_response_success(response, 201)

        response_data = response.json()
        assert response_data["name"] == instance_data["name"]
        assert response_data["scope"] == instance_data["scope"]

    def test_get_instance(self, api_client: TestClient, db_session: Session):
        """Test retrieving an instance via API."""
        instance = HopperInstanceFactory.create(session=db_session)

        response = api_client.get(f"/api/v1/instances/{instance.id}")
        assert_response_success(response)

        response_data = response.json()
        assert response_data["id"] == instance.id
        assert response_data["name"] == instance.name

    def test_list_instances(self, api_client: TestClient, db_session: Session):
        """Test listing instances via API."""
        HopperInstanceFactory.create_batch(3, session=db_session)

        response = api_client.get("/api/v1/instances")
        assert_response_success(response)

        response_data = response.json()
        assert len(response_data) >= 3


@pytest.mark.integration
class TestDataPersistence:
    """Test data persistence and consistency across API operations."""

    def test_task_created_at_timestamp(self, api_client: TestClient, db_session: Session):
        """Test that created_at timestamp is set automatically."""
        task_data = {"title": "Test Task", "project": "hopper"}

        response = api_client.post("/api/v1/tasks", json=task_data)
        assert_response_success(response, 201)

        response_data = response.json()
        assert "created_at" in response_data
        # Timestamp should be recent (within last 5 seconds)
        from datetime import datetime
        created_at = datetime.fromisoformat(response_data["created_at"].replace("Z", "+00:00"))
        assert_timestamp_recent(created_at, seconds=5)

    def test_task_updated_at_timestamp(self, api_client: TestClient, db_session: Session):
        """Test that updated_at timestamp changes on update."""
        # Create task
        task = TaskFactory.create(session=db_session)
        original_updated_at = task.updated_at

        # Update task
        import time
        time.sleep(1)  # Ensure timestamp difference
        response = api_client.put(
            f"/api/v1/tasks/{task.id}",
            json={"title": "Updated Title"}
        )
        assert_response_success(response)

        # Verify updated_at changed
        db_session.refresh(task)
        assert task.updated_at > original_updated_at

    def test_concurrent_task_creation(self, api_client: TestClient, db_session: Session):
        """Test handling concurrent task creation requests."""
        import concurrent.futures

        def create_task(i):
            task_data = {"title": f"Concurrent Task {i}", "project": "hopper"}
            return api_client.post("/api/v1/tasks", json=task_data)

        # Create 10 tasks concurrently
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(create_task, i) for i in range(10)]
            responses = [f.result() for f in futures]

        # All requests should succeed
        for response in responses:
            assert_response_success(response, 201)

        # Verify all tasks were created with unique IDs
        task_ids = [r.json()["id"] for r in responses]
        assert len(task_ids) == len(set(task_ids))  # All IDs are unique


@pytest.mark.integration
class TestTransactionHandling:
    """Test transaction handling and rollback behavior."""

    def test_create_task_with_invalid_data_rolls_back(
        self, api_client: TestClient, db_session: Session
    ):
        """Test that invalid task creation doesn't persist partial data."""
        # Count tasks before
        from hopper.models.task import Task
        count_before = db_session.query(Task).count()

        # Attempt to create task with invalid data
        invalid_data = {
            "title": "",  # Empty title should fail validation
            "project": "hopper",
            "priority": "invalid_priority"  # Invalid priority
        }

        response = api_client.post("/api/v1/tasks", json=invalid_data)
        assert response.status_code >= 400  # Should fail

        # Verify no tasks were created
        count_after = db_session.query(Task).count()
        assert count_after == count_before

    def test_update_task_with_invalid_status_rolls_back(
        self, api_client: TestClient, db_session: Session
    ):
        """Test that invalid update doesn't modify database."""
        task = TaskFactory.create(session=db_session, title="Original")

        # Attempt invalid update
        response = api_client.put(
            f"/api/v1/tasks/{task.id}",
            json={"status": "invalid_status"}
        )
        assert response.status_code >= 400

        # Verify task unchanged
        db_session.refresh(task)
        assert task.title == "Original"


@pytest.mark.integration
@pytest.mark.slow
class TestLargeDatasets:
    """Test API performance with large datasets."""

    def test_list_many_tasks(self, api_client: TestClient, db_session: Session):
        """Test listing tasks when many exist in database."""
        # Create 100 tasks
        TaskFactory.create_batch(100, session=db_session)

        # List with pagination
        response = api_client.get("/api/v1/tasks?page=1&page_size=50")
        assert_response_success(response)

        response_data = response.json()
        assert len(response_data["items"]) == 50
        assert response_data["total"] >= 100

    def test_search_tasks_performance(self, api_client: TestClient, db_session: Session):
        """Test task search performance with large dataset."""
        # Create tasks with specific keywords
        for i in range(50):
            TaskFactory.create(
                session=db_session,
                title=f"Authentication task {i}",
                tags={"auth": True}
            )

        # Search for tasks
        response = api_client.get("/api/v1/tasks/search?q=authentication")
        assert_response_success(response)

        # Should return results quickly
        assert "X-Process-Time" in response.headers
        process_time = float(response.headers["X-Process-Time"])
        assert process_time < 1.0  # Should complete in under 1 second
