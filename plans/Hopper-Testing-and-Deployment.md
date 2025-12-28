# 🧪 Hopper Testing & Deployment Guide

**Companion to:** Hopper Implementation Plan v1.0.0  
**Created:** 2025-12-26  
**Purpose:** Testing strategies and deployment procedures

---

## Testing Strategy

### Test Pyramid

```
                    ┌─────────────┐
                    │   E2E Tests │  (10%)
                    │   5-10 tests│
                    └─────────────┘
                  ┌───────────────────┐
                  │ Integration Tests │  (30%)
                  │   30-50 tests     │
                  └───────────────────┘
              ┌─────────────────────────────┐
              │      Unit Tests             │  (60%)
              │      100+ tests             │
              └─────────────────────────────┘
```

### 1. Unit Tests

**Coverage Target:** 80%+ for core logic

```python
# tests/unit/test_models.py
import pytest
from datetime import datetime
from hopper.core.models import Task, TaskCreate, Priority, Status

class TestTaskModel:
    def test_task_creation_with_defaults(self):
        """Test task creation with default values"""
        task = TaskCreate(title="Test task")
        assert task.title == "Test task"
        assert task.priority == Priority.MEDIUM
        assert task.tags == []
        assert task.description == ""
    
    def test_task_validation_title_required(self):
        """Test that title is required"""
        with pytest.raises(ValueError):
            TaskCreate(title="")
    
    def test_task_validation_title_max_length(self):
        """Test title max length validation"""
        with pytest.raises(ValueError):
            TaskCreate(title="x" * 501)
    
    def test_task_priority_enum(self):
        """Test priority enum validation"""
        task = TaskCreate(title="Test", priority=Priority.URGENT)
        assert task.priority == Priority.URGENT
        
        with pytest.raises(ValueError):
            TaskCreate(title="Test", priority="invalid")

# tests/unit/test_intelligence_rules.py
import pytest
from hopper.intelligence.rules import RulesIntelligence
from hopper.core.models import Task, TaskCreate

class TestRulesIntelligence:
    @pytest.fixture
    def intelligence(self):
        config = {
            "routing_rules": {
                "czarina": {
                    "keywords": ["orchestration", "worker"],
                    "tags": ["orchestration"],
                    "capabilities": ["multi-agent"]
                },
                "sark": {
                    "keywords": ["security", "policy"],
                    "tags": ["security"],
                    "capabilities": ["policy-enforcement"]
                }
            },
            "default_project": "hopper"
        }
        return RulesIntelligence(config)
    
    @pytest.fixture
    def projects(self):
        return [
            {"name": "czarina", "capabilities": ["multi-agent", "orchestration"]},
            {"name": "sark", "capabilities": ["policy-enforcement", "security"]},
            {"name": "hopper", "capabilities": ["task-management"]}
        ]
    
    async def test_explicit_project_assignment(self, intelligence, projects):
        """Test explicit project assignment takes precedence"""
        task = Task(title="Test", project="sark")
        decision = await intelligence.decide_routing(task, projects, {})
        
        assert decision.project == "sark"
        assert decision.confidence == 1.0
        assert "Explicit" in decision.reasoning
    
    async def test_keyword_matching(self, intelligence, projects):
        """Test keyword-based routing"""
        task = Task(title="Add orchestration worker", description="")
        decision = await intelligence.decide_routing(task, projects, {})
        
        assert decision.project == "czarina"
        assert decision.confidence > 0
    
    async def test_tag_matching(self, intelligence, projects):
        """Test tag-based routing"""
        task = Task(title="Task", tags=["security"])
        decision = await intelligence.decide_routing(task, projects, {})
        
        assert decision.project == "sark"
    
    async def test_capability_matching(self, intelligence, projects):
        """Test capability-based routing"""
        task = Task(
            title="Task",
            required_capabilities=["policy-enforcement"]
        )
        decision = await intelligence.decide_routing(task, projects, {})
        
        assert decision.project == "sark"
    
    async def test_default_fallback(self, intelligence, projects):
        """Test fallback to default project"""
        task = Task(title="Random task with no matches")
        decision = await intelligence.decide_routing(task, projects, {})
        
        assert decision.project == "hopper"
        assert decision.confidence == 0.5

# tests/unit/test_memory_working.py
import pytest
from hopper.memory.working import WorkingMemory
from unittest.mock import Mock, patch

class TestWorkingMemory:
    @pytest.fixture
    def memory(self):
        with patch('redis.from_url') as mock_redis:
            mock_redis.return_value = Mock()
            return WorkingMemory("redis://localhost:6379")
    
    def test_store_routing_context(self, memory):
        """Test storing routing context"""
        context = {
            "similar_recent": [],
            "project_availability": {"czarina": 3, "sark": 1}
        }
        
        memory.store_routing_context("TASK-123", context)
        
        memory.redis.setex.assert_called_once()
        args = memory.redis.setex.call_args
        assert args[0][0] == "routing:context:TASK-123"
        assert args[0][1] == 3600  # TTL
```

### 2. Integration Tests

**Focus:** Component interactions, database operations, external services

```python
# tests/integration/test_api_tasks.py
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from hopper.api.main import app
from hopper.core.database import Base, get_db

# Test database setup
SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture
def db():
    Base.metadata.create_all(bind=engine)
    yield TestingSessionLocal()
    Base.metadata.drop_all(bind=engine)

@pytest.fixture
def client(db):
    def override_get_db():
        try:
            yield db
        finally:
            db.close()
    
    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)

class TestTaskAPI:
    def test_create_task(self, client):
        """Test task creation via API"""
        response = client.post(
            "/api/v1/tasks",
            json={
                "title": "Test task",
                "description": "Test description",
                "tags": ["test"],
                "priority": "high"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "task_id" in data
        assert data["routed_to"] is not None
        assert "routing_confidence" in data
    
    def test_list_tasks(self, client):
        """Test listing tasks"""
        # Create some tasks
        for i in range(3):
            client.post(
                "/api/v1/tasks",
                json={"title": f"Task {i}", "tags": ["test"]}
            )
        
        # List tasks
        response = client.get("/api/v1/tasks")
        assert response.status_code == 200
        
        data = response.json()
        assert "tasks" in data
        assert len(data["tasks"]) == 3
    
    def test_list_tasks_with_filters(self, client):
        """Test listing tasks with filters"""
        # Create tasks with different statuses
        client.post("/api/v1/tasks", json={"title": "Task 1", "status": "pending"})
        client.post("/api/v1/tasks", json={"title": "Task 2", "status": "done"})
        
        # Filter by status
        response = client.get("/api/v1/tasks?status=pending")
        data = response.json()
        
        assert len(data["tasks"]) == 1
        assert data["tasks"][0]["status"] == "pending"
    
    def test_get_task(self, client):
        """Test getting specific task"""
        # Create task
        create_response = client.post(
            "/api/v1/tasks",
            json={"title": "Test task"}
        )
        task_id = create_response.json()["task_id"]
        
        # Get task
        response = client.get(f"/api/v1/tasks/{task_id}")
        assert response.status_code == 200
        
        data = response.json()
        assert data["id"] == task_id
        assert data["title"] == "Test task"
    
    def test_claim_task(self, client):
        """Test claiming a task"""
        # Create task
        create_response = client.post(
            "/api/v1/tasks",
            json={"title": "Test task"}
        )
        task_id = create_response.json()["task_id"]
        
        # Claim task
        response = client.post(
            f"/api/v1/tasks/{task_id}/claim",
            json={"executor": "test-worker"}
        )
        assert response.status_code == 200
        
        data = response.json()
        assert data["status"] == "claimed"
        assert data["owner"] == "test-worker"
    
    def test_complete_task_with_feedback(self, client):
        """Test completing task with feedback"""
        # Create and claim task
        create_response = client.post(
            "/api/v1/tasks",
            json={"title": "Test task"}
        )
        task_id = create_response.json()["task_id"]
        
        client.post(
            f"/api/v1/tasks/{task_id}/claim",
            json={"executor": "test-worker"}
        )
        
        # Complete with feedback
        response = client.post(
            f"/api/v1/tasks/{task_id}/complete",
            json={
                "feedback": {
                    "actual_duration": "2h",
                    "quality_score": 4.5,
                    "was_good_match": True,
                    "notes": "Completed successfully"
                }
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "done"

# tests/integration/test_github_sync.py
import pytest
from unittest.mock import Mock, patch
from hopper.integrations.github import GitHubIntegration
from hopper.core.models import Task

class TestGitHubIntegration:
    @pytest.fixture
    def github(self):
        with patch('github.Github') as mock_gh:
            return GitHubIntegration(token="test-token", owner="test-owner")
    
    def test_create_issue_from_task(self, github):
        """Test creating GitHub issue from task"""
        task = Task(
            id="TASK-123",
            title="Test task",
            description="Test description",
            tags=["bug", "urgent"],
            priority="high"
        )
        
        result = github.create_issue("test-repo", task)
        
        assert "id" in result
        assert "number" in result
        assert "url" in result
    
    def test_import_issue_as_task(self, github):
        """Test importing GitHub issue as task"""
        task = github.import_issue("test-repo", 123)
        
        assert task.title is not None
        assert task.external_platform == "github"
        assert task.external_id is not None
```

### 3. End-to-End Tests

**Focus:** Complete workflows from user perspective

```python
# tests/e2e/test_mcp_workflow.py
import pytest
from hopper.mcp.server import MCPServer
from hopper.api.client import HopperClient

@pytest.mark.e2e
class TestMCPWorkflow:
    @pytest.fixture
    def hopper_client(self):
        return HopperClient("http://localhost:8080")
    
    @pytest.fixture
    def mcp_server(self):
        return MCPServer("hopper", version="1.0.0")
    
    def test_claude_conversation_workflow(self, mcp_server, hopper_client):
        """Test complete workflow from Claude conversation"""
        # Simulate MCP call from Claude
        response = mcp_server.call_tool(
            "add_task",
            title="Add logging to SARK",
            description="Implement structured logging",
            tags=["infrastructure", "logging"],
            project="sark"
        )
        
        assert response["routed_to"] == "sark"
        task_id = response["task_id"]
        
        # Verify task exists in Hopper
        task = hopper_client.get_task(task_id)
        assert task["project"] == "sark"
        assert "infrastructure" in task["tags"]
        
        # Verify GitHub issue created (if sync enabled)
        if task.get("external_url"):
            assert "github.com" in task["external_url"]
    
    def test_multi_instance_delegation(self, hopper_client):
        """Test task delegation through instance hierarchy"""
        # Create task in global hopper
        response = hopper_client.add_task(
            title="Implement feature X",
            tags=["feature", "backend"],
            project="czarina"
        )
        
        global_task_id = response["task_id"]
        
        # Verify task routed to project hopper
        assert response["routed_to"] == "czarina"
        
        # Check project hopper received task
        project_hopper = HopperClient("http://localhost:8080", instance="hopper-czarina")
        project_tasks = project_hopper.list_tasks()
        
        assert any(t["title"] == "Implement feature X" for t in project_tasks)

# tests/e2e/test_learning_workflow.py
@pytest.mark.e2e
class TestLearningWorkflow:
    def test_routing_improves_over_time(self, hopper_client):
        """Test that routing accuracy improves with feedback"""
        # Create similar tasks and provide feedback
        for i in range(10):
            response = hopper_client.add_task(
                title=f"Security task {i}",
                tags=["security", "mcp"]
            )
            task_id = response["task_id"]
            
            # Simulate completion with feedback
            hopper_client.complete_task(
                task_id,
                feedback={
                    "was_good_match": response["routed_to"] == "sark",
                    "quality_score": 4.5 if response["routed_to"] == "sark" else 2.0,
                    "should_have_routed_to": "sark" if response["routed_to"] != "sark" else None
                }
            )
        
        # Trigger consolidation
        hopper_client.consolidate_memory()
        
        # Create new similar task
        response = hopper_client.add_task(
            title="Security task new",
            tags=["security", "mcp"]
        )
        
        # Should route to SARK with high confidence
        assert response["routed_to"] == "sark"
        assert response["routing_confidence"] > 0.8
```

### 