"""Tesseract OCR backend (fallback). Requires the tesseract system binary.
Not used on Android by default; kept for desktop fallback.
"""

from __future__ import annotations

from .base import register


@register
class TesseractEngine:
    id = "tesseract"
    display_name = "Tesseract"

    def is_available(self) -> bool:
        try:
            import pytesseract  # type: ignore
            from PIL import Image  # noqa: F401
            pytesseract.get_tesseract_version()
            return True
        except Exception:
            return False

    def extract(self, data: bytes, content_type: str) -> str:
        import io
        import pytesseract  # type: ignore
        from PIL import Image
        img = Image.open(io.BytesIO(data))
        return pytesseract.image_to_string(img, lang="eng")
