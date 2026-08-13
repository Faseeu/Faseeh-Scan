"""Fallback capture: the system file picker (gallery / files).

Works on every platform Flet supports — no native dependency. The UI wires
this up using Flet's FilePicker; here we define the adapter shape so the
service doesn't depend on Flet directly.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from .base import CapturedPage, CaptureResult, register


@register
class FilePickerCapture:
    id = "filepicker"
    display_name = "Choose from device"

    def __init__(self, opener: Optional[Callable[..., object]] = None):
        # opener is a UI-provided callback that returns a list of paths.
        self._opener = opener

    def is_available(self) -> bool:
        return True

    def set_opener(self, opener: Callable[..., object]) -> None:
        self._opener = opener

    def capture(self, ui_context=None, *, multi_page: bool = True) -> CaptureResult:
        if self._opener is None:
            raise RuntimeError("File picker opener has not been provided by the UI.")
        paths = self._opener(multi=multi_page) or []
        pages = []
        for p in paths:
            path = Path(p)
            ctype = _guess_type(path)
            pages.append(CapturedPage(path=path, content_type=ctype, source="import"))
        return CaptureResult(pages=pages)


def _guess_type(path: Path) -> str:
    ext = path.suffix.lower()
    return {
        ".pdf": "application/pdf",
        ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".png": "image/png", ".webp": "image/webp",
        ".doc": "application/msword",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".txt": "text/plain",
    }.get(ext, "application/octet-stream")
