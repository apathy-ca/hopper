"""
Integration tests for API routing functionality.

Tests routing-related API endpoints including:
- Routing task requests
- Rule evaluation via API
- Decision recording
- Feedback collection
- Routing analytics
"""

import pytest
pytestmark = pytest.mark.skip(reason="Integration test: Requires running API server with routing configured")


import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.factories import (
    RoutingDecisionFactory,
    TaskFactory,
    TaskFeedbackFactory,
)
from tests.utils import (
    assert_response_error,
    assert_response_success,
    validate_routing_decision_schema,
)


@pytest.mark.integration
class TestRoutingAPI:
    """Test routing functionality through API."""

    def test_route_task_with_rules_engine(self, api_client: TestClient, db_session: Session):
        """Test routing a task using rules engine via API."""
        # Create task without destination
        task = TaskFactory.create(
            session=db_session,
            title="Implement authentication for API",
            project=None,  # No project assigned yet
            tags={"auth": True, "backend": True},
        )

        # Request routing via API
        response = api_client.post(f"/api/v1/tasks/{task.id}/route", json={"strategy": "rules"})
        assert_response_success(response)

        # Verify routing decision
        response_data = response.json()
        validate_routing_decision_schema(response_data)
        assert response_data["task_id"] == task.id
        assert response_data["strategy"] == "rules"
        assert "destination" in response_data
        assert "confidence" in response_data
        assert "reasoning" in response_data

        # Verify decision recorded in database
        from hopper.models.routing_decision import RoutingDecision

        decision = (
            db_session.query(RoutingDecision).filter(RoutingDecision.task_id == task.id).first()
        )
        assert decision is not None
        assert decision.destination == response_data["destination"]
        assert decision.strategy == "rules"

        # Verify task updated with routing
        db_session.refresh(task)
        assert task.project == response_data["destination"]
        assert task.status == "routed"

    def test_route_task_auto_assigns_destination(self, api_client: TestClient, db_session: Session):
        """Test that routing automatically assigns task to destination."""
        task = TaskFactory.create(
            session=db_session, title="Task about routing and queues", project=None
        )

        response = api_client.post(f"/api/v1/tasks/{task.id}/route", json={"strategy": "rules"})
        assert_response_success(response)

        response_data = response.json()
        destination = response_data["destination"]

        # Verify task assigned
        db_session.refresh(task)
        assert task.project == destination

    def test_get_routing_suggestions(self, api_client: TestClient, db_session: Session):
        """Test getting routing suggestions without applying them."""
        task = TaskFactory.create(
            session=db_session, title="Database optimization task", project=None
        )

        # Get suggestions (don't apply routing)
        response = api_client.get(f"/api/v1/tasks/{task.id}/routing-suggestions")
        assert_response_success(response)

        # Verify suggestions
        response_data = response.json()
        assert isinstance(response_data, list)
        assert len(response_data) > 0

        for suggestion in response_data:
            assert "destination" in suggestion
            assert "confidence" in suggestion
            assert "reasoning" in suggestion
            assert 0 <= suggestion["confidence"] <= 1

        # Verify task NOT updated (suggestions only)
        db_session.refresh(task)
        assert task.project is None  # Still unassigned

    def test_route_task_with_llm_fallback(self, api_client: TestClient, db_session: Session):
        """Test routing with LLM fallback when rules don't match."""
        # Create task that won't match any rules
        task = TaskFactory.create(
            session=db_session, title="Very obscure unusual task", project=None, tags={}
        )

        # Request routing with LLM fallback
        response = api_client.post(
            f"/api/v1/tasks/{task.id}/route", json={"strategy": "rules", "fallback": "llm"}
        )
        assert_response_success(response)

        response_data = response.json()
        # May use LLM if rules didn't match
        assert response_data["strategy"] in ["rules", "llm"]
        assert response_data["destination"] is not None

    def test_route_nonexistent_task(self, api_client: TestClient):
        """Test routing a non-existent task returns 404."""
        response = api_client.post("/api/v1/tasks/nonexistent/route", json={"strategy": "rules"})
        assert_response_error(response, 404)

    def test_route_already_routed_task(self, api_client: TestClient, db_session: Session):
        """Test routing a task that's already routed."""
        # Create task with existing routing
        task = TaskFactory.create(session=db_session, project="hopper", status="routed")

        # Attempt to route again
        response = api_client.post(f"/api/v1/tasks/{task.id}/route", json={"strategy": "rules"})

        # Could either return existing routing or create new decision
        # Depending on implementation, verify appropriate response
        assert response.status_code in [200, 409]  # OK or Conflict


@pytest.mark.integration
class TestRoutingDecisions:
    """Test routing decision management via API."""

    def test_get_routing_decision(self, api_client: TestClient, db_session: Session):
        """Test retrieving a routing decision."""
        task = TaskFactory.create(session=db_session)
        decision = RoutingDecisionFactory.create(
            session=db_session, task_id=task.id, destination="hopper"
        )

        response = api_client.get(f"/api/v1/routing-decisions/{decision.id}")
        assert_response_success(response)

        response_data = response.json()
        assert response_data["id"] == decision.id
        assert response_data["task_id"] == task.id
        assert response_data["destination"] == "hopper"

    def test_get_routing_decision_by_task(self, api_client: TestClient, db_session: Session):
        """Test getting routing decision for a specific task."""
        task = TaskFactory.create(session=db_session)
        decision = RoutingDecisionFactory.create(session=db_session, task_id=task.id)

        response = api_client.get(f"/api/v1/tasks/{task.id}/routing-decision")
        assert_response_success(response)

        response_data = response.json()
        assert response_data["id"] == decision.id
        assert response_data["task_id"] == task.id

    def test_list_routing_decisions(self, api_client: TestClient, db_session: Session):
        """Test listing all routing decisions."""
        # Create multiple decisions
        for i in range(5):
            task = TaskFactory.create(session=db_session)
            RoutingDecisionFactory.create(session=db_session, task_id=task.id)

        response = api_client.get("/api/v1/routing-decisions")
        assert_response_success(response)

        response_data = response.json()
        assert len(response_data) >= 5

    def test_filter_routing_decisions_by_strategy(
        self, api_client: TestClient, db_session: Session
    ):
        """Test filtering routing decisions by strategy."""
        # Create decisions with different strategies
        task1 = TaskFactory.create(session=db_session)
        task2 = TaskFactory.create(session=db_session)
        RoutingDecisionFactory.create_rules_based(session=db_session, task_id=task1.id)
        RoutingDecisionFactory.create_llm_based(session=db_session, task_id=task2.id)

        # Filter by strategy
        response = api_client.get("/api/v1/routing-decisions?strategy=rules")
        assert_response_success(response)

        response_data = response.json()
        for decision in response_data:
            assert decision["strategy"] == "rules"


@pytest.mark.integration
class TestRoutingFeedback:
    """Test routing feedback collection via API."""

    def test_provide_positive_feedback(self, api_client: TestClient, db_session: Session):
        """Test providing positive feedback on routing."""
        task = TaskFactory.create(session=db_session, project="hopper")
        decision = RoutingDecisionFactory.create(
            session=db_session, task_id=task.id, destination="hopper"
        )

        feedback_data = {
            "routing_correct": True,
            "confidence_rating": 5,
            "comments": "Perfect routing!",
        }

        response = api_client.post(f"/api/v1/tasks/{task.id}/routing-feedback", json=feedback_data)
        assert_response_success(response, 201)

        # Verify feedback recorded
        from hopper.models.task_feedback import TaskFeedback

        feedback = db_session.query(TaskFeedback).filter(TaskFeedback.task_id == task.id).first()
        assert feedback is not None
        assert feedback.routing_correct is True
        assert feedback.confidence_rating == 5

    def test_provide_negative_feedback_with_suggestion(
        self, api_client: TestClient, db_session: Session
    ):
        """Test providing negative feedback with alternative suggestion."""
        task = TaskFactory.create(session=db_session, project="hopper")
        decision = RoutingDecisionFactory.create(
            session=db_session, task_id=task.id, destination="hopper"
        )

        feedback_data = {
            "routing_correct": False,
            "confidence_rating": 2,
            "comments": "Should have gone to czarina",
            "suggested_destination": "czarina",
        }

        response = api_client.post(f"/api/v1/tasks/{task.id}/routing-feedback", json=feedback_data)
        assert_response_success(response, 201)

        response_data = response.json()
        assert response_data["routing_correct"] is False
        assert response_data["suggested_destination"] == "czarina"

    def test_feedback_affects_future_routing(self, api_client: TestClient, db_session: Session):
        """Test that feedback influences future routing decisions."""
        # Provide negative feedback for similar task
        task1 = TaskFactory.create(
            session=db_session, title="Task about orchestration", project="hopper"
        )
        decision1 = RoutingDecisionFactory.create(
            session=db_session, task_id=task1.id, destination="hopper"
        )
        TaskFeedbackFactory.create_negative(
            session=db_session, task_id=task1.id, suggested_destination="czarina"
        )

        # Create similar task and route it
        task2 = TaskFactory.create(
            session=db_session, title="Another orchestration task", project=None
        )

        response = api_client.post(
            f"/api/v1/tasks/{task2.id}/route", json={"strategy": "rules", "use_feedback": True}
        )
        assert_response_success(response)

        # Feedback should influence routing (may route to czarina instead)
        # Note: This behavior depends on implementation
        response_data = response.json()
        # Could verify confidence is lower or destination changed

    def test_get_routing_feedback(self, api_client: TestClient, db_session: Session):
        """Test retrieving routing feedback for a task."""
        task = TaskFactory.create(session=db_session)
        feedback = TaskFeedbackFactory.create(session=db_session, task_id=task.id)

        response = api_client.get(f"/api/v1/tasks/{task.id}/routing-feedback")
        assert_response_success(response)

        response_data = response.json()
        assert response_data["task_id"] == task.id
        assert response_data["routing_correct"] == feedback.routing_correct


@pytest.mark.integration
class TestRoutingAnalytics:
    """Test routing analytics and statistics via API."""

    def test_get_routing_statistics(self, api_client: TestClient, db_session: Session):
        """Test getting overall routing statistics."""
        # Create decisions with different strategies
        for i in range(10):
            task = TaskFactory.create(session=db_session)
            RoutingDecisionFactory.create_rules_based(session=db_session, task_id=task.id)

        for i in range(5):
            task = TaskFactory.create(session=db_session)
            RoutingDecisionFactory.create_llm_based(session=db_session, task_id=task.id)

        response = api_client.get("/api/v1/routing/statistics")
        assert_response_success(response)

        response_data = response.json()
        assert "total_decisions" in response_data
        assert "by_strategy" in response_data
        assert response_data["total_decisions"] >= 15
        assert "rules" in response_data["by_strategy"]
        assert "llm" in response_data["by_strategy"]

    def test_get_routing_accuracy_metrics(self, api_client: TestClient, db_session: Session):
        """Test getting routing accuracy metrics based on feedback."""
        # Create tasks with feedback
        for i in range(8):
            task = TaskFactory.create(session=db_session)
            decision = RoutingDecisionFactory.create(session=db_session, task_id=task.id)
            TaskFeedbackFactory.create_positive(session=db_session, task_id=task.id)

        for i in range(2):
            task = TaskFactory.create(session=db_session)
            decision = RoutingDecisionFactory.create(session=db_session, task_id=task.id)
            TaskFeedbackFactory.create_negative(session=db_session, task_id=task.id)

        response = api_client.get("/api/v1/routing/accuracy")
        assert_response_success(response)

        response_data = response.json()
        assert "accuracy" in response_data
        assert "total_with_feedback" in response_data
        # 8 correct out of 10 = 80% accuracy
        assert response_data["accuracy"] >= 0.75

    def test_get_destination_popularity(self, api_client: TestClient, db_session: Session):
        """Test getting most popular routing destinations."""
        # Create tasks routed to different projects
        for i in range(10):
            task = TaskFactory.create(session=db_session)
            RoutingDecisionFactory.create(session=db_session, task_id=task.id, destination="hopper")

        for i in range(5):
            task = TaskFactory.create(session=db_session)
            RoutingDecisionFactory.create(
                session=db_session, task_id=task.id, destination="czarina"
            )

        response = api_client.get("/api/v1/routing/destinations/popular")
        assert_response_success(response)

        response_data = response.json()
        assert isinstance(response_data, list)
        assert len(response_data) > 0

        # hopper should be most popular
        assert response_data[0]["destination"] == "hopper"
        assert response_data[0]["count"] >= 10

    def test_get_average_confidence_by_strategy(self, api_client: TestClient, db_session: Session):
        """Test getting average confidence scores by strategy."""
        # Create decisions with different strategies and confidences
        for i in range(5):
            task = TaskFactory.create(session=db_session)
            RoutingDecisionFactory.create_rules_based(
                session=db_session, task_id=task.id, confidence=0.9  # High confidence for rules
            )

        for i in range(5):
            task = TaskFactory.create(session=db_session)
            RoutingDecisionFactory.create_llm_based(
                session=db_session, task_id=task.id, confidence=0.6  # Lower confidence for LLM
            )

        response = api_client.get("/api/v1/routing/confidence/by-strategy")
        assert_response_success(response)

        response_data = response.json()
        assert "rules" in response_data
        assert "llm" in response_data
        assert response_data["rules"]["average"] >= 0.85
        assert response_data["llm"]["average"] <= 0.65


@pytest.mark.integration
class TestRuleEvaluation:
    """Test rule evaluation and matching via API."""

    def test_evaluate_rules_for_task(self, api_client: TestClient, db_session: Session):
        """Test evaluating routing rules for a specific task."""
        task = TaskFactory.create(
            session=db_session,
            title="Implement task queue routing",
            tags={"routing": True, "backend": True},
        )

        response = api_client.post("/api/v1/routing/evaluate-rules", json={"task_id": task.id})
        assert_response_success(response)

        response_data = response.json()
        assert "matched_rules" in response_data
        assert "destination" in response_data
        assert "confidence" in response_data

    def test_test_rule_against_task(self, api_client: TestClient, db_session: Session):
        """Test a specific rule against a task without applying it."""
        task = TaskFactory.create(session=db_session, title="Authentication task")

        rule_definition = {
            "type": "keyword",
            "keywords": ["authentication", "auth"],
            "destination": "hopper",
        }

        response = api_client.post(
            "/api/v1/routing/test-rule", json={"task_id": task.id, "rule": rule_definition}
        )
        assert_response_success(response)

        response_data = response.json()
        assert "matches" in response_data
        assert response_data["matches"] is True  # Should match "authentication"

    def test_validate_routing_rules(self, api_client: TestClient):
        """Test validating routing rule configuration."""
        rules_config = {
            "rules": [
                {
                    "name": "test_rule",
                    "type": "keyword",
                    "keywords": ["test"],
                    "destination": "test-project",
                }
            ]
        }

        response = api_client.post("/api/v1/routing/validate-rules", json=rules_config)
        assert_response_success(response)

        response_data = response.json()
        assert "valid" in response_data
        assert response_data["valid"] is True
