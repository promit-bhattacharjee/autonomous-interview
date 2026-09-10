import base64
import hashlib
import os
from cryptography.fernet import Fernet


def _get_fernet() -> Fernet:
    """Retrieves or derives a 32-byte url-safe base64 Fernet key."""
    raw_secret = os.getenv("ENCRYPTION_SECRET_KEY", "default-ukvi-dev-secret-key-must-change-in-prod")
    # Derive a deterministic 32-byte key via SHA-256 and base64-encode it
    derived_bytes = hashlib.sha256(raw_secret.encode("utf-8")).digest()
    fernet_key = base64.urlsafe_b64encode(derived_bytes)
    return Fernet(fernet_key)


def encrypt_api_key(plaintext_key: str) -> str:
    """Encrypts a plaintext API key for storage in the vault."""
    if not plaintext_key:
        raise ValueError("Plaintext API key cannot be empty.")
    f = _get_fernet()
    encrypted_bytes = f.encrypt(plaintext_key.strip().encode("utf-8"))
    return encrypted_bytes.decode("utf-8")


def decrypt_api_key(ciphertext_key: str) -> str:
    """Decrypts a vault-stored API key back to plaintext strictly in-memory."""
    if not ciphertext_key:
        raise ValueError("Ciphertext API key cannot be empty.")
    f = _get_fernet()
    decrypted_bytes = f.decrypt(ciphertext_key.encode("utf-8"))
    return decrypted_bytes.decode("utf-8")


def mask_api_key(key: str) -> str:
    """Generates a safe preview mask of an API key (e.g., sk-...3x91)."""
    if not key or len(key) < 8:
        return "sk-...xxxx"
    return f"{key[:3]}...{key[-4:]}"
