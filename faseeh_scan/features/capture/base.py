"""Capture: turn paper into an image/PDF.

A CaptureProvider opens some UI (native scanner, camera, or file picker) and
returns one or more files. It does NO encryption — the service handles that.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional, Protocol


@dataclass
class CapturedPage:
    path: Path                      # path to the image/PDF on disk
    content_type: str
    source: str = "capture"         # "capture" | "import"


@dataclass
class CaptureResult:
    pages: list[CapturedPage] = field(default_factory=list)
    # When the provider already produced a PDF (e.g. ML Kit), this is it.
    pdf_path: Optional[Path] = None

    @property
    def is_empty(self) -> bool:
        return not self.pdf_path and not self.pages


class CaptureProvider(Protocol):
    id: str
    display_name: str

    def is_available(self) -> bool: ...
    def capture(self, ui_context=None, *, multi_page: bool = True) -> CaptureResult: ...


_REGISTRY: dict[str, type[CaptureProvider]] = {}


def register(cls: type[CaptureProvider]) -> type[CaptureProvider]:
    _REGISTRY[cls.id] = cls
    return cls


def available() -> list[CaptureProvider]:
    out = []
    for cls in _REGISTRY.values():
        try:
            inst = cls()
            if inst.is_available():
                out.append(inst)
        except Exception:
            continue
    return out


def default() -> Optional[CaptureProvider]:
    """Best capture provider: native scanner first, then picker."""
    by_id = {p.id: p for p in available()}
    for preferred in ("mlkit", "filepicker"):
        if preferred in by_id:
            return by_id[preferred]
    return None
