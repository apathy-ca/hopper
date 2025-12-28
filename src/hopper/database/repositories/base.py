"""
Base repository with generic CRUD operations.
"""

from typing import Any, Generic, TypeVar

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from hopper.models.base import Base

ModelType = TypeVar("ModelType", bound=Base)


class BaseRepository(Generic[ModelType]):
    """
    Base repository with common CRUD operations.

    Provides generic create, read, update, delete operations that can be
    inherited by model-specific repositories.
    """

    def __init__(self, model: type[ModelType], session: Session):
        """
        Initialize repository.

        Args:
            model: The SQLAlchemy model class
            session: Database session
        """
        self.model = model
        self.session = session

    def create(self, **kwargs: Any) -> ModelType:
        """
        Create a new model instance.

        Args:
            **kwargs: Model field values

        Returns:
            Created model instance
        """
        instance = self.model(**kwargs)
        self.session.add(instance)
        self.session.flush()  # Flush to get ID without committing
        return instance

    def get(self, id: Any) -> ModelType | None:
        """
        Get a model instance by ID.

        Args:
            id: Primary key value

        Returns:
            Model instance or None if not found
        """
        return self.session.get(self.model, id)

    def get_all(
        self, skip: int = 0, limit: int | None = None, order_by: str | None = None
    ) -> list[ModelType]:
        """
        Get all model instances with optional pagination and sorting.

        Args:
            skip: Number of records to skip
            limit: Maximum number of records to return
            order_by: Field name to sort by (prefix with - for descending)

        Returns:
            List of model instances
        """
        query = select(self.model)

        # Apply ordering
        if order_by:
            if order_by.startswith("-"):
                # Descending order
                field_name = order_by[1:]
                if hasattr(self.model, field_name):
                    query = query.order_by(getattr(self.model, field_name).desc())
            else:
                # Ascending order
                if hasattr(self.model, order_by):
                    query = query.order_by(getattr(self.model, order_by))

        # Apply pagination
        query = query.offset(skip)
        if limit:
            query = query.limit(limit)

        result = self.session.execute(query)
        return list(result.scalars().all())

    def filter(
        self,
        filters: dict[str, Any] | None = None,
        skip: int = 0,
        limit: int | None = None,
        order_by: str | None = None,
    ) -> list[ModelType]:
        """
        Get filtered model instances.

        Args:
            filters: Dictionary of field:value pairs to filter by
            skip: Number of records to skip
            limit: Maximum number of records to return
            order_by: Field name to sort by (prefix with - for descending)

        Returns:
            List of model instances matching filters
        """
        query = select(self.model)

        # Apply filters
        if filters:
            for field, value in filters.items():
                if hasattr(self.model, field):
                    query = query.where(getattr(self.model, field) == value)

        # Apply ordering
        if order_by:
            if order_by.startswith("-"):
                field_name = order_by[1:]
                if hasattr(self.model, field_name):
                    query = query.order_by(getattr(self.model, field_name).desc())
            else:
                if hasattr(self.model, order_by):
                    query = query.order_by(getattr(self.model, order_by))

        # Apply pagination
        query = query.offset(skip)
        if limit:
            query = query.limit(limit)

        result = self.session.execute(query)
        return list(result.scalars().all())

    def update(self, id: Any, **kwargs: Any) -> ModelType | None:
        """
        Update a model instance.

        Args:
            id: Primary key value
            **kwargs: Fields to update

        Returns:
            Updated model instance or None if not found
        """
        instance = self.get(id)
        if instance is None:
            return None

        for key, value in kwargs.items():
            if hasattr(instance, key):
                setattr(instance, key, value)

        self.session.flush()
        return instance

    def delete(self, id: Any) -> bool:
        """
        Delete a model instance.

        Args:
            id: Primary key value

        Returns:
            True if deleted, False if not found
        """
        instance = self.get(id)
        if instance is None:
            return False

        self.session.delete(instance)
        self.session.flush()
        return True

    def count(self, filters: dict[str, Any] | None = None) -> int:
        """
        Count model instances.

        Args:
            filters: Optional dictionary of field:value pairs to filter by

        Returns:
            Number of instances matching filters
        """
        query = select(func.count()).select_from(self.model)

        # Apply filters
        if filters:
            for field, value in filters.items():
                if hasattr(self.model, field):
                    query = query.where(getattr(self.model, field) == value)

        result = self.session.execute(query)
        return result.scalar() or 0

    def exists(self, id: Any) -> bool:
        """
        Check if a model instance exists.

        Args:
            id: Primary key value

        Returns:
            True if exists, False otherwise
        """
        return self.get(id) is not None

    def bulk_create(self, instances: list[dict[str, Any]]) -> list[ModelType]:
        """
        Create multiple instances efficiently.

        Args:
            instances: List of dictionaries with model field values

        Returns:
            List of created model instances
        """
        created = []
        for instance_data in instances:
            instance = self.model(**instance_data)
            self.session.add(instance)
            created.append(instance)

        self.session.flush()
        return created

    def bulk_update(self, updates: list[dict[str, Any]]) -> int:
        """
        Update multiple instances efficiently.

        Each update dict must include the 'id' field and the fields to update.

        Args:
            updates: List of dictionaries with id and fields to update

        Returns:
            Number of instances updated
        """
        updated_count = 0
        for update_data in updates:
            id_value = update_data.pop("id", None)
            if id_value and self.update(id_value, **update_data):
                updated_count += 1

        return updated_count

    def bulk_delete(self, ids: list[Any]) -> int:
        """
        Delete multiple instances efficiently.

        Args:
            ids: List of primary key values

        Returns:
            Number of instances deleted
        """
        deleted_count = 0
        for id_value in ids:
            if self.delete(id_value):
                deleted_count += 1

        return deleted_count
