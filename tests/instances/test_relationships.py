"""Tests for instance relationships — DAG model, migration, and cycle detection."""

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from hopper.models import HopperInstance, HopperScope, InstanceRelationship, InstanceStatus, InstanceType


def _make_instance(session: Session, iid: str) -> HopperInstance:
    inst = HopperInstance(
        id=iid,
        name=iid,
        scope=HopperScope.PERSONAL,
        instance_type=InstanceType.PERSISTENT,
        status=InstanceStatus.CREATED,
    )
    session.add(inst)
    session.flush()
    return inst


class TestInstanceRelationshipModel:
    def test_create_edge(self, clean_db: Session):
        _make_instance(clean_db, "parent")
        _make_instance(clean_db, "child")

        edge = InstanceRelationship(parent_id="parent", child_id="child")
        clean_db.add(edge)
        clean_db.commit()

        result = clean_db.query(InstanceRelationship).first()
        assert result.parent_id == "parent"
        assert result.child_id == "child"
        assert result.created_at is not None

    def test_composite_pk_prevents_duplicate(self, clean_db: Session):
        import pytest

        _make_instance(clean_db, "p")
        _make_instance(clean_db, "c")

        clean_db.add(InstanceRelationship(parent_id="p", child_id="c"))
        clean_db.flush()
        clean_db.add(InstanceRelationship(parent_id="p", child_id="c"))
        with pytest.raises(IntegrityError):
            clean_db.flush()

    def test_dag_multiple_parents(self, clean_db: Session):
        """An instance can have multiple parents (DAG, not tree)."""
        _make_instance(clean_db, "overseer1")
        _make_instance(clean_db, "overseer2")
        _make_instance(clean_db, "shared-child")

        clean_db.add(InstanceRelationship(parent_id="overseer1", child_id="shared-child"))
        clean_db.add(InstanceRelationship(parent_id="overseer2", child_id="shared-child"))
        clean_db.commit()

        edges = clean_db.query(InstanceRelationship).filter_by(child_id="shared-child").all()
        assert len(edges) == 2
        parent_ids = {e.parent_id for e in edges}
        assert parent_ids == {"overseer1", "overseer2"}

    def test_cascade_delete_parent(self, clean_db: Session):
        """Deleting an instance cascades to its relationship edges."""
        _make_instance(clean_db, "p")
        _make_instance(clean_db, "c")
        clean_db.add(InstanceRelationship(parent_id="p", child_id="c"))
        clean_db.commit()

        parent = clean_db.query(HopperInstance).get("p")
        clean_db.delete(parent)
        clean_db.commit()

        assert clean_db.query(InstanceRelationship).count() == 0

    def test_cascade_delete_child(self, clean_db: Session):
        _make_instance(clean_db, "p")
        _make_instance(clean_db, "c")
        clean_db.add(InstanceRelationship(parent_id="p", child_id="c"))
        clean_db.commit()

        child = clean_db.query(HopperInstance).get("c")
        clean_db.delete(child)
        clean_db.commit()

        assert clean_db.query(InstanceRelationship).count() == 0

    def test_fk_integrity(self, clean_db: Session):
        """Edge referencing non-existent instance should fail."""
        import pytest

        _make_instance(clean_db, "exists")
        clean_db.add(InstanceRelationship(parent_id="exists", child_id="ghost"))
        with pytest.raises(IntegrityError):
            clean_db.flush()


class TestConfigReader:
    def test_read_sub_instances(self, tmp_path):
        config = tmp_path / "config.yaml"
        config.write_text(
            "instance:\n  id: test\nsub_instances:\n"
            "- id: child1\n  scope: personal\n"
            "- id: child2\n  scope: company\n  description: My company\n"
        )

        from hopper.instances.config import read_sub_instances

        subs = read_sub_instances(tmp_path)
        assert len(subs) == 2
        assert subs[0]["id"] == "child1"
        assert subs[1]["description"] == "My company"

    def test_read_empty(self, tmp_path):
        config = tmp_path / "config.yaml"
        config.write_text("instance:\n  id: test\n")

        from hopper.instances.config import read_sub_instances

        assert read_sub_instances(tmp_path) == []

    def test_read_no_file(self, tmp_path):
        from hopper.instances.config import read_sub_instances

        assert read_sub_instances(tmp_path) == []

    def test_string_entries(self, tmp_path):
        config = tmp_path / "config.yaml"
        config.write_text("sub_instances:\n- child1\n- child2\n")

        from hopper.instances.config import read_sub_instances

        subs = read_sub_instances(tmp_path)
        assert len(subs) == 2
        assert subs[0] == {"id": "child1"}
