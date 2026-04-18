"""MCP Bearer Token to DID mapping store.

Manages the mapping between Bearer tokens and DIDs for MCP authentication.
Tokens are stored in a JSON file with metadata including creation time,
optional labels, and last usage timestamps.

Token format: hpr_ + 32 random hex chars (e.g., hpr_a1b2c3d4e5f6...)

Usage:
    from hopper.api.mcp_tokens import get_token_store

    store = get_token_store(Path(".hopper"))

    # Generate a token for a DID
    token = store.generate_token("did:key:z6Mk...", label="claude-web")

    # Look up DID from token
    did = store.lookup(token)

    # Revoke a token
    store.revoke(token)

    # List tokens (optionally filtered by DID)
    tokens = store.list_tokens(did="did:key:z6Mk...")
"""

from __future__ import annotations

import json
import os
import secrets
import tempfile
import time
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


TOKEN_PREFIX = "hpr_"
TOKEN_FILE = "mcp_tokens.json"


class MCPTokenStore:
    """Store for MCP Bearer token to DID mappings.

    Tokens are stored in a JSON file at the specified storage path.
    File permissions are set to 0o600 for security.

    Attributes:
        storage_path: Path to the storage directory (e.g., .hopper/)
        token_file: Full path to the tokens JSON file
    """

    def __init__(self, storage_path: Path):
        """Initialize with path to storage directory.

        Args:
            storage_path: Directory where the token file will be stored.
                         Creates the directory if it doesn't exist.
        """
        self.storage_path = Path(storage_path)
        self.token_file = self.storage_path / TOKEN_FILE

        # Ensure storage directory exists
        self.storage_path.mkdir(parents=True, exist_ok=True)

    def generate_token(
        self,
        did: str,
        label: str = "",
        instance: str = "default",
        instance_path: str | None = None,
    ) -> str:
        """Generate and store a new token for a DID.

        Creates a new token with the hpr_ prefix followed by 32 random
        hex characters (64 hex digits total for the random part).

        Args:
            did: The DID to associate with this token (e.g., "did:key:z6Mk...")
            label: Optional user-provided label for identifying the token
            instance: Instance name/identifier (e.g., "work", "personal")
            instance_path: Path to the instance storage directory (e.g., "/path/to/.hopper")

        Returns:
            The generated token string (e.g., "hpr_a1b2c3d4...")
        """
        # Generate token: prefix + 32 random bytes as hex (64 hex chars)
        random_part = secrets.token_hex(32)
        token = f"{TOKEN_PREFIX}{random_part}"

        # Load existing data
        data = self._load()

        # Store token metadata
        now = int(time.time())
        data[token] = {
            "did": did,
            "instance": instance,
            "instance_path": instance_path,
            "created_at": now,
            "label": label,
            "last_used_at": now,
        }

        # Save atomically
        self._save(data)

        return token

    def lookup(self, token: str) -> str | None:
        """Look up DID for a token.

        Also updates the last_used_at timestamp for the token.

        Args:
            token: The token to look up

        Returns:
            The associated DID if found, None otherwise
        """
        data = self._load()

        if token not in data:
            return None

        # Update last_used_at
        data[token]["last_used_at"] = int(time.time())
        self._save(data)

        return data[token]["did"]

    def lookup_full(self, token: str) -> dict | None:
        """Look up full token metadata including DID and instance.

        Also updates the last_used_at timestamp for the token.

        Args:
            token: The token to look up

        Returns:
            Dict with keys: did, instance, instance_path
            Or None if not found.
        """
        data = self._load()

        if token not in data:
            return None

        # Update last_used_at
        data[token]["last_used_at"] = int(time.time())
        self._save(data)

        metadata = data[token]
        return {
            "did": metadata["did"],
            "instance": metadata.get("instance", "default"),
            "instance_path": metadata.get("instance_path"),
        }

    def revoke(self, token: str) -> bool:
        """Revoke a token.

        Removes the token from the store entirely.

        Args:
            token: The token to revoke

        Returns:
            True if the token was found and revoked, False if not found
        """
        data = self._load()

        if token not in data:
            return False

        del data[token]
        self._save(data)

        return True

    def list_tokens(self, did: str | None = None) -> list[dict]:
        """List tokens, optionally filtered by DID.

        Returns metadata about tokens without exposing the full token.
        The token_prefix field contains only the first 12 characters
        of the token for identification purposes.

        Args:
            did: Optional DID to filter by. If None, returns all tokens.

        Returns:
            List of token metadata dicts with keys:
            - token_prefix: First 12 chars of token (e.g., "hpr_a1b2c3d4")
            - did: The associated DID
            - instance: Instance name/identifier
            - instance_path: Path to instance storage (may be None)
            - created_at: Unix timestamp of creation
            - label: User-provided label (may be empty)
            - last_used_at: Unix timestamp of last use
        """
        data = self._load()

        result = []
        for token, metadata in data.items():
            if did is not None and metadata["did"] != did:
                continue

            result.append({
                "token_prefix": token[:12],  # hpr_ + 8 hex chars
                "did": metadata["did"],
                "instance": metadata.get("instance", "default"),
                "instance_path": metadata.get("instance_path"),
                "created_at": metadata["created_at"],
                "label": metadata.get("label", ""),
                "last_used_at": metadata.get("last_used_at", metadata["created_at"]),
            })

        # Sort by created_at descending (newest first)
        result.sort(key=lambda x: x["created_at"], reverse=True)

        return result

    def revoke_by_prefix(self, token_prefix: str, did: str) -> bool:
        """Revoke a token by its prefix (first 12 characters).

        The token must be owned by the specified DID to be revoked.

        Args:
            token_prefix: First 12 characters of the token (e.g., "hpr_a1b2c3d4")
            did: The DID that must own the token for revocation to succeed

        Returns:
            True if a matching token owned by the DID was found and revoked,
            False otherwise
        """
        data = self._load()

        # Find token matching the prefix owned by the specified DID
        for token, metadata in list(data.items()):
            if token.startswith(token_prefix) and metadata["did"] == did:
                del data[token]
                self._save(data)
                return True

        return False

    def _load(self) -> dict:
        """Load tokens from file.

        Returns:
            Dict mapping tokens to their metadata, or empty dict if
            file doesn't exist or is invalid.
        """
        if not self.token_file.exists():
            return {}

        try:
            with open(self.token_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            # Return empty dict on error - don't crash
            return {}

    def _save(self, data: dict):
        """Save tokens to file with atomic write.

        Uses a temporary file and rename to ensure atomic writes.
        Sets file permissions to 0o600 (owner read/write only).

        Args:
            data: The token data dict to save
        """
        # Write to temp file in the same directory (for atomic rename)
        fd, temp_path = tempfile.mkstemp(
            dir=self.storage_path,
            prefix=".mcp_tokens_",
            suffix=".tmp",
        )

        try:
            # Write data
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)

            # Set permissions before rename
            os.chmod(temp_path, 0o600)

            # Atomic rename
            os.rename(temp_path, self.token_file)
        except Exception:
            # Clean up temp file on error
            try:
                os.unlink(temp_path)
            except OSError:
                pass
            raise


# Singleton instance
_store: MCPTokenStore | None = None


def get_token_store(storage_path: Path | None = None) -> MCPTokenStore:
    """Get or create the token store singleton.

    If storage_path is not provided, uses HOPPER_SERVER_PATH environment
    variable, falling back to ~/.hopper-server/ as default.

    Args:
        storage_path: Path to storage directory. If None, uses environment
                     variable or default.

    Returns:
        The MCPTokenStore singleton instance.

    Example:
        # Uses HOPPER_SERVER_PATH env var or ~/.hopper-server/
        store = get_token_store()

        # Or specify explicit path
        store = get_token_store(Path(".hopper"))
    """
    global _store

    if _store is None:
        if storage_path is None:
            env_path = os.getenv("HOPPER_SERVER_PATH")
            if env_path:
                storage_path = Path(env_path).expanduser()
            else:
                storage_path = Path.home() / ".hopper-server"
        _store = MCPTokenStore(storage_path)

    return _store
