# Knowledge Base: scope-behaviors

Custom knowledge for the Scope Behaviors worker, extracted from agent-knowledge library.

## Strategy Pattern for Behaviors

### Abstract Base Behavior

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Protocol

class TaskAction(str, Enum):
    """Actions a scope can take on a task."""
    DELEGATE = "delegate"      # Send to child instance
    EXECUTE = "execute"        # Handle directly
    QUEUE = "queue"           # Add to local queue
    ESCALATE = "escalate"     # Return to parent
    REJECT = "reject"         # Cannot handle

@dataclass
class RoutingDecision:
    """Result of routing decision."""
    action: TaskAction
    target_instance: HopperInstance | None = None
    reason: str = ""

class ScopeBehavior(ABC):
    """Abstract base for scope-specific behaviors."""

    @abstractmethod
    async def handle_incoming_task(
        self,
        task: Task,
        instance: HopperInstance,
    ) -> RoutingDecision:
        """Decide how to handle an incoming task.

        Args:
            task: The incoming task
            instance: The receiving instance

        Returns:
            Routing decision with action and optional target
        """
        pass

    @abstractmethod
    async def should_delegate(
        self,
        task: Task,
        instance: HopperInstance,
    ) -> bool:
        """Determine if task should be delegated."""
        pass

    @abstractmethod
    async def find_delegation_target(
        self,
        task: Task,
        instance: HopperInstance,
    ) -> HopperInstance | None:
        """Find appropriate delegation target."""
        pass

    @abstractmethod
    async def on_task_completed(
        self,
        task: Task,
        instance: HopperInstance,
    ) -> None:
        """Handle task completion at this scope."""
        pass

    @abstractmethod
    async def get_task_queue(
        self,
        instance: HopperInstance,
    ) -> list[Task]:
        """Get pending tasks for this instance."""
        pass
```

## Global Scope Implementation

```python
class GlobalScopeBehavior(ScopeBehavior):
    """Behavior for Global Hopper instances.

    Global instances are strategic routers - they never execute tasks
    directly, but route them to appropriate Project instances.
    """

    def __init__(self, db: AsyncSession, config: GlobalConfig | None = None):
        self.db = db
        self.config = config or GlobalConfig()
        self.instance_repo = HopperInstanceRepository()

    async def handle_incoming_task(
        self,
        task: Task,
        instance: HopperInstance,
    ) -> RoutingDecision:
        """Global always delegates to Project level."""
        target = await self.find_delegation_target(task, instance)

        if target:
            return RoutingDecision(
                action=TaskAction.DELEGATE,
                target_instance=target,
                reason=f"Routing to project: {target.name}"
            )

        # No suitable project found
        if self.config.auto_create_projects:
            target = await self._create_project_for_task(task, instance)
            return RoutingDecision(
                action=TaskAction.DELEGATE,
                target_instance=target,
                reason="Created new project for task"
            )

        return RoutingDecision(
            action=TaskAction.REJECT,
            reason="No suitable project found and auto-create disabled"
        )

    async def should_delegate(
        self,
        task: Task,
        instance: HopperInstance,
    ) -> bool:
        """Global ALWAYS delegates - never executes directly."""
        return True

    async def find_delegation_target(
        self,
        task: Task,
        instance: HopperInstance,
    ) -> HopperInstance | None:
        """Find appropriate Project instance.

        Strategy:
        1. Explicit project assignment in task metadata
        2. Tag matching with project capabilities
        3. Keyword matching in task content
        4. Load balancing (least busy project)
        """
        # 1. Check explicit assignment
        if task.metadata and task.metadata.get("project_id"):
            return await self.instance_repo.get_by_id(
                self.db, task.metadata["project_id"]
            )

        # Get all running Project instances (children of global)
        children = await self.instance_repo.get_children(self.db, instance.id)
        projects = [
            c for c in children
            if c.scope == HopperScope.PROJECT and c.status == InstanceStatus.RUNNING
        ]

        if not projects:
            return None

        # 2. Tag matching
        if task.tags:
            for project in projects:
                capabilities = project.config.get("capabilities", [])
                if any(tag in capabilities for tag in task.tags):
                    return project

        # 3. Keyword matching (using routing engine)
        # ... integrate with existing routing intelligence ...

        # 4. Load balancing fallback
        return await self._select_least_busy(projects)

    async def _select_least_busy(
        self,
        projects: list[HopperInstance],
    ) -> HopperInstance:
        """Select project with fewest active tasks."""
        project_loads = []
        for project in projects:
            count = await self._get_task_count(project)
            project_loads.append((project, count))

        return min(project_loads, key=lambda x: x[1])[0]
```

## Project Scope Implementation

```python
class ProjectScopeBehavior(ScopeBehavior):
    """Behavior for Project Hopper instances.

    Project instances make tactical decisions - they can handle
    simple tasks directly or delegate to Orchestration for complex work.
    """

    COMPLEXITY_THRESHOLD = 3  # Tasks with complexity > this get delegated

    async def handle_incoming_task(
        self,
        task: Task,
        instance: HopperInstance,
    ) -> RoutingDecision:
        """Decide between direct handling and orchestration."""
        if await self.should_delegate(task, instance):
            target = await self.find_delegation_target(task, instance)
            if target:
                return RoutingDecision(
                    action=TaskAction.DELEGATE,
                    target_instance=target,
                    reason="Task complexity requires orchestration"
                )

            # Create new orchestration if needed
            if self.config.auto_create_orchestrations:
                target = await self._create_orchestration(task, instance)
                return RoutingDecision(
                    action=TaskAction.DELEGATE,
                    target_instance=target,
                    reason="Created new orchestration for task"
                )

        # Handle directly
        return RoutingDecision(
            action=TaskAction.EXECUTE,
            reason="Simple task - handling directly"
        )

    async def should_delegate(
        self,
        task: Task,
        instance: HopperInstance,
    ) -> bool:
        """Decide if task needs orchestration.

        Criteria:
        - Task complexity score
        - Task type (automatable?)
        - Task decomposability
        """
        complexity = self._calculate_complexity(task)
        return complexity > self.COMPLEXITY_THRESHOLD

    def _calculate_complexity(self, task: Task) -> int:
        """Calculate task complexity score."""
        score = 0

        # Base complexity from estimated duration
        if task.estimated_duration:
            score += min(task.estimated_duration // 60, 5)  # Hours

        # Complexity from subtasks
        if task.metadata and task.metadata.get("subtasks"):
            score += len(task.metadata["subtasks"])

        # Complexity from tags
        complex_tags = ["multi-step", "automation", "complex", "czarina"]
        if task.tags and any(t in complex_tags for t in task.tags):
            score += 2

        return score
```

## Orchestration Scope Implementation

```python
class OrchestrationScopeBehavior(ScopeBehavior):
    """Behavior for Orchestration Hopper instances.

    Orchestration instances are execution engines - they manage
    worker queues and execute tasks. They never delegate further.
    """

    async def handle_incoming_task(
        self,
        task: Task,
        instance: HopperInstance,
    ) -> RoutingDecision:
        """Orchestration always queues for execution."""
        return RoutingDecision(
            action=TaskAction.QUEUE,
            reason="Added to execution queue"
        )

    async def should_delegate(
        self,
        task: Task,
        instance: HopperInstance,
    ) -> bool:
        """Orchestration never delegates."""
        return False

    async def find_delegation_target(
        self,
        task: Task,
        instance: HopperInstance,
    ) -> HopperInstance | None:
        """No delegation targets for Orchestration."""
        return None

    async def on_task_completed(
        self,
        task: Task,
        instance: HopperInstance,
    ) -> None:
        """Report completion to parent Project."""
        # Trigger completion bubbling
        bubbler = CompletionBubbler(self.db)
        await bubbler.bubble_completion(task)

    async def get_task_queue(
        self,
        instance: HopperInstance,
    ) -> list[Task]:
        """Get pending tasks for this orchestration."""
        return await self.task_repo.get_by_instance(
            self.db,
            instance_id=instance.id,
            status=TaskStatus.PENDING,
        )
```

## Behavior Factory Pattern

```python
from typing import Type

class ScopeBehaviorFactory:
    """Factory for creating scope behaviors."""

    _registry: dict[HopperScope, Type[ScopeBehavior]] = {
        HopperScope.GLOBAL: GlobalScopeBehavior,
        HopperScope.PROJECT: ProjectScopeBehavior,
        HopperScope.ORCHESTRATION: OrchestrationScopeBehavior,
    }

    @classmethod
    def get_behavior_for_scope(
        cls,
        scope: HopperScope,
        db: AsyncSession,
    ) -> ScopeBehavior:
        """Get behavior class for scope."""
        behavior_class = cls._registry.get(scope)
        if not behavior_class:
            raise ValueError(f"No behavior registered for scope: {scope}")
        return behavior_class(db)

    @classmethod
    def get_behavior_for_instance(
        cls,
        instance: HopperInstance,
        db: AsyncSession,
    ) -> ScopeBehavior:
        """Get behavior for instance."""
        return cls.get_behavior_for_scope(instance.scope, db)

    @classmethod
    def register_behavior(
        cls,
        scope: HopperScope,
        behavior_class: Type[ScopeBehavior],
    ) -> None:
        """Register custom behavior for scope."""
        cls._registry[scope] = behavior_class
```

## Configuration Pattern

### YAML Configuration

```yaml
# config/scope_behaviors.yaml
global:
  routing_strategy: "tag_first"  # tag_first, keyword, round_robin
  fallback_strategy: "round_robin"
  auto_create_projects: false
  max_projects: 10

project:
  complexity_threshold: 3
  orchestration_threshold: 5  # Max direct tasks before orchestration
  auto_create_orchestrations: true
  max_orchestrations_per_project: 5

orchestration:
  max_concurrent_tasks: 10
  retry_on_failure: true
  max_retries: 3
  worker_timeout_seconds: 300
```

### Config Loading

```python
import yaml
from pydantic import BaseModel

class GlobalConfig(BaseModel):
    routing_strategy: str = "tag_first"
    fallback_strategy: str = "round_robin"
    auto_create_projects: bool = False
    max_projects: int = 10

class ScopeBehaviorConfig(BaseModel):
    global_config: GlobalConfig
    project_config: ProjectConfig
    orchestration_config: OrchestrationConfig

    @classmethod
    def from_yaml(cls, path: str) -> "ScopeBehaviorConfig":
        with open(path) as f:
            data = yaml.safe_load(f)
        return cls(
            global_config=GlobalConfig(**data.get("global", {})),
            project_config=ProjectConfig(**data.get("project", {})),
            orchestration_config=OrchestrationConfig(**data.get("orchestration", {})),
        )
```

## Testing Patterns

```python
@pytest.mark.asyncio
async def test_global_routes_to_project(db, global_instance, project_instance):
    """Test Global correctly routes to Project."""
    behavior = GlobalScopeBehavior(db)
    task = create_task(tags=["czarina"])
    project_instance.config = {"capabilities": ["czarina"]}

    decision = await behavior.handle_incoming_task(task, global_instance)

    assert decision.action == TaskAction.DELEGATE
    assert decision.target_instance == project_instance

@pytest.mark.asyncio
async def test_project_handles_simple_tasks(db, project_instance):
    """Test Project handles simple tasks directly."""
    behavior = ProjectScopeBehavior(db)
    task = create_task(estimated_duration=30)  # 30 min = simple

    decision = await behavior.handle_incoming_task(task, project_instance)

    assert decision.action == TaskAction.EXECUTE

@pytest.mark.asyncio
async def test_orchestration_never_delegates(db, orchestration_instance):
    """Test Orchestration never delegates."""
    behavior = OrchestrationScopeBehavior(db)

    assert await behavior.should_delegate(create_task(), orchestration_instance) is False
```

## Best Practices

### DO
- Use Strategy pattern for extensibility
- Make behaviors stateless (get state from instance/task)
- Log all routing decisions
- Make behaviors configurable without code changes
- Test each behavior in isolation

### DON'T
- Hard-code routing rules
- Skip validation of instance states
- Make behaviors that depend on each other directly
- Forget to handle edge cases (no targets, all instances busy)

## References

- Design patterns: `/home/exedev/czarina/czarina-core/patterns/agent-knowledge/core-rules/design-patterns/`
- Tool use patterns: `/home/exedev/czarina/czarina-core/patterns/agent-knowledge/patterns/tool-use/`
