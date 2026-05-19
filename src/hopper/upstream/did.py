"""DID key management and signing for upstream sync.

Implements did:key method with ed25519 keys for request authentication.
"""

from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from nacl.encoding import RawEncoder
from nacl.signing import SigningKey, VerifyKey

# Multicodec prefix for ed25519-pub (0xed01)
ED25519_MULTICODEC = bytes([0xED, 0x01])

# Base58btc alphabet
BASE58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def _base58_encode(data: bytes) -> str:
    """Encode bytes to base58btc."""
    num = int.from_bytes(data, "big")
    if num == 0:
        return BASE58_ALPHABET[0]

    result = []
    while num > 0:
        num, rem = divmod(num, 58)
        result.append(BASE58_ALPHABET[rem])

    # Handle leading zeros
    for byte in data:
        if byte == 0:
            result.append(BASE58_ALPHABET[0])
        else:
            break

    return "".join(reversed(result))


def _base58_decode(s: str) -> bytes:
    """Decode base58btc string to bytes."""
    num = 0
    for char in s:
        num = num * 58 + BASE58_ALPHABET.index(char)

    # Count leading zeros
    leading_zeros = 0
    for char in s:
        if char == BASE58_ALPHABET[0]:
            leading_zeros += 1
        else:
            break

    # Convert to bytes
    result = []
    while num > 0:
        result.append(num & 0xFF)
        num >>= 8

    return bytes(leading_zeros) + bytes(reversed(result))


@dataclass
class DIDKey:
    """A DID key with signing and verification capabilities."""

    signing_key: SigningKey
    verify_key: VerifyKey
    did: str

    @classmethod
    def generate(cls) -> DIDKey:
        """Generate a new ed25519 DID key pair."""
        signing_key = SigningKey.generate()
        verify_key = signing_key.verify_key
        did = cls._public_key_to_did(bytes(verify_key))
        return cls(signing_key=signing_key, verify_key=verify_key, did=did)

    @classmethod
    def from_private_key(cls, private_key: bytes) -> DIDKey:
        """Load a DID key from a 32-byte private key seed."""
        signing_key = SigningKey(private_key)
        verify_key = signing_key.verify_key
        did = cls._public_key_to_did(bytes(verify_key))
        return cls(signing_key=signing_key, verify_key=verify_key, did=did)

    @classmethod
    def from_did(cls, did: str) -> VerifyKey:
        """Extract verify key from a DID (for verification only)."""
        if not did.startswith("did:key:z"):
            raise ValueError(f"Invalid did:key format: {did}")

        # Remove did:key:z prefix and decode
        encoded = did[9:]  # Skip "did:key:z"
        decoded = _base58_decode(encoded)

        # Verify multicodec prefix
        if decoded[:2] != ED25519_MULTICODEC:
            raise ValueError(f"Invalid multicodec prefix in DID: {did}")

        # Extract public key
        public_key = decoded[2:]
        return VerifyKey(public_key)

    @staticmethod
    def _public_key_to_did(public_key: bytes) -> str:
        """Convert a public key to did:key format."""
        # Prepend multicodec prefix
        multicodec_key = ED25519_MULTICODEC + public_key
        # Encode with base58btc (z prefix)
        encoded = _base58_encode(multicodec_key)
        return f"did:key:z{encoded}"

    def sign(self, message: bytes) -> bytes:
        """Sign a message with the private key."""
        signed = self.signing_key.sign(message, encoder=RawEncoder)
        return signed.signature

    def verify(self, message: bytes, signature: bytes) -> bool:
        """Verify a signature with the public key."""
        try:
            self.verify_key.verify(message, signature)
            return True
        except Exception:
            return False

    def to_bytes(self) -> bytes:
        """Export the private key seed for storage."""
        return bytes(self.signing_key)

    def save(self, path: Path) -> None:
        """Save the private key to a file."""
        import os
        import tempfile

        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".did-key-")
        try:
            os.chmod(fd, 0o600)
            os.write(fd, self.to_bytes())
            os.fsync(fd)
            os.close(fd)
            os.replace(tmp, path)
        except Exception:
            os.close(fd)
            os.unlink(tmp)
            raise

    @classmethod
    def load(cls, path: Path) -> DIDKey:
        """Load a DID key from a file."""
        private_key = path.read_bytes()
        return cls.from_private_key(private_key)


def generate_did_key() -> DIDKey:
    """Generate a new DID key pair."""
    return DIDKey.generate()


def load_did_key(path: Path) -> DIDKey:
    """Load a DID key from a file."""
    return DIDKey.load(path)


def sign_request(
    did_key: DIDKey,
    method: str,
    path: str,
    body: bytes | str | dict | None = None,
) -> str:
    """Sign an HTTP request and return the Authorization header value.

    Args:
        did_key: The DID key to sign with
        method: HTTP method (GET, POST, etc.)
        path: Request path
        body: Request body (bytes, string, or dict to be JSON-encoded)

    Returns:
        Authorization header value: "DID <did> <base64-signature>"
    """
    # Normalize body
    if body is None:
        body_bytes = b""
    elif isinstance(body, dict):
        body_bytes = json.dumps(body, separators=(",", ":"), sort_keys=True).encode()
    elif isinstance(body, str):
        body_bytes = body.encode()
    else:
        body_bytes = body

    # Create message to sign: METHOD + PATH + SHA256(body)
    body_hash = hashlib.sha256(body_bytes).hexdigest()
    message = f"{method.upper()}:{path}:{body_hash}".encode()

    # Sign
    signature = did_key.sign(message)
    sig_b64 = base64.b64encode(signature).decode()

    return f"DID {did_key.did} {sig_b64}"


def verify_signature(
    auth_header: str,
    method: str,
    path: str,
    body: bytes | str | dict | None = None,
) -> tuple[bool, str | None]:
    """Verify a signed request.

    Args:
        auth_header: Authorization header value
        method: HTTP method
        path: Request path
        body: Request body

    Returns:
        Tuple of (valid, did) where did is the verified DID or None if invalid
    """
    # Parse header
    if not auth_header.startswith("DID "):
        return False, None

    parts = auth_header[4:].split(" ", 1)
    if len(parts) != 2:
        return False, None

    did, sig_b64 = parts

    try:
        signature = base64.b64decode(sig_b64)
    except Exception:
        return False, None

    # Normalize body
    if body is None:
        body_bytes = b""
    elif isinstance(body, dict):
        body_bytes = json.dumps(body, separators=(",", ":"), sort_keys=True).encode()
    elif isinstance(body, str):
        body_bytes = body.encode()
    else:
        body_bytes = body

    # Recreate message
    body_hash = hashlib.sha256(body_bytes).hexdigest()
    message = f"{method.upper()}:{path}:{body_hash}".encode()

    # Extract verify key from DID and verify
    try:
        verify_key = DIDKey.from_did(did)
        verify_key.verify(message, signature)
        return True, did
    except Exception:
        return False, None
