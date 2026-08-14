"""Capture providers. Importing this package registers all built-in backends."""

from . import filepicker  # noqa: F401  (registers FilePickerCapture)
from . import mlkit  # noqa: F401  (registers MlKitCapture when on device)
from .base import (
    CaptureProvider,
    CaptureResult,
    CapturedPage,
    available,
    default,
    register,
)
from .service import CaptureService

__all__ = [
    "CaptureProvider",
    "CaptureResult",
    "CapturedPage",
    "CaptureService",
    "available",
    "default",
    "register",
]
