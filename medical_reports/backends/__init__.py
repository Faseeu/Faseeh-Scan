"""Pluggable storage backends.

A backend only ever sees ENCRYPTED bytes. It does not know the password,
the master key, or any plaintext. This is what makes storing data in the
patient's own Google Drive safe: Google holds ciphertext only.
"""

from .base import StorageBackend
from .local import LocalBackend
from .gdrive import GoogleDriveBackend, GDriveNotConfigured

__all__ = [
    "StorageBackend",
    "LocalBackend",
    "GoogleDriveBackend",
    "GDriveNotConfigured",
]
