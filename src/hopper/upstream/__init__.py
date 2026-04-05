"""Upstream sync module for Hopper.

Provides lightweight sync between Hopper instances via HTTP with DID authentication.
"""

from .did import DIDKey, generate_did_key, load_did_key, sign_request, verify_signature
from .client import UpstreamClient, UpstreamError, AuthenticationError
from .protocol import SyncRequest, SyncResponse, SyncTask
from .sync import sync_with_upstream, SyncResult

__all__ = [
    # DID
    "DIDKey",
    "generate_did_key",
    "load_did_key",
    "sign_request",
    "verify_signature",
    # Client
    "UpstreamClient",
    "UpstreamError",
    "AuthenticationError",
    # Protocol
    "SyncRequest",
    "SyncResponse",
    "SyncTask",
    # Sync
    "sync_with_upstream",
    "SyncResult",
]
