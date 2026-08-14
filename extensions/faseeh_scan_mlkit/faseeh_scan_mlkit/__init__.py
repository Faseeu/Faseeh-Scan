"""
Python side of the ML Kit document scanner Flet extension.

This is a thin wrapper; the real work happens in the Flutter package under
src/flutter/faseeh_scan_mlkit, which calls Google's on-device document
scanner and returns PDF/JPEG paths.

Usage:
    from faseeh_scan_mlkit import scan_document, ScanResult
    result = scan_document(page, page_limit=0)
    print(result.pdf_path, result.image_paths)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from flet.core.page import Page


@dataclass
class ScanResult:
    pdf_path: Optional[str] = None
    image_paths: list[str] = field(default_factory=list)


def scan_document(page: "Page", page_limit: int = 0) -> ScanResult:
    """Open the native ML Kit document scanner and return the result.

    page_limit: 0 = unlimited pages.
    """
    # The Flutter control registers a method/control with Flet. We send the
    # request and block on the page's result handler.
    result = page.invoke_method("faseeh_scan_mlkit", "scan",
                                {"page_limit": int(page_limit)})
    if not result:
        return ScanResult()
    return ScanResult(
        pdf_path=result.get("pdf_path"),
        image_paths=list(result.get("image_paths", [])),
    )


def is_available(page: "Page") -> bool:
    try:
        return bool(page.invoke_method("faseeh_scan_mlkit", "is_available", {}))
    except Exception:
        return False
