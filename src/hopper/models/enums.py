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
    CZARINA = "czarina"  # Learnings from Czarina phase closeouts


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


class RecordType(str, Enum):
    """Record type discriminator.

    - INBOX: default for untriaged captures (from `hopper note ...`).
      Triage agents move inbox items to terminal kinds.
    - TASK: record with a status lifecycle.
    - IDEA: no lifecycle, may never be "done."
    - NOTE: terminal, append-only context.
    - MEMORY: agent knowledge, first-class across agents (attributed by
      author DID). Not tied to Claude's auto-memory; that system stays
      untouched here and can bridge in later via MCP.
    - REFERENCE: pointer to external resource (doc, dashboard, ticket).
    - LOG: immutable event record (publishes, GPU state transitions).
    - JOB: a unit of compute work (e.g. GPU job). A valued use case, but
      kept out of default task/context/memory views via its own kind.

    Payload stays JSON so types can evolve without schema migrations.
    """

    INBOX = "inbox"
    TASK = "task"
    IDEA = "idea"
    NOTE = "note"
    MEMORY = "memory"
    REFERENCE = "reference"
    LOG = "log"
    JOB = "job"


class RevisionAction(str, Enum):
    """Action recorded on a revision.

    create/update/tombstone are applied directly. propose is a pending change
    that does not advance the record's current_revision until followed by an
    apply. reject marks a propose as refused.
    """

    CREATE = "create"
    UPDATE = "update"
    TOMBSTONE = "tombstone"
    PROPOSE = "propose"
    APPLY = "apply"
    REJECT = "reject"
