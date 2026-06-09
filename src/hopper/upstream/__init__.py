"""Upstream sync module for Hopper.

Provides lightweight sync between Hopper instances via HTTP with DID authentication.
"""

from .client import AuthenticationError, UpstreamClient, UpstreamError
from .did import DIDKey, generate_did_key, load_did_key, sign_request, verify_signature
from .protocol import SyncRequest, SyncResponse, SyncTask
from .sync import SyncResult, sync_with_upstream

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
