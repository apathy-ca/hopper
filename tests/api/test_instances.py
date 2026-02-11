"""
Tests for instance API routes.

Tests the instance API endpoints for CRUD operations, hierarchy, and lifecycle.
"""

import pytest
from sqlalchemy.orm import Session

from hopper.models import HopperInstance, HopperScope, InstanceStatus, InstanceType
from hopper.api.schemas.hopper_instance import (
    InstanceCreate,
    InstanceUpdate,
    InstanceResponse,
    HopperScope as SchemaScope,
    InstanceStatus as SchemaStatus,
    InstanceType as SchemaType,
)


class TestInstanceSchemas:
    """Test instance schema validation and conversion."""

    def test_instance_create_schema(self):
        """Test InstanceCreate schema validation."""
        data = InstanceCreate(
            name="test-instance",
            scope=SchemaScope.PROJECT,
            instance_type=SchemaType.PERSISTENT,
            description="Test instance",
        )
        assert data.name == "test-instance"
        assert data.scope == SchemaScope.PROJECT
        assert data.instance_type == SchemaType.PERSISTENT

    def test_instance_create_with_parent(self):
        """Test InstanceCreate schema with parent_id."""
        data = InstanceCreate(
            name="child-instance",
            scope=SchemaScope.ORCHESTRATION,
            parent_id="parent-123",
        )
        assert data.parent_id == "parent-123"

    def test_instance_update_schema(self):
        """Test InstanceUpdate schema partial updates."""
        # Only name
        data = InstanceUpdate(name="new-name")
        assert data.name == "new-name"
        assert data.status is None
        assert data.config is None

        # Only status
        data = InstanceUpdate(status=SchemaStatus.RUNNING)
        assert data.status == SchemaStatus.RUNNING
        assert data.name is None


class TestInstanceModel:
    """Test HopperInstance model operations."""

    def test_create_instance(self, clean_db: Session):
        """Test creating a HopperInstance."""
        instance = HopperInstance(
            id="test-instance-1",
            name="Test Instance",
            scope=HopperScope.PROJECT,
            instance_type=InstanceType.PERSISTENT,
            status=InstanceStatus.CREATED,
        )
        clean_db.add(instance)
        clean_db.commit()

        retrieved = clean_db.query(HopperInstance).filter_by(id="test-instance-1").first()
        assert retrieved is not None
        assert retrieved.name == "Test Instance"
        assert retrieved.scope == HopperScope.PROJECT
        assert retrieved.status == InstanceStatus.CREATED

    def test_instance_hierarchy(self, clean_db: Session):
        """Test parent-child relationships."""
        # Create parent
        parent = HopperInstance(
            id="parent-instance",
            name="Parent",
            scope=HopperScope.GLOBAL,
            status=InstanceStatus.RUNNING,
        )
        clean_db.add(parent)
        clean_db.commit()

        # Create child
        child = HopperInstance(
            id="child-instance",
            name="Child",
            scope=HopperScope.PROJECT,
            parent_id="parent-instance",
            status=InstanceStatus.RUNNING,
        )
        clean_db.add(child)
        clean_db.commit()

        # Verify relationship
        retrieved_child = clean_db.query(HopperInstance).filter_by(id="child-instance").first()
        assert retrieved_child.parent_id == "parent-instance"
        assert retrieved_child.parent.name == "Parent"

        # Verify parent's children
        retrieved_parent = clean_db.query(HopperInstance).filter_by(id="parent-instance").first()
        assert len(retrieved_parent.children) == 1
        assert retrieved_parent.children[0].name == "Child"

    def test_instance_status_lifecycle(self, clean_db: Session):
        """Test instance status transitions."""
        instance = HopperInstance(
            id="lifecycle-test",
            name="Lifecycle Test",
            scope=HopperScope.PROJECT,
            status=InstanceStatus.CREATED,
        )
        clean_db.add(instance)
        clean_db.commit()

        # Start instance
        instance.status = InstanceStatus.RUNNING
        clean_db.commit()

        retrieved = clean_db.query(HopperInstance).filter_by(id="lifecycle-test").first()
        assert retrieved.status == InstanceStatus.RUNNING

        # Pause instance
        instance.status = InstanceStatus.PAUSED
        clean_db.commit()

        retrieved = clean_db.query(HopperInstance).filter_by(id="lifecycle-test").first()
        assert retrieved.status == InstanceStatus.PAUSED

        # Stop instance
        instance.status = InstanceStatus.STOPPED
        clean_db.commit()

        retrieved = clean_db.query(HopperInstance).filter_by(id="lifecycle-test").first()
        assert retrieved.status == InstanceStatus.STOPPED

    def test_instance_config_jsonb(self, clean_db: Session):
        """Test instance config JSONB field."""
        config = {
            "max_concurrent_tasks": 10,
            "routing_strategy": "rules",
            "custom_setting": {"nested": "value"},
        }
        instance = HopperInstance(
            id="config-test",
            name="Config Test",
            scope=HopperScope.PROJECT,
            config=config,
            status=InstanceStatus.CREATED,
        )
        clean_db.add(instance)
        clean_db.commit()

        retrieved = clean_db.query(HopperInstance).filter_by(id="config-test").first()
        assert retrieved.config == config
        assert retrieved.config["max_concurrent_tasks"] == 10
        assert retrieved.config["custom_setting"]["nested"] == "value"

    def test_instance_get_ancestors(self, clean_db: Session):
        """Test getting instance ancestors."""
        # Create 3-level hierarchy
        global_inst = HopperInstance(
            id="global-1",
            name="Global",
            scope=HopperScope.GLOBAL,
            status=InstanceStatus.RUNNING,
        )
        clean_db.add(global_inst)
        clean_db.commit()

        project_inst = HopperInstance(
            id="project-1",
            name="Project",
            scope=HopperScope.PROJECT,
            parent_id="global-1",
            status=InstanceStatus.RUNNING,
        )
        clean_db.add(project_inst)
        clean_db.commit()

        orch_inst = HopperInstance(
            id="orch-1",
            name="Orchestration",
            scope=HopperScope.ORCHESTRATION,
            parent_id="project-1",
            status=InstanceStatus.RUNNING,
        )
        clean_db.add(orch_inst)
        clean_db.commit()

        # Get ancestors from orchestration
        retrieved = clean_db.query(HopperInstance).filter_by(id="orch-1").first()
        ancestors = retrieved.get_ancestors()

        assert len(ancestors) == 2
        assert ancestors[0].id == "project-1"  # Immediate parent
        assert ancestors[1].id == "global-1"   # Root

    def test_instance_get_root(self, clean_db: Session):
        """Test getting root instance."""
        # Create hierarchy
        root = HopperInstance(
            id="root-1",
            name="Root",
            scope=HopperScope.GLOBAL,
            status=InstanceStatus.RUNNING,
        )
        clean_db.add(root)
        clean_db.commit()

        child = HopperInstance(
            id="child-1",
            name="Child",
            scope=HopperScope.PROJECT,
            parent_id="root-1",
            status=InstanceStatus.RUNNING,
        )
        clean_db.add(child)
        clean_db.commit()

        # Root's root is itself
        assert root.get_root().id == "root-1"

        # Child's root is the parent
        retrieved_child = clean_db.query(HopperInstance).filter_by(id="child-1").first()
        assert retrieved_child.get_root().id == "root-1"

    def test_instance_is_root(self, clean_db: Session):
        """Test is_root check."""
        root = HopperInstance(
            id="root-check",
            name="Root",
            scope=HopperScope.GLOBAL,
            status=InstanceStatus.RUNNING,
        )
        clean_db.add(root)
        clean_db.commit()

        child = HopperInstance(
            id="child-check",
            name="Child",
            scope=HopperScope.PROJECT,
            parent_id="root-check",
            status=InstanceStatus.RUNNING,
        )
        clean_db.add(child)
        clean_db.commit()

        assert root.is_root() is True

        retrieved_child = clean_db.query(HopperInstance).filter_by(id="child-check").first()
        assert retrieved_child.is_root() is False

    def test_instance_get_depth(self, clean_db: Session):
        """Test getting instance depth in hierarchy."""
        # Create 3-level hierarchy
        level0 = HopperInstance(id="depth-0", name="L0", scope=HopperScope.GLOBAL, status=InstanceStatus.RUNNING)
        clean_db.add(level0)
        clean_db.commit()

        level1 = HopperInstance(id="depth-1", name="L1", scope=HopperScope.PROJECT, parent_id="depth-0", status=InstanceStatus.RUNNING)
        clean_db.add(level1)
        clean_db.commit()

        level2 = HopperInstance(id="depth-2", name="L2", scope=HopperScope.ORCHESTRATION, parent_id="depth-1", status=InstanceStatus.RUNNING)
        clean_db.add(level2)
        clean_db.commit()

        assert level0.get_depth() == 0

        retrieved_l1 = clean_db.query(HopperInstance).filter_by(id="depth-1").first()
        assert retrieved_l1.get_depth() == 1

        retrieved_l2 = clean_db.query(HopperInstance).filter_by(id="depth-2").first()
        assert retrieved_l2.get_depth() == 2


class TestEnumAlignment:
    """Test that schema enums align with model enums."""

    def test_scope_enum_values_match(self):
        """Verify schema scope values match model scope values."""
        # Schema uses uppercase values now
        assert SchemaScope.GLOBAL.value == HopperScope.GLOBAL.value
        assert SchemaScope.PROJECT.value == HopperScope.PROJECT.value
        assert SchemaScope.ORCHESTRATION.value == HopperScope.ORCHESTRATION.value

    def test_status_enum_values_match(self):
        """Verify schema status values match model status values."""
        assert SchemaStatus.CREATED.value == InstanceStatus.CREATED.value
        assert SchemaStatus.RUNNING.value == InstanceStatus.RUNNING.value
        assert SchemaStatus.STOPPED.value == InstanceStatus.STOPPED.value
        assert SchemaStatus.PAUSED.value == InstanceStatus.PAUSED.value
        assert SchemaStatus.TERMINATED.value == InstanceStatus.TERMINATED.value

    def test_instance_type_enum_values_match(self):
        """Verify schema instance type values match model values."""
        assert SchemaType.PERSISTENT.value == InstanceType.PERSISTENT.value
        assert SchemaType.EPHEMERAL.value == InstanceType.EPHEMERAL.value
        assert SchemaType.TEMPORARY.value == InstanceType.TEMPORARY.value
