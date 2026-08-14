"""Pluggable OCR (English only in v1).

Backends register themselves; the service picks the best available one.
OCR output is stored as an encrypted 'ocr' artifact and used only for search.
"""

from .base import OcrEngine, available, default, register
from . import rapidocr  # noqa: F401
from . import tesseract  # noqa: F401

__all__ = ["OcrEngine", "available", "default", "register"]
