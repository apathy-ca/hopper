"""
Hopper Instance model for multi-instance support.
"""

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import DateTime, Enum as SQLEnum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship, synonym
from sqlalchemy.types import JSON

from .base import Base, TimestampMixin
from .enums import HopperScope, InstanceStatus, InstanceType


class HopperInstance(Base, TimestampMixin):
    """Hopper Instance model for hierarchical instance management."""

    __tablename__ = "hopper_instances"

    # Primary key
    id: Mapped[str] = mapped_column(String(100), primary_key=True)

    # Instance details
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    scope: Mapped[HopperScope] = mapped_column(
        SQLEnum(HopperScope, name="hopper_scope", native_enum=False),
        nullable=False
    )

    # Instance type
    instance_type: Mapped[InstanceType] = mapped_column(
        SQLEnum(InstanceType, name="instance_type", native_enum=False),
        default=InstanceType.PERSISTENT,
        nullable=False
    )

    # Hierarchy
    parent_id: Mapped[str | None] = mapped_column(
        String(100),
        ForeignKey("hopper_instances.id", ondelete="CASCADE"),
        nullable=True
    )

    # Configuration
    config: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"), nullable=True
    )

    # Runtime metadata - instance-specific runtime information
    # Note: Using 'runtime_metadata' instead of 'metadata' as 'metadata' is reserved by SQLAlchemy
    runtime_metadata: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"), nullable=True
    )

    # Lifecycle status
    status: Mapped[InstanceStatus] = mapped_column(
        SQLEnum(InstanceStatus, name="instance_status", native_enum=False),
        default=InstanceStatus.CREATED,
        nullable=False
    )

    # Lifecycle timestamps
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    stopped_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Additional metadata
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Deprecated - kept for backward compatibility
    terminated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Relationships
    parent: Mapped[Optional["HopperInstance"]] = relationship(
        "HopperInstance", remote_side=[id], back_populates="children"
    )
    children: Mapped[list["HopperInstance"]] = relationship(
        "HopperInstance", back_populates="parent"
    )
    tasks: Mapped[list["Task"]] = relationship("Task", back_populates="instance")

    def __init__(self, **kwargs):
        """Initialize with support for backward compatibility aliases."""
        # Handle backward compatibility aliases
        if "instance_id" in kwargs:
            kwargs["id"] = kwargs.pop("instance_id")
        if "parent_instance_id" in kwargs:
            kwargs["parent_id"] = kwargs.pop("parent_instance_id")

        # Auto-generate name from id if not provided
        if "name" not in kwargs and "id" in kwargs:
            kwargs["name"] = kwargs["id"]

        super().__init__(**kwargs)

    # Backward compatibility: Create synonyms that work with filter_by
    instance_id = synonym("id")
    parent_instance_id = synonym("parent_id")

    def __repr__(self) -> str:
        return f"<HopperInstance(id={self.id}, name={self.name}, scope={self.scope.value}, status={self.status.value})>"

    def get_ancestors(self) -> list["HopperInstance"]:
        """Get all ancestor instances in the hierarchy.

        Returns:
            List of ancestor instances from immediate parent to root.
        """
        ancestors = []
        current = self.parent
        while current is not None:
            ancestors.append(current)
            current = current.parent
        return ancestors

    def get_descendants(self) -> list["HopperInstance"]:
        """Get all descendant instances in the hierarchy.

        Returns:
            List of all descendant instances (children, grandchildren, etc.).
        """
        descendants = []

        def collect_descendants(instance: "HopperInstance") -> None:
            for child in instance.children:
                descendants.append(child)
                collect_descendants(child)

        collect_descendants(self)
        return descendants

    def get_root(self) -> "HopperInstance":
        """Get the root instance in the hierarchy.

        Returns:
            The root instance (instance with no parent).
        """
        current = self
        while current.parent is not None:
            current = current.parent
        return current

    def is_root(self) -> bool:
        """Check if this instance is a root instance.

        Returns:
            True if this instance has no parent, False otherwise.
        """
        return self.parent_id is None

    def get_depth(self) -> int:
        """Get the depth of this instance in the hierarchy.

        Returns:
            Depth level (0 for root, 1 for immediate children, etc.).
        """
        depth = 0
        current = self.parent
        while current is not None:
            depth += 1
            current = current.parent
        return depth
