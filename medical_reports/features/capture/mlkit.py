"""ML Kit Document Scanner capture (Android).

This provider is the primary scanner on Android. It wraps Google's on-device
document scanner, which is exposed to Flet through a small Flet extension
(Flutter package). We import the extension lazily:

    import faseeh_scan_mlkit as mlkit

so this module is safe on desktop/web where the extension isn't installed —
is_available() simply returns False and the file picker fallback is used.

The Flet extension's API (defined in src/flutter/faseeh_scan_mlkit) exposes a
function `scan_document(page, page_limit=...) -> ScanResult` with `.pdf_path`
and `.image_paths`. That package is listed as an *optional* dependency and
declared under [tool.flet.flutter.pubspec.dependencies] in pyproject.toml when
building the Android APK. Until the extension package is built/published, this
backend reports unavailable; the app still works via the file picker.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from .base import CapturedPage, CaptureResult, register


@register
class MlKitCapture:
    id = "mlkit"
    display_name = "Scan with camera"

    def __init__(self):
        self._mod = None

    def _import(self):
        if self._mod is not None:
            return self._mod
        try:
            import faseeh_scan_mlkit as mod  # type: ignore
            self._mod = mod
        except Exception:
            self._mod = None
        return self._mod

    def is_available(self) -> bool:
        # Also gate to Android; the extension is a no-op elsewhere.
        import platform
        if platform.system().lower() != "android":
            return False
        return self._import() is not None

    def capture(self, ui_context=None, *, multi_page: bool = True) -> CaptureResult:
        mod = self._import()
        if mod is None:
            raise RuntimeError("ML Kit scanner extension is not available on this device.")
        result = mod.scan_document(ui_context, page_limit=0 if multi_page else 1)
        pages = []
        pdf_path: Optional[Path] = None
        if getattr(result, "pdf_path", None):
            pdf_path = Path(result.pdf_path)
        for ip in getattr(result, "image_paths", []) or []:
            pages.append(CapturedPage(path=Path(ip), content_type="image/jpeg",
                                      source="capture"))
        return CaptureResult(pages=pages, pdf_path=pdf_path)
