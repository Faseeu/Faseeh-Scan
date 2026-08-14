"""Thumbnail generation for documents.

For images, we downscale with OpenCV. For PDFs, we render the first page if a
PDF renderer is available (pypdfium2), otherwise we return None and the UI
shows a generic PDF icon. All optional and lazy-imported.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

try:
    import cv2  # type: ignore
    import numpy as np  # type: ignore
    _CV = True
except Exception:
    _CV = False

THUMB_SIZE = 512


def make_thumbnail(data: bytes, content_type: str) -> Optional[bytes]:
    """Return JPEG thumbnail bytes, or None if not possible."""
    if not _CV:
        return None
    try:
        if content_type.startswith("image/"):
            return _image_thumbnail(data)
        if content_type == "application/pdf":
            return _pdf_thumbnail(data)
    except Exception:
        return None
    return None


def _image_thumbnail(data: bytes) -> Optional[bytes]:
    arr = np.frombuffer(data, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        return None
    return _encode_thumb(img)


def _pdf_thumbnail(data: bytes) -> Optional[bytes]:
    try:
        import pypdfium2 as pdfium  # type: ignore
    except Exception:
        return None
    pdf = pdfium.PdfDocument(data)
    if len(pdf) == 0:
        return None
    page = pdf[0]
    # Render at a scale that gives roughly THUMB_SIZE on the long edge.
    bitmap = page.render(scale=1.5)
    pil = bitmap.to_pil()
    import numpy as np
    img = cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)
    return _encode_thumb(img)


def _encode_thumb(img) -> bytes:
    h, w = img.shape[:2]
    scale = THUMB_SIZE / max(h, w)
    if scale < 1:
        img = cv2.resize(img, (int(w * scale), int(h * scale)),
                         interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
    if not ok:
        raise RuntimeError("JPEG encode failed")
    return buf.tobytes()
