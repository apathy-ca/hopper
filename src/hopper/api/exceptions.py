"""
Custom exception classes and handlers for the Hopper API.

Provides standardized error responses and exception handling.
"""

from typing import Any

from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class HopperException(Exception):
    """Base exception class for all Hopper-specific exceptions."""

    def __init__(
        self,
        message: str,
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail: dict[str, Any] | None = None,
    ):
        self.message = message
        self.status_code = status_code
        self.detail = detail or {}
        super().__init__(self.message)


class NotFoundException(HopperException):
    """Exception raised when a resource is not found."""

    def __init__(self, resource: str, resource_id: Any):
        super().__init__(
            message=f"{resource} with id {resource_id} not found",
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"resource": resource, "id": str(resource_id)},
        )


class AlreadyExistsException(HopperException):
    """Exception raised when attempting to create a resource that already exists."""

    def __init__(self, resource: str, identifier: str):
        super().__init__(
            message=f"{resource} with identifier {identifier} already exists",
            status_code=status.HTTP_409_CONFLICT,
            detail={"resource": resource, "identifier": identifier},
        )


class ValidationException(HopperException):
    """Exception raised when validation fails."""

    def __init__(self, message: str, field: str | None = None):
        detail = {"field": field} if field else {}
        super().__init__(
            message=message,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=detail,
        )


class UnauthorizedException(HopperException):
    """Exception raised when authentication fails."""

    def __init__(self, message: str = "Authentication required"):
        super().__init__(
            message=message,
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={},
        )


class ForbiddenException(HopperException):
    """Exception raised when user lacks permission for an action."""

    def __init__(self, message: str = "Permission denied"):
        super().__init__(
            message=message,
            status_code=status.HTTP_403_FORBIDDEN,
            detail={},
        )


class InvalidStateTransitionException(HopperException):
    """Exception raised when attempting an invalid state transition."""

    def __init__(self, current_state: str, target_state: str):
        super().__init__(
            message=f"Invalid state transition from {current_state} to {target_state}",
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"current_state": current_state, "target_state": target_state},
        )


class DatabaseException(HopperException):
    """Exception raised for database-related errors."""

    def __init__(self, message: str, operation: str | None = None):
        detail = {"operation": operation} if operation else {}
        super().__init__(
            message=message,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=detail,
        )


async def hopper_exception_handler(request: Request, exc: HopperException) -> JSONResponse:
    """
    Exception handler for HopperException and its subclasses.

    Args:
        request: The FastAPI request
        exc: The exception instance

    Returns:
        JSONResponse with standardized error format
    """
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "message": exc.message,
                "status_code": exc.status_code,
                "detail": exc.detail,
            }
        },
    )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """
    Exception handler for request validation errors.

    Args:
        request: The FastAPI request
        exc: The validation error exception

    Returns:
        JSONResponse with validation error details
    """
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": {
                "message": "Validation error",
                "status_code": status.HTTP_422_UNPROCESSABLE_ENTITY,
                "detail": {"validation_errors": exc.errors()},
            }
        },
    )
