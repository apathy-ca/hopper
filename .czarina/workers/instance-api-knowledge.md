# Knowledge Base: instance-api

Custom knowledge for the Instance API worker, extracted from agent-knowledge library.

## FastAPI Async Endpoint Patterns

### Endpoint Structure with Dependency Injection

```python
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/api/v1/instances", tags=["instances"])

@router.post("/", response_model=InstanceResponse, status_code=status.HTTP_201_CREATED)
async def create_instance(
    request: InstanceCreate,
    db: AsyncSession = Depends(get_db),
) -> InstanceResponse:
    """Create a new Hopper instance.

    Args:
        request: Instance creation request
        db: Database session (injected)

    Returns:
        Created instance details

    Raises:
        HTTPException: If parent instance not found (404)
    """
    # Validate parent exists if specified
    if request.parent_id:
        parent = await instance_repo.get_by_id(db, request.parent_id)
        if not parent:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Parent instance {request.parent_id} not found"
            )

    instance = await instance_repo.create(db, request)
    return instance
```

### Database Session Pattern

```python
from collections.abc import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Get database session with automatic cleanup."""
    session_factory = get_session_factory()
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
```

## Error Handling Patterns

### HTTP Exception Handling

```python
from fastapi import HTTPException, status

# 404 - Not Found
raise HTTPException(
    status_code=status.HTTP_404_NOT_FOUND,
    detail=f"Instance {instance_id} not found"
)

# 400 - Bad Request
raise HTTPException(
    status_code=status.HTTP_400_BAD_REQUEST,
    detail="Cannot delete running instance. Stop it first."
)

# 409 - Conflict
raise HTTPException(
    status_code=status.HTTP_409_CONFLICT,
    detail=f"Instance {instance_id} is already in {status} state"
)

# 422 - Validation Error (automatic from Pydantic)
```

### Validation Error Response

```python
from fastapi.exceptions import RequestValidationError

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc):
    errors = []
    for error in exc.errors():
        errors.append({
            "field": " -> ".join(str(loc) for loc in error["loc"]),
            "message": error["msg"],
            "type": error["type"],
        })
    return JSONResponse(
        status_code=422,
        content={"error_type": "ValidationError", "errors": errors},
    )
```

## Pydantic Schema Patterns

### Request/Response Schemas

```python
from pydantic import BaseModel, Field
from enum import Enum
from datetime import datetime

class HopperScope(str, Enum):
    GLOBAL = "GLOBAL"
    PROJECT = "PROJECT"
    ORCHESTRATION = "ORCHESTRATION"

class InstanceCreate(BaseModel):
    """Request schema for creating an instance."""
    name: str = Field(..., min_length=1, max_length=255)
    scope: HopperScope
    parent_id: str | None = None
    config: dict = Field(default_factory=dict)
    description: str | None = None

class InstanceResponse(BaseModel):
    """Response schema for instance details."""
    id: str
    name: str
    scope: HopperScope
    status: InstanceStatus
    parent_id: str | None
    created_at: datetime

    class Config:
        from_attributes = True  # Enable ORM mode
```

### Enum Alignment

Ensure Pydantic enums match SQLAlchemy model enums exactly:

```python
# Check model enum values
from hopper.models.enums import HopperScope as ModelScope

# Pydantic enum must have same values
class HopperScope(str, Enum):
    GLOBAL = ModelScope.GLOBAL.value
    PROJECT = ModelScope.PROJECT.value
    # ...
```

## Lifecycle State Machine

```
                    ┌──────────┐
                    │ CREATED  │
                    └────┬─────┘
                         │ start()
                         ▼
                    ┌──────────┐
                    │ STARTING │
                    └────┬─────┘
                         │ ready
                         ▼
     ┌──────────────┬──────────┬──────────────┐
     │              │ RUNNING  │              │
     │              └────┬─────┘              │
     │ pause()           │ stop()             │
     ▼                   ▼                    │
┌──────────┐       ┌──────────┐              │
│ PAUSED   │       │ STOPPING │              │
└────┬─────┘       └────┬─────┘              │
     │ resume()         │ complete           │
     │                  ▼                    │
     │             ┌──────────┐              │
     └────────────▶│ STOPPED  │◀─────────────┘
                   └──────────┘
                        │ terminate()
                        ▼
                   ┌───────────┐
                   │TERMINATED │
                   └───────────┘
```

### Lifecycle Endpoint Implementation

```python
@router.post("/{instance_id}/start")
async def start_instance(
    instance_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Start an instance."""
    instance = await instance_repo.get_by_id(db, instance_id)
    if not instance:
        raise HTTPException(status_code=404, detail="Instance not found")

    if instance.status not in [InstanceStatus.CREATED, InstanceStatus.STOPPED]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot start instance in {instance.status} state"
        )

    instance.status = InstanceStatus.STARTING
    instance.started_at = datetime.utcnow()
    await db.commit()

    # Transition to RUNNING (in real system, would be async)
    instance.status = InstanceStatus.RUNNING
    await db.commit()

    return {"status": "started", "instance_id": instance_id}
```

## Testing API Endpoints

### Test Structure

```python
import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_create_instance(client: AsyncClient):
    """Test creating a new instance."""
    response = await client.post(
        "/api/v1/instances",
        json={
            "name": "test-instance",
            "scope": "PROJECT",
            "description": "Test instance"
        }
    )

    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "test-instance"
    assert data["scope"] == "PROJECT"
    assert data["status"] == "created"

@pytest.mark.asyncio
async def test_get_instance_not_found(client: AsyncClient):
    """Test 404 for non-existent instance."""
    response = await client.get("/api/v1/instances/nonexistent-id")
    assert response.status_code == 404
```

### Test Fixtures

```python
@pytest.fixture
async def test_instance(db: AsyncSession):
    """Create a test instance."""
    instance = HopperInstance(
        id=str(uuid4()),
        name="test-instance",
        scope=HopperScope.PROJECT,
        status=InstanceStatus.CREATED,
    )
    db.add(instance)
    await db.commit()
    return instance
```

## Best Practices

### DO
- Use proper HTTP status codes (201 for create, 204 for delete)
- Include OpenAPI documentation via docstrings
- Validate all inputs with Pydantic
- Use dependency injection for database sessions
- Return consistent error response format
- Test all error paths

### DON'T
- Expose internal errors to clients
- Use blocking operations in async endpoints
- Skip validation on IDs
- Forget to handle edge cases (empty lists, null values)
- Commit transactions manually (use session context manager)

## References

- Full async patterns: `/home/exedev/czarina/czarina-core/patterns/agent-knowledge/core-rules/python-standards/ASYNC_PATTERNS.md`
- Error handling: `/home/exedev/czarina/czarina-core/patterns/agent-knowledge/core-rules/python-standards/ERROR_HANDLING.md`
- Testing patterns: `/home/exedev/czarina/czarina-core/patterns/agent-knowledge/core-rules/testing/README.md`
