"""Tests for instance DAG edge API endpoints."""

import asyncio
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from hopper.models.base import Base
from hopper.models.enums import HopperScope, InstanceStatus, InstanceType
from hopper.models.hopper_instance import HopperInstance
from hopper.models.instance_relationship import InstanceRelationship


def _make_edge_client(monkeypatch) -> tuple[TestClient, async_sessionmaker]:
    """Build a TestClient backed by a fresh async-SQLite engine."""
    monkeypatch.setenv("HOPPER_API_RECORDS_BACKEND", "1")

    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def _setup() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(_setup())

    from hopper.api.app import create_app
    from hopper.api.dependencies import get_db

    app = create_app()

    async def _override_get_db():
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = _override_get_db
    return TestClient(app), session_factory


@pytest.fixture
def edge_client(monkeypatch) -> Generator[TestClient, None, None]:
    client, _ = _make_edge_client(monkeypatch)
    yield client


def _seed_instance(client: TestClient, iid: str) -> dict:
    """Create an instance via the API."""
    resp = client.post(
        "/api/v1/instances",
        json={"id": iid, "name": iid, "scope": "PERSONAL"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


class TestAddChildInstance:
    def test_create_edge(self, edge_client):
        _seed_instance(edge_client, "parent")
        _seed_instance(edge_client, "child")

        resp = edge_client.post("/api/v1/instances/parent/children/child")
        assert resp.status_code == 201
        assert resp.json()["status"] == "created"

    def test_idempotent(self, edge_client):
        _seed_instance(edge_client, "p")
        _seed_instance(edge_client, "c")

        resp1 = edge_client.post("/api/v1/instances/p/children/c")
        assert resp1.status_code == 201

        resp2 = edge_client.post("/api/v1/instances/p/children/c")
        assert resp2.json()["status"] == "already_exists"

    def test_cycle_rejected(self, edge_client):
        _seed_instance(edge_client, "A")
        _seed_instance(edge_client, "B")

        edge_client.post("/api/v1/instances/A/children/B")

        resp = edge_client.post("/api/v1/instances/B/children/A")
        assert resp.status_code == 422

    def test_self_loop_rejected(self, edge_client):
        _seed_instance(edge_client, "X")

        resp = edge_client.post("/api/v1/instances/X/children/X")
        assert resp.status_code == 422

    def test_missing_instance_404(self, edge_client):
        _seed_instance(edge_client, "exists")

        resp = edge_client.post("/api/v1/instances/exists/children/ghost")
        assert resp.status_code == 404

    def test_indirect_cycle_rejected(self, edge_client):
        """A -> B -> C, then C -> A should be rejected."""
        _seed_instance(edge_client, "A")
        _seed_instance(edge_client, "B")
        _seed_instance(edge_client, "C")

        edge_client.post("/api/v1/instances/A/children/B")
        edge_client.post("/api/v1/instances/B/children/C")

        resp = edge_client.post("/api/v1/instances/C/children/A")
        assert resp.status_code == 422

    def test_diamond_allowed(self, edge_client):
        """A -> B, A -> C, B -> D, C -> D — diamond is valid DAG."""
        for iid in ("A", "B", "C", "D"):
            _seed_instance(edge_client, iid)

        for p, c in [("A", "B"), ("A", "C"), ("B", "D"), ("C", "D")]:
            resp = edge_client.post(f"/api/v1/instances/{p}/children/{c}")
            assert resp.status_code == 201, f"Failed: {p}->{c}: {resp.text}"


class TestRemoveChildInstance:
    def test_remove_edge(self, edge_client):
        _seed_instance(edge_client, "p")
        _seed_instance(edge_client, "c")
        edge_client.post("/api/v1/instances/p/children/c")

        resp = edge_client.delete("/api/v1/instances/p/children/c")
        assert resp.status_code == 200
        assert resp.json()["status"] == "removed"

    def test_remove_nonexistent_404(self, edge_client):
        resp = edge_client.delete("/api/v1/instances/p/children/c")
        assert resp.status_code == 404


class TestGetChildrenAndParents:
    def test_get_children(self, edge_client):
        _seed_instance(edge_client, "overseer")
        _seed_instance(edge_client, "sub1")
        _seed_instance(edge_client, "sub2")
        edge_client.post("/api/v1/instances/overseer/children/sub1")
        edge_client.post("/api/v1/instances/overseer/children/sub2")

        resp = edge_client.get("/api/v1/instances/overseer/children")
        assert resp.status_code == 200
        data = resp.json()
        ids = {c["id"] for c in data["items"]}
        assert ids == {"sub1", "sub2"}

    def test_get_parents(self, edge_client):
        _seed_instance(edge_client, "o1")
        _seed_instance(edge_client, "o2")
        _seed_instance(edge_client, "shared")
        edge_client.post("/api/v1/instances/o1/children/shared")
        edge_client.post("/api/v1/instances/o2/children/shared")

        resp = edge_client.get("/api/v1/instances/shared/parents")
        assert resp.status_code == 200
        ids = {p["id"] for p in resp.json()}
        assert ids == {"o1", "o2"}

    def test_no_children(self, edge_client):
        _seed_instance(edge_client, "leaf")

        resp = edge_client.get("/api/v1/instances/leaf/children")
        assert resp.status_code == 200
        assert resp.json()["items"] == []
