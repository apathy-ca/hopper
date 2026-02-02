"""
Enumerations used throughout Hopper data models.
"""

from enum import Enum


class TaskStatus(str, Enum):
    """Task status values."""

    PENDING = "pending"
    CLAIMED = "claimed"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    DONE = "done"
    CANCELLED = "cancelled"


class TaskPriority(str, Enum):
    """Task priority levels."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class HopperScope(str, Enum):
    """Hopper instance scope types."""

    GLOBAL = "GLOBAL"
    PROJECT = "PROJECT"
    ORCHESTRATION = "ORCHESTRATION"
    PERSONAL = "PERSONAL"
    FAMILY = "FAMILY"
    EVENT = "EVENT"
    FEDERATED = "FEDERATED"


class DecisionStrategy(str, Enum):
    """Routing decision strategies."""

    RULES = "rules"
    LLM = "llm"
    SAGE = "sage"
    HYBRID = "hybrid"
    SIMPLE_PRIORITY = "simple_priority"


class ExecutorType(str, Enum):
    """Types of task executors."""

    CZARINA = "czarina"
    SARK = "sark"
    HUMAN = "human"
    CUSTOM = "custom"
    SAGE = "sage"


class VelocityRequirement(str, Enum):
    """Task velocity requirements."""

    FAST = "fast"
    MEDIUM = "medium"
    SLOW = "slow"
    GLACIAL = "glacial"


class ExternalPlatform(str, Enum):
    """External platform types."""

    GITHUB = "github"
    GITLAB = "gitlab"
    JIRA = "jira"
    LINEAR = "linear"


class TaskSource(str, Enum):
    """Task source types."""

    MCP = "mcp"
    CLI = "cli"
    WEBHOOK = "webhook"
    EMAIL = "email"
    HTTP = "http"
    API = "api"


class InstanceStatus(str, Enum):
    """Hopper instance status values."""

    CREATED = "created"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    PAUSED = "paused"
    ERROR = "error"
    TERMINATED = "terminated"


class InstanceType(str, Enum):
    """Hopper instance types."""

    PERSISTENT = "persistent"
    EPHEMERAL = "ephemeral"
    TEMPORARY = "temporary"
