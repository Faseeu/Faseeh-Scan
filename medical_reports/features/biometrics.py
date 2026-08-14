"""
Pluggable biometric / device-local authentication.

On mobile, the `local_auth` Flutter plugin (wrapped by the
faseeh_local_auth Flet extension) unlocks the vault after the password has
already been set: the master key is wrapped with a random key stored in the
platform keystore/Keychain, so a fingerprint/face can unwrap it.

This module defines the interface used by the UI. A no-op implementation is
used on desktop/web where biometrics isn't available.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from flet.core.page import Page


class BiometricBackend(Protocol):
    id: str
    def is_available(self) -> bool: ...
    def can_check(self) -> bool: ...
    def authenticate(self, reason: str) -> bool: ...


@dataclass
class BiometricStatus:
    available: bool = False
    enabled: bool = False
    # True when a wrapped key has been stored and the user can unlock with it.
    enrolled: bool = False


class StubBiometric:
    """Desktop/web fallback: biometrics unavailable."""
    id = "stub"

    def is_available(self) -> bool:
        return False

    def can_check(self) -> bool:
        return False

    def authenticate(self, reason: str) -> bool:
        return False


_backend: BiometricBackend | None = None


def get_backend(page: "Page | None" = None) -> BiometricBackend:
    """Return the platform biometric backend, best-effort.

    Tries the faseeh_local_auth Flet extension when present (mobile builds);
    otherwise falls back to the stub. Never raises.
    """
    global _backend
    if _backend is not None:
        return _backend
    if page is not None:
        try:
            from faseeh_local_auth import LocalAuthBackend  # type: ignore
            b = LocalAuthBackend(page)
            if b.is_available():
                _backend = b
                return b
        except Exception:
            pass
    _backend = StubBiometric()
    return _backend
