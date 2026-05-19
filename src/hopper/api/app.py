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
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from hopper.api.exceptions import (
    HopperException,
    hopper_exception_handler,
    validation_exception_handler,
)
from hopper.api.mcp_sse import create_sse_server, create_streamable_http_server, get_streamable_session_manager, get_stateless_session_manager

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
    shadow_sqlite_url = os.getenv("HOPPER_SHADOW_SQLITE_URL") or None
    configure_storage(upstream_path, shadow_sqlite_url=shadow_sqlite_url)
    logger.info(f"Upstream storage: {upstream_path}")
    if shadow_sqlite_url:
        logger.info(f"Revision shadow SQLite: {shadow_sqlite_url}")

    logger.info("Starting Hopper API")
    async with get_streamable_session_manager().run():
        async with get_stateless_session_manager().run():
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
            "mcp": "/mcp",
            "mcp_sse_legacy": "/mcp/sse/sse/",
            "upstream_sync": "/sync",
            "oauth_metadata": "/.well-known/oauth-authorization-server",
            "oauth_resource_metadata": "/.well-known/oauth-protected-resource",
        }

    # Import and include routers
    from hopper.api.routes import delegations, instances, learning, mcp_auth, oauth, tasks

    app.include_router(tasks.router, prefix="/api/v1", tags=["Tasks"])
    app.include_router(instances.router, prefix="/api/v1", tags=["Instances"])
    app.include_router(delegations.router, prefix="/api/v1", tags=["Delegations"])
    app.include_router(learning.router, prefix="/api/v1", tags=["Learning"])
    # MCP token registration (DID-authenticated)
    app.include_router(mcp_auth.router, tags=["MCP Auth"])
    # OAuth 2.1 + RFC 9728 metadata for Claude Web custom connector flow
    app.include_router(oauth.router)
    # from hopper.api.routes import projects, auth
    # app.include_router(projects.router, prefix="/api/v1", tags=["Projects"])
    # app.include_router(auth.router, prefix="/api/v1/auth", tags=["Authentication"])

    # Serve static assets (favicon, logo)
    static_dir = Path(__file__).parent / "static"
    if static_dir.exists():
        @app.get("/favicon.ico", include_in_schema=False)
        async def favicon():
            return FileResponse(static_dir / "favicon.ico")

        @app.get("/favicon.png", include_in_schema=False)
        async def favicon_png():
            return FileResponse(static_dir / "favicon-32.png", media_type="image/png")

        @app.get("/logo.png", include_in_schema=False)
        async def logo():
            return FileResponse(static_dir / "logo.png", media_type="image/png")

        @app.get("/icon-512.png", include_in_schema=False)
        async def icon_512():
            return FileResponse(static_dir / "icon-512.png", media_type="image/png")

        app.mount("/static", StaticFiles(directory=static_dir), name="static")

    # Streamable HTTP transport at /mcp (Claude Web 2024+, MCP 1.26+)
    app.mount("/mcp", create_streamable_http_server())
    # Legacy SSE transport at /mcp/sse/ (older clients)
    app.mount("/mcp/sse", create_sse_server())

    # Include upstream sync routes at root so DID-signed paths (/sync, /admin/*)
    # match the client's signature expectations without a mount prefix.
    from hopper.upstream.server import router as upstream_router
    app.include_router(upstream_router, tags=["Upstream"])

    return app


# Create the application instance
app = create_app()
