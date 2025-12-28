"""
Hopper Instance repository for multi-instance management.
"""
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from hopper.models.hopper_instance import HopperInstance
from .base import BaseRepository


class HopperInstanceRepository(BaseRepository[HopperInstance]):
    """Repository for HopperInstance model with custom queries."""

    def __init__(self, session: Session):
        """Initialize HopperInstanceRepository."""
        super().__init__(HopperInstance, session)

    def get_instance_by_scope_and_name(
        self, scope: str, name: str
    ) -> Optional[HopperInstance]:
        """
        Get an instance by scope and name.

        Args:
            scope: Instance scope (GLOBAL, PROJECT, ORCHESTRATION)
            name: Instance name

        Returns:
            HopperInstance or None if not found
        """
        query = select(HopperInstance).where(
            HopperInstance.scope == scope, HopperInstance.name == name
        )
        result = self.session.execute(query)
        return result.scalar_one_or_none()

    def get_child_instances(self, parent_id: str) -> List[HopperInstance]:
        """
        Get all child instances of a parent.

        Args:
            parent_id: Parent instance ID

        Returns:
            List of child instances
        """
        return self.filter(filters={"parent_id": parent_id})

    def get_instances_by_scope(self, scope: str) -> List[HopperInstance]:
        """
        Get all instances with a specific scope.

        Args:
            scope: Instance scope (GLOBAL, PROJECT, ORCHESTRATION)

        Returns:
            List of instances with the scope
        """
        return self.filter(filters={"scope": scope})

    def get_active_instances(self) -> List[HopperInstance]:
        """
        Get all active instances.

        Returns:
            List of active instances
        """
        return self.filter(filters={"status": "active"})

    def get_instance_hierarchy(self, instance_id: str) -> List[HopperInstance]:
        """
        Get the full hierarchy for an instance (ancestors and descendants).

        Args:
            instance_id: Instance ID

        Returns:
            List of instances in the hierarchy
        """
        # Start with the instance itself
        instance = self.get(instance_id)
        if not instance:
            return []

        hierarchy = [instance]

        # Get ancestors (walk up the tree)
        current = instance
        while current.parent_id:
            parent = self.get(current.parent_id)
            if parent:
                hierarchy.insert(0, parent)
                current = parent
            else:
                break

        # Get descendants (walk down the tree)
        def get_all_children(parent_id: str) -> List[HopperInstance]:
            children = self.get_child_instances(parent_id)
            all_descendants = list(children)
            for child in children:
                all_descendants.extend(get_all_children(child.id))
            return all_descendants

        descendants = get_all_children(instance_id)
        hierarchy.extend(descendants)

        return hierarchy

    def terminate_instance(self, instance_id: str) -> Optional[HopperInstance]:
        """
        Terminate an instance.

        Args:
            instance_id: Instance ID

        Returns:
            Terminated instance or None if not found
        """
        from datetime import datetime

        return self.update(
            instance_id, status="terminated", terminated_at=datetime.utcnow()
        )

    def pause_instance(self, instance_id: str) -> Optional[HopperInstance]:
        """
        Pause an instance.

        Args:
            instance_id: Instance ID

        Returns:
            Paused instance or None if not found
        """
        return self.update(instance_id, status="paused")

    def resume_instance(self, instance_id: str) -> Optional[HopperInstance]:
        """
        Resume a paused instance.

        Args:
            instance_id: Instance ID

        Returns:
            Resumed instance or None if not found
        """
        return self.update(instance_id, status="active")

    def get_root_instances(self) -> List[HopperInstance]:
        """
        Get all root instances (instances with no parent).

        Returns:
            List of root instances
        """
        query = select(HopperInstance).where(HopperInstance.parent_id.is_(None))
        result = self.session.execute(query)
        return list(result.scalars().all())

    def count_children(self, parent_id: str) -> int:
        """
        Count the number of child instances for a parent.

        Args:
            parent_id: Parent instance ID

        Returns:
            Number of child instances
        """
        return self.count(filters={"parent_id": parent_id})
