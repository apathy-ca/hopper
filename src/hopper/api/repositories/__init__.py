"""Repository layer for the REST API.

Repositories encapsulate records+revisions-backed persistence so routes can
stay thin. Methods are SYNC and operate on a SQLAlchemy ``Session`` — async
routes bridge to them via ``await db.run_sync(...)``.
"""

from hopper.api.repositories.record_tasks import RecordTaskRepository

__all__ = ["RecordTaskRepository"]
