"""Tests for MCP server context management."""

from hopper.mcp.context import ServerContext


class TestServerContext:
    """Test server context management."""

    def test_context_initialization(self, mock_config):
        """Test context initializes correctly."""
        context = ServerContext(mock_config)
        assert context.get_user() is None
        assert context.get_active_project() is None

    def test_set_and_get_user(self, mock_config):
        """Test setting and getting user."""
        context = ServerContext(mock_config)
        context.set_user("test-user")
        assert context.get_user() == "test-user"

    def test_set_and_get_active_project(self, mock_config):
        """Test setting and getting active project."""
        context = ServerContext(mock_config)
        context.set_active_project("test-project")
        assert context.get_active_project() == "test-project"

    def test_add_and_get_recent_tasks(self, mock_config):
        """Test adding and retrieving recent tasks."""
        context = ServerContext(mock_config)
        context.add_recent_task("task-1", "First task")
        context.add_recent_task("task-2", "Second task")

        recent = context.get_recent_tasks(limit=5)
        assert len(recent) == 2
        assert recent[0]["id"] == "task-2"  # Most recent first
        assert recent[1]["id"] == "task-1"

    def test_get_context(self, mock_config):
        """Test getting complete context."""
        context = ServerContext(mock_config)
        context.set_user("user-1")
        context.set_active_project("project-1")
        context.add_recent_task("task-1", "Task")

        ctx = context.get_context()
        assert ctx["user"] == "user-1"
        assert ctx["active_project"] == "project-1"
        assert len(ctx["recent_tasks"]) == 1

    def test_clear_context(self, mock_config):
        """Test clearing context."""
        context = ServerContext(mock_config)
        context.set_user("user-1")
        context.set_active_project("project-1")
        context.clear()

        assert context.get_user() is None
        assert context.get_active_project() is None
        assert len(context.get_recent_tasks()) == 0
