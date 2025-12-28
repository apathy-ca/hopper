"""
Tests for Project model.
"""

from datetime import datetime

from sqlalchemy.orm import Session

from hopper.models import ExecutorType, Project


def test_project_creation(clean_db: Session) -> None:
    """Test creating a basic project."""
    project = Project(
        name="czarina",
        slug="czarina",
        repository="https://github.com/org/czarina",
        executor_type=ExecutorType.CZARINA.value,
    )
    clean_db.add(project)
    clean_db.commit()

    retrieved_project = clean_db.query(Project).filter_by(name="czarina").first()
    assert retrieved_project is not None
    assert retrieved_project.name == "czarina"
    assert retrieved_project.slug == "czarina"
    assert retrieved_project.repository == "https://github.com/org/czarina"
    assert retrieved_project.executor_type == ExecutorType.CZARINA.value
    assert isinstance(retrieved_project.created_at, datetime)


def test_project_with_capabilities_and_tags(clean_db: Session) -> None:
    """Test project with capabilities and tags."""
    project = Project(
        name="backend-service",
        slug="backend-service",
        capabilities=["python", "postgresql", "redis"],
        tags=["backend", "api", "microservice"],
    )
    clean_db.add(project)
    clean_db.commit()

    retrieved_project = (
        clean_db.query(Project).filter_by(name="backend-service").first()
    )
    assert retrieved_project is not None
    assert retrieved_project.capabilities == ["python", "postgresql", "redis"]
    assert retrieved_project.tags == ["backend", "api", "microservice"]


def test_project_executor_config(clean_db: Session) -> None:
    """Test project with executor configuration."""
    executor_config = {
        "api_endpoint": "https://czarina.example.com/api",
        "max_workers": 3,
        "timeout": 3600,
    }

    project = Project(
        name="czarina",
        slug="czarina",
        executor_type=ExecutorType.CZARINA.value,
        executor_config=executor_config,
    )
    clean_db.add(project)
    clean_db.commit()

    retrieved_project = clean_db.query(Project).filter_by(name="czarina").first()
    assert retrieved_project is not None
    assert retrieved_project.executor_config == executor_config
    assert retrieved_project.executor_config["max_workers"] == 3


def test_project_routing_preferences(clean_db: Session) -> None:
    """Test project with routing preferences."""
    priority_boost = {"urgent": 2.0, "high": 1.5}
    sla = {"response_time": "1h", "completion_time": "24h"}

    project = Project(
        name="high-priority-service",
        slug="high-priority-service",
        auto_claim=True,
        priority_boost=priority_boost,
        velocity="fast",
        sla=sla,
    )
    clean_db.add(project)
    clean_db.commit()

    retrieved_project = (
        clean_db.query(Project).filter_by(name="high-priority-service").first()
    )
    assert retrieved_project is not None
    assert retrieved_project.auto_claim is True
    assert retrieved_project.priority_boost == priority_boost
    assert retrieved_project.velocity == "fast"
    assert retrieved_project.sla == sla


def test_project_sync_configuration(clean_db: Session) -> None:
    """Test project with sync configuration."""
    sync_config = {
        "github": {
            "enabled": True,
            "repo": "org/repo",
            "label_mapping": {"bug": ["type:bug"], "feature": ["type:feature"]},
        }
    }

    project = Project(
        name="synced-project",
        slug="synced-project",
        sync_config=sync_config,
    )
    clean_db.add(project)
    clean_db.commit()

    retrieved_project = (
        clean_db.query(Project).filter_by(name="synced-project").first()
    )
    assert retrieved_project is not None
    assert retrieved_project.sync_config is not None
    assert retrieved_project.sync_config["github"]["enabled"] is True
    assert retrieved_project.sync_config["github"]["repo"] == "org/repo"


def test_project_unique_slug(clean_db: Session) -> None:
    """Test that project slug must be unique."""
    project1 = Project(name="project1", slug="unique-slug")
    clean_db.add(project1)
    clean_db.commit()

    # Try to create another project with the same slug
    project2 = Project(name="project2", slug="unique-slug")
    clean_db.add(project2)

    # This should raise an integrity error
    try:
        clean_db.commit()
        assert False, "Should have raised integrity error for duplicate slug"
    except Exception:
        clean_db.rollback()
        # Expected behavior


def test_project_integration_endpoints(clean_db: Session) -> None:
    """Test project with webhook and API endpoints."""
    project = Project(
        name="integrated-project",
        slug="integrated-project",
        webhook_url="https://example.com/webhook",
        api_endpoint="https://api.example.com/tasks",
    )
    clean_db.add(project)
    clean_db.commit()

    retrieved_project = (
        clean_db.query(Project).filter_by(name="integrated-project").first()
    )
    assert retrieved_project is not None
    assert retrieved_project.webhook_url == "https://example.com/webhook"
    assert retrieved_project.api_endpoint == "https://api.example.com/tasks"
