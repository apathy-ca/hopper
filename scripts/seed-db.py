#!/usr/bin/env python
"""
Seed the database with sample data for development and testing.

Usage:
    python scripts/seed-db.py [--reset]

Options:
    --reset    Reset database before seeding
"""
import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from hopper.database.connection import get_sync_session, reset_session_factories
from hopper.database.init import reset_database
from hopper.database.repositories import (
    ProjectRepository,
    TaskRepository,
    RoutingDecisionRepository,
)


def seed_projects(session):
    """Seed sample projects."""
    project_repo = ProjectRepository(session)

    projects = [
        {
            "name": "czarina",
            "slug": "czarina",
            "repository": "https://github.com/user/czarina",
            "capabilities": {
                "languages": ["python"],
                "skills": ["orchestration", "planning", "code-generation"],
            },
            "tags": ["ai", "orchestration", "automation"],
            "executor_type": "agent",
            "executor_config": {"model": "claude-3-5-sonnet", "temperature": 0.7},
            "auto_claim": True,
            "velocity": "fast",
            "created_by": "admin",
        },
        {
            "name": "sark",
            "slug": "sark",
            "repository": "https://github.com/user/sark",
            "capabilities": {
                "languages": ["python", "typescript", "rust"],
                "skills": ["coding", "debugging", "testing"],
            },
            "tags": ["ai", "coding", "assistant"],
            "executor_type": "agent",
            "executor_config": {"model": "claude-3-5-sonnet", "temperature": 0.3},
            "auto_claim": False,
            "velocity": "medium",
            "created_by": "admin",
        },
        {
            "name": "documentation",
            "slug": "docs",
            "repository": "https://github.com/user/docs",
            "capabilities": {
                "languages": ["markdown"],
                "skills": ["writing", "documentation", "explaining"],
            },
            "tags": ["documentation", "writing"],
            "executor_type": "human",
            "auto_claim": False,
            "velocity": "slow",
            "created_by": "admin",
        },
    ]

    created = []
    for project_data in projects:
        try:
            project = project_repo.create(**project_data)
            created.append(project)
            print(f"✓ Created project: {project.name}")
        except Exception as e:
            print(f"✗ Failed to create project {project_data['name']}: {e}")

    return created


def seed_tasks(session):
    """Seed sample tasks."""
    task_repo = TaskRepository(session)

    now = datetime.utcnow()

    tasks = [
        {
            "id": "task-001",
            "title": "Implement user authentication",
            "description": "Add JWT-based authentication to the API",
            "project": "czarina",
            "status": "in_progress",
            "priority": "high",
            "requester": "alice",
            "owner": "czarina-agent",
            "source": "mcp",
            "tags": ["backend", "security", "api"],
            "required_capabilities": ["python", "jwt", "security"],
            "created_at": now - timedelta(days=2),
        },
        {
            "id": "task-002",
            "title": "Fix bug in task routing",
            "description": "Tasks are not being routed to the correct project",
            "project": "sark",
            "status": "pending",
            "priority": "high",
            "requester": "bob",
            "source": "cli",
            "tags": ["bug", "routing"],
            "required_capabilities": ["python", "debugging"],
            "created_at": now - timedelta(days=1),
        },
        {
            "id": "task-003",
            "title": "Write API documentation",
            "description": "Document all REST API endpoints with examples",
            "project": "documentation",
            "status": "pending",
            "priority": "medium",
            "requester": "alice",
            "source": "http",
            "tags": ["documentation", "api"],
            "required_capabilities": ["writing", "api-knowledge"],
            "created_at": now - timedelta(hours=12),
        },
        {
            "id": "task-004",
            "title": "Add database migration for user preferences",
            "description": "Create Alembic migration for new user_preferences table",
            "status": "pending",
            "priority": "medium",
            "requester": "charlie",
            "source": "mcp",
            "tags": ["database", "migration"],
            "required_capabilities": ["python", "sql", "alembic"],
            "created_at": now - timedelta(hours=6),
        },
        {
            "id": "task-005",
            "title": "Optimize task query performance",
            "description": "Add indexes and optimize slow queries in task repository",
            "project": "sark",
            "status": "completed",
            "priority": "medium",
            "requester": "bob",
            "owner": "sark-agent",
            "source": "cli",
            "tags": ["performance", "database"],
            "required_capabilities": ["sql", "optimization"],
            "created_at": now - timedelta(days=5),
        },
        {
            "id": "task-006",
            "title": "Update README with setup instructions",
            "description": "Add step-by-step setup guide for new contributors",
            "project": "documentation",
            "status": "completed",
            "priority": "low",
            "requester": "alice",
            "owner": "alice",
            "source": "http",
            "tags": ["documentation", "onboarding"],
            "created_at": now - timedelta(days=7),
        },
    ]

    created = []
    for task_data in tasks:
        try:
            task = task_repo.create(**task_data)
            created.append(task)
            print(f"✓ Created task: {task.id} - {task.title}")
        except Exception as e:
            print(f"✗ Failed to create task {task_data['id']}: {e}")

    return created


def seed_routing_decisions(session):
    """Seed sample routing decisions."""
    routing_repo = RoutingDecisionRepository(session)

    decisions = [
        {
            "task_id": "task-001",
            "project": "czarina",
            "confidence": 0.95,
            "reasoning": "Project has required capabilities (python, jwt, security) and is active",
            "alternatives": {"sark": 0.7, "documentation": 0.1},
            "decided_by": "llm",
            "decision_time_ms": 250.5,
            "context": {"strategy": "llm-routing", "model": "claude-3-5-sonnet"},
        },
        {
            "task_id": "task-002",
            "project": "sark",
            "confidence": 0.88,
            "reasoning": "Bug fix matches project capabilities (python, debugging)",
            "alternatives": {"czarina": 0.6},
            "decided_by": "rules",
            "decision_time_ms": 12.3,
            "context": {"strategy": "keyword-matching", "matched_tags": ["bug"]},
        },
        {
            "task_id": "task-003",
            "project": "documentation",
            "confidence": 0.99,
            "reasoning": "Perfect match for documentation project",
            "alternatives": {},
            "decided_by": "rules",
            "decision_time_ms": 8.7,
            "context": {"strategy": "capability-matching"},
        },
        {
            "task_id": "task-005",
            "project": "sark",
            "confidence": 0.92,
            "reasoning": "Database optimization requires coding skills",
            "decided_by": "llm",
            "decision_time_ms": 315.2,
            "context": {"strategy": "llm-routing"},
        },
        {
            "task_id": "task-006",
            "project": "documentation",
            "confidence": 1.0,
            "reasoning": "Documentation task routed to documentation project",
            "decided_by": "rules",
            "decision_time_ms": 5.1,
            "context": {"strategy": "exact-match"},
        },
    ]

    created = []
    for decision_data in decisions:
        try:
            decision = routing_repo.create(**decision_data)
            created.append(decision)
            print(f"✓ Created routing decision for task: {decision.task_id}")
        except Exception as e:
            print(f"✗ Failed to create routing decision for {decision_data['task_id']}: {e}")

    return created


def main():
    """Main seeding function."""
    parser = argparse.ArgumentParser(description="Seed database with sample data")
    parser.add_argument("--reset", action="store_true", help="Reset database before seeding")
    args = parser.parse_args()

    print("=" * 60)
    print("Hopper Database Seeder")
    print("=" * 60)

    if args.reset:
        print("\n⚠️  Resetting database...")
        reset_database(confirm=True)
        print("✓ Database reset complete")

    print("\n📦 Seeding database...")

    try:
        with get_sync_session() as session:
            # Seed projects
            print("\n1. Seeding projects...")
            projects = seed_projects(session)
            print(f"   Created {len(projects)} projects")

            # Seed tasks
            print("\n2. Seeding tasks...")
            tasks = seed_tasks(session)
            print(f"   Created {len(tasks)} tasks")

            # Seed routing decisions
            print("\n3. Seeding routing decisions...")
            decisions = seed_routing_decisions(session)
            print(f"   Created {len(decisions)} routing decisions")

            session.commit()

        print("\n" + "=" * 60)
        print("✓ Database seeding complete!")
        print("=" * 60)

    except Exception as e:
        print(f"\n✗ Error seeding database: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    finally:
        reset_session_factories()


if __name__ == "__main__":
    main()
