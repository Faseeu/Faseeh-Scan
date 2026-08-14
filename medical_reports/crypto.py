"""
Authenticated client-side encryption for the medical reports vault.

Design (password-based, zero-knowledge):

  * A random 32-byte MASTER KEY is generated once when the vault is created.
    Every report is encrypted with AES-256-GCM under this master key.
  * The master key is itself encrypted ("wrapped") with a KEY ENCRYPTION KEY
    (KEK) derived from the user's password using Argon2id (memory-hard KDF).
  * Changing the password only re-wraps the master key -- reports are NOT
    re-encrypted.
  * AES-256-GCM provides confidentiality AND tamper detection. A wrong password
    or a corrupted ciphertext fails verification with InvalidToken.

Nothing here ever sends data anywhere; it only transforms bytes.
"""

from __future__ import annotations

import json
import os
import secrets
from dataclasses import dataclass

from argon2.low_level import Type, hash_secret_raw
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# --- Tunables ---------------------------------------------------------------

# Argon2id parameters. These are deliberately heavy to resist offline brute
# force if the wrapped key file ever leaks. Tune down if mobile devices
# struggle; tune up over time as hardware improves.
ARGON2_TIME_COST = 4          # iterations
ARGON2_MEMORY_COST = 128 * 1024  # 128 MiB
ARGON2_PARALLELISM = 4
ARGON2_HASH_LEN = 32          # 256-bit KEK -> AES-256
ARGON2_SALT_LEN = 16

# AES-256-GCM uses a 96-bit (12-byte) nonce, which is the recommended length.
NONCE_LEN = 12
KEY_LEN = 32

# Magic header + version for the per-report encrypted file container.
CONTAINER_MAGIC = b"MRBK"     # Medical Reports BacKup
CONTAINER_VERSION = 1

# Filename for the password-wrapped master key.
KEYFILE_NAME = "vault.key"


class WrongPasswordError(Exception):
    """Raised when the password cannot unwrap the master key."""


class VaultCorruptedError(Exception):
    """Raised when a stored blob fails authentication / parsing."""


# --- Key derivation & wrapping ---------------------------------------------

def _derive_kek(password: str, salt: bytes) -> bytes:
    """Derive a 256-bit key-encryption key from the user's password."""
    return hash_secret_raw(
        secret=password.encode("utf-8"),
        salt=salt,
        time_cost=ARGON2_TIME_COST,
        memory_cost=ARGON2_MEMORY_COST,
        parallelism=ARGON2_PARALLELISM,
        hash_len=ARGON2_HASH_LEN,
        type=Type.ID,
    )


def _aes_gcm_encrypt(key: bytes, plaintext: bytes, aad: bytes | None = None) -> tuple[bytes, bytes]:
    nonce = secrets.token_bytes(NONCE_LEN)
    ct = AESGCM(key).encrypt(nonce, plaintext, aad)
    return nonce, ct


def _aes_gcm_decrypt(key: bytes, nonce: bytes, ciphertext: bytes, aad: bytes | None = None) -> bytes:
    return AESGCM(key).decrypt(nonce, ciphertext, aad)


@dataclass
class WrappedMasterKey:
    """The on-disk representation of the wrapped master key."""
    version: int
    salt: bytes
    nonce: bytes
    wrapped_key: bytes
    kdf_params: dict

    def to_json(self) -> str:
        return json.dumps({
            "version": self.version,
            "kdf": "argon2id",
            "kdf_params": self.kdf_params,
            "salt": self.salt.hex(),
            "nonce": self.nonce.hex(),
            "wrapped_key": self.wrapped_key.hex(),
        }, indent=2)

    @classmethod
    def from_json(cls, text: str) -> "WrappedMasterKey":
        try:
            d = json.loads(text)
            return cls(
                version=d["version"],
                salt=bytes.fromhex(d["salt"]),
                nonce=bytes.fromhex(d["nonce"]),
                wrapped_key=bytes.fromhex(d["wrapped_key"]),
                kdf_params=d.get("kdf_params", {}),
            )
        except (KeyError, ValueError, json.JSONDecodeError) as e:
            raise VaultCorruptedError(f"Malformed key file: {e}") from e


def create_wrapped_master_key(password: str) -> tuple[bytes, WrappedMasterKey]:
    """Generate a fresh master key and wrap it with the user's password.

    Returns (master_key, wrapped_master_key).
    """
    master_key = secrets.token_bytes(KEY_LEN)
    wrapped = wrap_master_key(master_key, password)
    return master_key, wrapped


def wrap_master_key(master_key: bytes, password: str) -> WrappedMasterKey:
    salt = secrets.token_bytes(ARGON2_SALT_LEN)
    kek = _derive_kek(password, salt)
    nonce, wrapped_key = _aes_gcm_encrypt(kek, master_key)
    return WrappedMasterKey(
        version=1,
        salt=salt,
        nonce=nonce,
        wrapped_key=wrapped_key,
        kdf_params={
            "time_cost": ARGON2_TIME_COST,
            "memory_cost": ARGON2_MEMORY_COST,
            "parallelism": ARGON2_PARALLELISM,
            "hash_len": ARGON2_HASH_LEN,
        },
    )


def unwrap_master_key(wrapped: WrappedMasterKey, password: str) -> bytes:
    """Recover the master key. Raises WrongPasswordError on bad password."""
    kek = _derive_kek(password, wrapped.salt)
    try:
        return _aes_gcm_decrypt(kek, wrapped.nonce, wrapped.wrapped_key)
    except Exception as e:
        raise WrongPasswordError("Incorrect password or corrupted vault key.") from e


# --- Per-report encryption -------------------------------------------------

def encrypt_report(master_key: bytes, plaintext: bytes) -> bytes:
    """Encrypt one report file. Returns a self-contained binary container."""
    nonce, ct = _aes_gcm_encrypt(master_key, plaintext)
    return CONTAINER_MAGIC + bytes([CONTAINER_VERSION]) + nonce + ct


def decrypt_report(master_key: bytes, container: bytes) -> bytes:
    """Decrypt a report container. Raises VaultCorruptedError if tampered."""
    header_len = len(CONTAINER_MAGIC) + 1 + NONCE_LEN
    if len(container) < header_len:
        raise VaultCorruptedError("Container too short.")
    if container[: len(CONTAINER_MAGIC)] != CONTAINER_MAGIC:
        raise VaultCorruptedError("Bad magic header.")
    version = container[len(CONTAINER_MAGIC)]
    if version != CONTAINER_VERSION:
        raise VaultCorruptedError(f"Unsupported container version {version}.")
    nonce = container[len(CONTAINER_MAGIC) + 1 : header_len]
    ct = container[header_len:]
    try:
        return _aes_gcm_decrypt(master_key, nonce, ct)
    except Exception as e:
        raise VaultCorruptedError("Report failed authentication.") from e


# --- Convenience: file IDs -------------------------------------------------

def new_report_id() -> str:
    """Short, collision-resistant id for a report (used as the file name)."""
    return secrets.token_hex(8)


def secure_delete(path: str) -> None:
    """Best-effort: overwrite then unlink. (SSD copy-on-write limits guarantees.)"""
    try:
        size = os.path.getsize(path)
        with open(path, "r+b") as f:
            f.write(secrets.token_bytes(size))
            f.flush()
            os.fsync(f.fileno())
    finally:
        try:
            os.remove(path)
        except OSError:
            pass
