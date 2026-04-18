"""
FastAPI application factory for Hopper.

This module creates and configures the FastAPI application with:
- CORS configuration
- Middleware setup (logging, error handling)
- Health check endpoint
- OpenAPI customization
"""

import logging
import os
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from hopper.api.exceptions import (
    HopperException,
    hopper_exception_handler,
    validation_exception_handler,
)
from hopper.api.mcp_sse import create_sse_server

logger = logging.getLogger(__name__)


def _get_upstream_storage_path() -> Path:
    env = os.getenv("HOPPER_UPSTREAM_STORAGE")
    if env:
        return Path(env).expanduser()
    return Path.home() / ".hopper" / "upstream-data"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Initialize upstream sync storage
    from hopper.upstream.server import configure_storage
    upstream_path = _get_upstream_storage_path()
    upstream_path.mkdir(parents=True, exist_ok=True)
    configure_storage(upstream_path)
    logger.info(f"Upstream storage: {upstream_path}")

    logger.info("Starting Hopper API")
    yield
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
        return {
            "name": "Hopper API",
            "version": "0.1.0",
            "docs": "/docs",
            "health": "/health",
            "mcp_sse": "/mcp/sse/",
            "mcp_register": "/mcp/register",
            "upstream_sync": "/upstream/sync",
        }

    # Import and include routers
    from hopper.api.routes import delegations, instances, learning, mcp_auth, tasks

    app.include_router(tasks.router, prefix="/api/v1", tags=["Tasks"])
    app.include_router(instances.router, prefix="/api/v1", tags=["Instances"])
    app.include_router(delegations.router, prefix="/api/v1", tags=["Delegations"])
    app.include_router(learning.router, prefix="/api/v1", tags=["Learning"])
    # MCP token registration (DID-authenticated)
    app.include_router(mcp_auth.router, tags=["MCP Auth"])
    # from hopper.api.routes import projects, auth
    # app.include_router(projects.router, prefix="/api/v1", tags=["Projects"])
    # app.include_router(auth.router, prefix="/api/v1/auth", tags=["Authentication"])

    # Mount MCP SSE server for Claude Web integration
    app.mount("/mcp", create_sse_server())

    # Mount upstream sync server (replaces standalone port 9000 service)
    from hopper.upstream.server import app as upstream_app
    app.mount("/upstream", upstream_app)

    return app


# Create the application instance
app = create_app()
