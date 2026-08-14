"""RapidOCR backend (PaddleOCR models via ONNX Runtime).

~50-80 MB, CPU only, no system binary — the best cross-platform default.
Install with: pip install rapidocr-onnxruntime
"""

from __future__ import annotations

from .base import register


@register
class RapidOcrEngine:
    id = "rapidocr"
    display_name = "RapidOCR (on-device)"

    def __init__(self):
        self._ocr = None

    def is_available(self) -> bool:
        try:
            from rapidocr_onnxruntime import RapidOCR  # type: ignore
            self._Cls = RapidOCR
            return True
        except Exception:
            return False

    def _engine(self):
        if self._ocr is None:
            from rapidocr_onnxruntime import RapidOCR  # type: ignore
            # English-only for v1.
            self._ocr = RapidOCR()
        return self._ocr

    def extract(self, data: bytes, content_type: str) -> str:
        import numpy as np
        engine = self._engine()
        arr = np.frombuffer(data, dtype=np.uint8)
        import cv2  # type: ignore
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        result, _ = engine(img)
        if not result:
            return ""
        return "\n".join(line[1] for line in result if len(line) > 1)
