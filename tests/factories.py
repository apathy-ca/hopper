"""
Factory pattern for generating test data.

Provides factories for creating realistic test instances of:
- Tasks
- Projects
- Hopper Instances
- Routing Decisions
- Task Feedback
- External Mappings

Usage:
    task = TaskFactory.create(title="Custom title")
    tasks = TaskFactory.create_batch(5, project="hopper")
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

# Import models (will be available after integration)
try:
    from hopper.models.external_mapping import ExternalMapping
    from hopper.models.hopper_instance import HopperInstance
    from hopper.models.project import Project
    from hopper.models.routing_decision import RoutingDecision
    from hopper.models.task import Task
    from hopper.models.task_feedback import TaskFeedback
except ImportError:
    # Models not yet integrated, define mock classes
    Task = None
    Project = None
    HopperInstance = None
    RoutingDecision = None
    TaskFeedback = None
    ExternalMapping = None


class BaseFactory:
    """
    Base factory class with common functionality.
    """

    model = None
    _counter = 0

    @classmethod
    def _get_sequence(cls) -> int:
        """Get the next sequence number."""
        cls._counter += 1
        return cls._counter

    @classmethod
    def _generate_id(cls, prefix: str) -> str:
        """Generate a unique ID with prefix."""
        return f"{prefix}-{uuid.uuid4().hex[:8]}"

    @classmethod
    def build(cls, **kwargs) -> Any:
        """
        Build an instance without persisting to database.

        Args:
            **kwargs: Override default attributes

        Returns:
            Model instance (not persisted)
        """
        if cls.model is None:
            raise NotImplementedError("Model not set for factory")

        # Get default attributes
        attributes = cls._get_defaults()

        # Override with provided kwargs
        attributes.update(kwargs)

        # Create instance
        return cls.model(**attributes)

    @classmethod
    def create(cls, session: Session | None = None, **kwargs) -> Any:
        """
        Create and persist an instance to the database.

        Args:
            session: SQLAlchemy session (optional)
            **kwargs: Override default attributes

        Returns:
            Persisted model instance
        """
        instance = cls.build(**kwargs)

        if session:
            session.add(instance)
            session.commit()
            session.refresh(instance)

        return instance

    @classmethod
    def create_batch(cls, size: int, session: Session | None = None, **kwargs) -> list[Any]:
        """
        Create and persist multiple instances.

        Args:
            size: Number of instances to create
            session: SQLAlchemy session (optional)
            **kwargs: Common attributes for all instances

        Returns:
            List of persisted model instances
        """
        instances = []
        for i in range(size):
            # Add sequence number to make instances unique
            instance_kwargs = kwargs.copy()
            if "title" in instance_kwargs:
                instance_kwargs["title"] = f"{instance_kwargs['title']} {i+1}"

            instance = cls.create(session=session, **instance_kwargs)
            instances.append(instance)

        return instances

    @classmethod
    def _get_defaults(cls) -> dict[str, Any]:
        """Get default attributes for the model. Override in subclasses."""
        return {}


class TaskFactory(BaseFactory):
    """
    Factory for creating Task instances.
    """

    model = Task

    @classmethod
    def _get_defaults(cls) -> dict[str, Any]:
        seq = cls._get_sequence()
        return {
            "id": cls._generate_id("task"),
            "title": f"Test Task {seq}",
            "description": f"This is a test task created by TaskFactory (sequence {seq})",
            "project": "test-project",
            "status": "pending",
            "priority": "medium",
            "requester": "test-user",
            "owner": None,
            "source": "test",
            "tags": {"test": True, "automated": True},
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }

    @classmethod
    def create_pending(cls, session: Session | None = None, **kwargs) -> Task:
        """Create a task with pending status."""
        return cls.create(session=session, status="pending", **kwargs)

    @classmethod
    def create_routed(cls, session: Session | None = None, **kwargs) -> Task:
        """Create a task with routed status."""
        return cls.create(session=session, status="routed", **kwargs)

    @classmethod
    def create_in_progress(cls, session: Session | None = None, **kwargs) -> Task:
        """Create a task with in_progress status."""
        return cls.create(session=session, status="in_progress", **kwargs)

    @classmethod
    def create_completed(cls, session: Session | None = None, **kwargs) -> Task:
        """Create a task with completed status."""
        return cls.create(session=session, status="completed", **kwargs)

    @classmethod
    def create_with_high_priority(cls, session: Session | None = None, **kwargs) -> Task:
        """Create a task with high priority."""
        return cls.create(session=session, priority="high", **kwargs)

    @classmethod
    def create_with_dependencies(cls, session: Session | None = None, **kwargs) -> Task:
        """Create a task with dependencies."""
        depends_on = kwargs.pop("depends_on", ["task-dep-1", "task-dep-2"])
        return cls.create(session=session, depends_on={"task_ids": depends_on}, **kwargs)


class ProjectFactory(BaseFactory):
    """
    Factory for creating Project instances.
    """

    model = Project

    @classmethod
    def _get_defaults(cls) -> dict[str, Any]:
        seq = cls._get_sequence()
        slug = f"test-project-{seq}"
        return {
            "id": cls._generate_id("proj"),
            "name": f"Test Project {seq}",
            "slug": slug,
            "description": f"A test project created by ProjectFactory (sequence {seq})",
            "configuration": {
                "routing_rules": ["keyword_match", "tag_match"],
                "default_priority": "medium",
                "auto_routing": True,
            },
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }

    @classmethod
    def create_with_custom_config(
        cls, config: dict[str, Any], session: Session | None = None, **kwargs
    ) -> Project:
        """Create a project with custom configuration."""
        return cls.create(session=session, configuration=config, **kwargs)


class HopperInstanceFactory(BaseFactory):
    """
    Factory for creating HopperInstance instances.
    """

    model = HopperInstance

    @classmethod
    def _get_defaults(cls) -> dict[str, Any]:
        seq = cls._get_sequence()
        return {
            "id": cls._generate_id("inst"),
            "name": f"Test Instance {seq}",
            "scope": "global",
            "configuration": {
                "routing_engine": "rules",
                "llm_fallback": True,
                "confidence_threshold": 0.7,
            },
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }

    @classmethod
    def create_global(cls, session: Session | None = None, **kwargs) -> HopperInstance:
        """Create a global-scope instance."""
        return cls.create(session=session, scope="global", **kwargs)

    @classmethod
    def create_project_scoped(cls, session: Session | None = None, **kwargs) -> HopperInstance:
        """Create a project-scoped instance."""
        return cls.create(session=session, scope="project", **kwargs)

    @classmethod
    def create_orchestration_scoped(
        cls, session: Session | None = None, **kwargs
    ) -> HopperInstance:
        """Create an orchestration-scoped instance."""
        return cls.create(session=session, scope="orchestration", **kwargs)


class RoutingDecisionFactory(BaseFactory):
    """
    Factory for creating RoutingDecision instances.
    """

    model = RoutingDecision

    @classmethod
    def _get_defaults(cls) -> dict[str, Any]:
        return {
            "id": cls._generate_id("decision"),
            "task_id": cls._generate_id("task"),
            "destination": "default-project",
            "strategy": "rules",
            "confidence": 0.85,
            "reasoning": "Matched based on keyword analysis",
            "metadata": {
                "matched_rules": ["keyword_match"],
                "execution_time_ms": 50,
            },
            "created_at": datetime.utcnow(),
        }

    @classmethod
    def create_rules_based(cls, session: Session | None = None, **kwargs) -> RoutingDecision:
        """Create a rules-based routing decision."""
        return cls.create(session=session, strategy="rules", **kwargs)

    @classmethod
    def create_llm_based(cls, session: Session | None = None, **kwargs) -> RoutingDecision:
        """Create an LLM-based routing decision."""
        return cls.create(
            session=session,
            strategy="llm",
            confidence=0.75,
            reasoning="LLM analysis suggests this routing",
            **kwargs,
        )

    @classmethod
    def create_sage_based(cls, session: Session | None = None, **kwargs) -> RoutingDecision:
        """Create a SAGE-based routing decision."""
        return cls.create(
            session=session,
            strategy="sage",
            confidence=0.95,
            reasoning="SAGE memory system found historical patterns",
            **kwargs,
        )


class TaskFeedbackFactory(BaseFactory):
    """
    Factory for creating TaskFeedback instances.
    """

    model = TaskFeedback

    @classmethod
    def _get_defaults(cls) -> dict[str, Any]:
        return {
            "id": cls._generate_id("feedback"),
            "task_id": cls._generate_id("task"),
            "routing_correct": True,
            "confidence_rating": 4,
            "comments": "The routing was appropriate for this task",
            "suggested_destination": None,
            "created_at": datetime.utcnow(),
        }

    @classmethod
    def create_positive(cls, session: Session | None = None, **kwargs) -> TaskFeedback:
        """Create positive feedback."""
        return cls.create(
            session=session,
            routing_correct=True,
            confidence_rating=5,
            comments="Perfect routing!",
            **kwargs,
        )

    @classmethod
    def create_negative(cls, session: Session | None = None, **kwargs) -> TaskFeedback:
        """Create negative feedback with correction."""
        return cls.create(
            session=session,
            routing_correct=False,
            confidence_rating=2,
            comments="Should have been routed elsewhere",
            suggested_destination=kwargs.pop("suggested_destination", "other-project"),
            **kwargs,
        )


class ExternalMappingFactory(BaseFactory):
    """
    Factory for creating ExternalMapping instances.
    """

    model = ExternalMapping

    @classmethod
    def _get_defaults(cls) -> dict[str, Any]:
        seq = cls._get_sequence()
        return {
            "id": cls._generate_id("mapping"),
            "task_id": cls._generate_id("task"),
            "platform": "github",
            "external_id": f"issue-{seq}",
            "external_url": f"https://github.com/test/repo/issues/{seq}",
            "metadata": {
                "repository": "test/repo",
                "issue_number": seq,
            },
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }

    @classmethod
    def create_github_mapping(cls, session: Session | None = None, **kwargs) -> ExternalMapping:
        """Create a GitHub issue mapping."""
        return cls.create(session=session, platform="github", **kwargs)

    @classmethod
    def create_gitlab_mapping(cls, session: Session | None = None, **kwargs) -> ExternalMapping:
        """Create a GitLab issue mapping."""
        seq = cls._get_sequence()
        return cls.create(
            session=session,
            platform="gitlab",
            external_id=f"issue-{seq}",
            external_url=f"https://gitlab.com/test/repo/-/issues/{seq}",
            **kwargs,
        )


# ============================================================================
# Utility Functions
# ============================================================================


def create_task_with_routing(
    session: Session | None = None,
    task_kwargs: dict[str, Any] | None = None,
    decision_kwargs: dict[str, Any] | None = None,
) -> tuple:
    """
    Create a task with associated routing decision.

    Args:
        session: SQLAlchemy session
        task_kwargs: Keyword arguments for task creation
        decision_kwargs: Keyword arguments for routing decision creation

    Returns:
        Tuple of (task, routing_decision)
    """
    task_kwargs = task_kwargs or {}
    decision_kwargs = decision_kwargs or {}

    # Create task
    task = TaskFactory.create(session=session, **task_kwargs)

    # Create routing decision linked to task
    decision_kwargs["task_id"] = task.id
    decision = RoutingDecisionFactory.create(session=session, **decision_kwargs)

    return task, decision


def create_task_with_feedback(
    session: Session | None = None,
    task_kwargs: dict[str, Any] | None = None,
    feedback_kwargs: dict[str, Any] | None = None,
) -> tuple:
    """
    Create a task with associated feedback.

    Args:
        session: SQLAlchemy session
        task_kwargs: Keyword arguments for task creation
        feedback_kwargs: Keyword arguments for feedback creation

    Returns:
        Tuple of (task, feedback)
    """
    task_kwargs = task_kwargs or {}
    feedback_kwargs = feedback_kwargs or {}

    # Create task
    task = TaskFactory.create(session=session, **task_kwargs)

    # Create feedback linked to task
    feedback_kwargs["task_id"] = task.id
    feedback = TaskFeedbackFactory.create(session=session, **feedback_kwargs)

    return task, feedback


def create_complete_task_workflow(session: Session | None = None, **kwargs) -> dict[str, Any]:
    """
    Create a complete task workflow with all related entities.

    Creates:
    - Task
    - Routing Decision
    - Task Feedback
    - External Mapping

    Returns:
        Dictionary with all created entities
    """
    # Create task
    task = TaskFactory.create(session=session, **kwargs)

    # Create routing decision
    decision = RoutingDecisionFactory.create(
        session=session, task_id=task.id, destination=kwargs.get("project", "default-project")
    )

    # Create feedback
    feedback = TaskFeedbackFactory.create(session=session, task_id=task.id, routing_correct=True)

    # Create external mapping
    mapping = ExternalMappingFactory.create(session=session, task_id=task.id)

    return {
        "task": task,
        "decision": decision,
        "feedback": feedback,
        "mapping": mapping,
    }
