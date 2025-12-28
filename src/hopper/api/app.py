"""
FastAPI application factory for Hopper.

This module creates and configures the FastAPI application with:
- CORS configuration
- Middleware setup (logging, error handling)
- Health check endpoint
- OpenAPI customization
"""

import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from hopper.api.exceptions import (
    HopperException,
    hopper_exception_handler,
    validation_exception_handler,
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """
    Application lifespan context manager.

    Handles startup and shutdown events.
    """
    # Startup
    logger.info("Starting Hopper API")
    yield
    # Shutdown
    logger.info("Shutting down Hopper API")


def create_app() -> FastAPI:
    """
    Create and configure the FastAPI application.

    Returns:
        FastAPI: Configured FastAPI application instance
    """
    app = FastAPI(
        title="Hopper API",
        description="Universal, multi-instance, hierarchical task queue for human-AI collaborative workflows",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # Configure CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Configure based on environment in production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Add GZip compression
    app.add_middleware(GZipMiddleware, minimum_size=1000)

    # Add request timing middleware
    @app.middleware("http")
    async def add_process_time_header(request: Request, call_next):
        start_time = time.time()
        response = await call_next(request)
        process_time = time.time() - start_time
        response.headers["X-Process-Time"] = str(process_time)
        return response

    # Add logging middleware
    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        logger.info(f"{request.method} {request.url.path}")
        response = await call_next(request)
        logger.info(f"{request.method} {request.url.path} - {response.status_code}")
        return response

    # Register exception handlers
    from fastapi.exceptions import RequestValidationError

    app.add_exception_handler(HopperException, hopper_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)

    # Health check endpoint
    @app.get("/health", tags=["Health"])
    async def health_check():
        """
        Health check endpoint.

        Returns service status and basic information.
        """
        return {
            "status": "healthy",
            "service": "hopper-api",
            "version": "0.1.0",
        }

    # Root endpoint
    @app.get("/", tags=["Root"])
    async def root():
        """
        Root endpoint with API information.
        """
        return {
            "name": "Hopper API",
            "version": "0.1.0",
            "docs": "/docs",
            "health": "/health",
        }

    # Import and include routers
    from hopper.api.routes import tasks

    app.include_router(tasks.router, prefix="/api/v1", tags=["Tasks"])
    # from hopper.api.routes import projects, instances, auth
    # app.include_router(projects.router, prefix="/api/v1", tags=["Projects"])
    # app.include_router(instances.router, prefix="/api/v1", tags=["Instances"])
    # app.include_router(auth.router, prefix="/api/v1/auth", tags=["Authentication"])

    return app


# Create the application instance
app = create_app()
