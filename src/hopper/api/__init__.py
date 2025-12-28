"""
Hopper API module.

FastAPI-based REST API for the Hopper task queue system.
"""

from hopper.api.app import create_app, app

__version__ = "0.1.0"

__all__ = ["create_app", "app", "__version__"]
