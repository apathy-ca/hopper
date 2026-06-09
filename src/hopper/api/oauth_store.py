"""OAuth 2.1 state storage for MCP authorization.

Persists OAuth clients, authorization codes, and access tokens in a single
JSON file at <storage_path>/oauth.json. Mirrors the file-backed pattern used
by mcp_tokens.py (atomic writes, 0o600 perms, singleton accessor).

Token formats:
    hpc_<hex>  — client_id (public client, no secret; PKCE required)
    hpa_<hex>  — authorization code (one-time-use, 10 min TTL)
    hpo_<hex>  — access token (1 hour TTL)

Audience binding: every code and access token records the `resource` URI it
was issued for. The MCP SSE endpoint must reject tokens whose resource does
not match the server's canonical URL (RFC 8707).
"""

from __future__ import annotations

import json
import os
import secrets
import tempfile
import time
from pathlib import Path

CLIENT_PREFIX = "hpc_"
CODE_PREFIX = "hpa_"
TOKEN_PREFIX = "hpo_"

OAUTH_FILE = "oauth.json"

AUTH_CODE_TTL_SECONDS = 600  # 10 minutes
ACCESS_TOKEN_TTL_SECONDS = 3600  # 1 hour


class OAuthStore:
    """File-backed store for OAuth clients, codes, and access tokens."""

    def __init__(self, storage_path: Path):
        self.storage_path = Path(storage_path)
        self.oauth_file = self.storage_path / OAUTH_FILE
        self.storage_path.mkdir(parents=True, exist_ok=True)

    # --- Clients ---

    def register_client(
        self,
        client_name: str,
        redirect_uris: list[str],
        grant_types: list[str] | None = None,
        response_types: list[str] | None = None,
        scope: str | None = None,
    ) -> dict:
        """Register a new public OAuth client (PKCE, no secret).

        Returns the full client record (including generated client_id).
        """
        if not redirect_uris:
            raise ValueError("redirect_uris must not be empty")

        client_id = f"{CLIENT_PREFIX}{secrets.token_hex(16)}"
        now = int(time.time())
        record = {
            "client_id": client_id,
            "client_name": client_name or "",
            "redirect_uris": list(redirect_uris),
            "grant_types": list(grant_types or ["authorization_code"]),
            "response_types": list(response_types or ["code"]),
            "scope": scope or "",
            "token_endpoint_auth_method": "none",  # public client
            "created_at": now,
        }

        data = self._load()
        data.setdefault("clients", {})[client_id] = record
        self._save(data)
        return record

    def get_client(self, client_id: str) -> dict | None:
        data = self._load()
        return data.get("clients", {}).get(client_id)

    # --- Authorization codes ---

    def create_auth_code(
        self,
        client_id: str,
        redirect_uri: str,
        did: str,
        instance: str,
        instance_path: str | None,
        scope: str,
        resource: str,
        code_challenge: str,
        code_challenge_method: str,
        state: str | None = None,
    ) -> str:
        code = f"{CODE_PREFIX}{secrets.token_hex(24)}"
        now = int(time.time())
        record = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "did": did,
            "instance": instance,
            "instance_path": instance_path,
            "scope": scope,
            "resource": resource,
            "code_challenge": code_challenge,
            "code_challenge_method": code_challenge_method,
            "state": state,
            "created_at": now,
            "expires_at": now + AUTH_CODE_TTL_SECONDS,
            "used": False,
        }
        data = self._load()
        data.setdefault("codes", {})[code] = record
        self._save(data)
        return code

    def consume_auth_code(self, code: str) -> dict | None:
        """Look up, mark used, and return an auth code record.

        Returns None if the code is unknown, already used, or expired.
        Single-use enforced: a second call returns None.
        """
        data = self._load()
        codes = data.setdefault("codes", {})
        record = codes.get(code)
        if not record:
            return None
        if record.get("used"):
            return None
        if record["expires_at"] < int(time.time()):
            return None
        record["used"] = True
        self._save(data)
        return record

    # --- Access tokens ---

    def create_access_token(
        self,
        client_id: str,
        did: str,
        instance: str,
        instance_path: str | None,
        scope: str,
        resource: str,
    ) -> tuple[str, int]:
        """Create an access token. Returns (token, expires_in_seconds)."""
        token = f"{TOKEN_PREFIX}{secrets.token_hex(32)}"
        now = int(time.time())
        record = {
            "client_id": client_id,
            "did": did,
            "instance": instance,
            "instance_path": instance_path,
            "scope": scope,
            "resource": resource,
            "created_at": now,
            "expires_at": now + ACCESS_TOKEN_TTL_SECONDS,
        }
        data = self._load()
        data.setdefault("tokens", {})[token] = record
        self._save(data)
        return token, ACCESS_TOKEN_TTL_SECONDS

    def lookup_access_token(self, token: str) -> dict | None:
        """Return the access token record if valid and unexpired, else None."""
        data = self._load()
        record = data.get("tokens", {}).get(token)
        if not record:
            return None
        if record["expires_at"] < int(time.time()):
            return None
        return record

    def revoke_access_token(self, token: str) -> bool:
        data = self._load()
        tokens = data.get("tokens", {})
        if token not in tokens:
            return False
        del tokens[token]
        self._save(data)
        return True

    # --- Persistence ---

    def _load(self) -> dict:
        if not self.oauth_file.exists():
            return {"clients": {}, "codes": {}, "tokens": {}}
        try:
            with open(self.oauth_file, encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            return {"clients": {}, "codes": {}, "tokens": {}}
        data.setdefault("clients", {})
        data.setdefault("codes", {})
        data.setdefault("tokens", {})
        return data

    def _save(self, data: dict) -> None:
        fd, temp_path = tempfile.mkstemp(
            dir=self.storage_path,
            prefix=".oauth_",
            suffix=".tmp",
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            os.chmod(temp_path, 0o600)
            os.rename(temp_path, self.oauth_file)
        except Exception:
            try:
                os.unlink(temp_path)
            except OSError:
                pass
            raise


_store: OAuthStore | None = None


def get_oauth_store(storage_path: Path | None = None) -> OAuthStore:
    """Get or create the OAuth store singleton.

    Uses HOPPER_SERVER_PATH env var or ~/.hopper when storage_path is None,
    matching the convention in mcp_tokens.get_token_store.
    """
    global _store
    if _store is None:
        if storage_path is None:
            env_path = os.getenv("HOPPER_SERVER_PATH")
            if env_path:
                storage_path = Path(env_path).expanduser()
            else:
                storage_path = Path.home() / ".hopper"
        _store = OAuthStore(storage_path)
    return _store


def reset_oauth_store() -> None:
    """Reset the singleton (used by tests)."""
    global _store
    _store = None
