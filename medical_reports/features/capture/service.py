"""CaptureService orchestrates: capture -> process -> bundle -> add to vault.

It is UI-agnostic. The UI provides a CaptureProvider (native scanner or file
picker); the service runs the image processing and assembles a PDF, then hands
the bytes to DocumentsService. Heavy deps (cv2, img2pdf) are only touched when
processing is requested, so plain import-to-vault works with nothing installed.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Optional

from ...services import DocumentsService
from ...vault import DocumentMeta
from .base import CaptureProvider, CaptureResult
from . import base as capture_base
from ..processing.pipeline import (
    ProcessOptions, SUPPORTED as PROCESSING_SUPPORTED, images_to_pdf,
    load_image, process_image, save_image,
)


class CaptureService:
    def __init__(self, documents: DocumentsService):
        self.documents = documents

    # ---- provider selection ---------------------------------------------

    def available_providers(self) -> list[CaptureProvider]:
        return capture_base.available()

    def default_provider(self) -> Optional[CaptureProvider]:
        return capture_base.default()

    # ---- capture + store -------------------------------------------------

    def import_files(self, paths: list[str | Path], source: str = "import") -> list[DocumentMeta]:
        """Direct import with no processing; files stored as-is."""
        out = []
        for p in paths:
            p = Path(p)
            data = p.read_bytes()
            out.append(self.documents.add(
                data, p.name, _guess_type(p), source=source))
        return out

    def capture_to_vault(
        self,
        provider: CaptureProvider,
        *,
        name: str,
        multi_page: bool = True,
        process: bool = True,
        options: Optional[ProcessOptions] = None,
        as_pdf: bool = True,
        ocr: bool = False,
    ) -> DocumentMeta:
        """Run the capture flow and store the result as one document."""
        result: CaptureResult = provider.capture(multi_page=multi_page)
        if result.is_empty:
            raise RuntimeError("No pages were captured.")

        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)

            # If the provider already produced a PDF (ML Kit), keep it as-is.
            if result.pdf_path is not None:
                data = Path(result.pdf_path).read_bytes()
                doc = self.documents.add(data, name or "scan.pdf",
                                         "application/pdf", source="camera")
                if ocr:
                    self._run_ocr(doc.id, data, "application/pdf")
                return doc

            # Process each page image.
            processed = []
            for i, page in enumerate(result.pages):
                if page.content_type.startswith("image/"):
                    if process and PROCESSING_SUPPORTED:
                        img = load_image(page.path)
                        img = process_image(img, options or ProcessOptions())
                        out = tmp / f"page_{i:03d}.jpg"
                        save_image(img, out)
                        processed.append(out)
                    else:
                        processed.append(page.path)
                else:
                    processed.append(page.path)

            if as_pdf and any(p.suffix.lower() in (".jpg", ".jpeg", ".png") for p in processed):
                pdf_path = tmp / "scan.pdf"
                images_to_pdf(processed, pdf_path)
                data = pdf_path.read_bytes()
                doc = self.documents.add(data, name or "scan.pdf",
                                         "application/pdf", source="camera")
            elif len(processed) == 1:
                p = processed[0]
                data = p.read_bytes()
                doc = self.documents.add(data, name or p.name,
                                         _guess_type(p), source="camera")
            else:
                # Multiple non-PDF pages without PDF bundling: store first, rest?
                # For v1 we always bundle to PDF above, so this is defensive.
                pdf_path = tmp / "scan.pdf"
                images_to_pdf(processed, pdf_path)
                data = pdf_path.read_bytes()
                doc = self.documents.add(data, name or "scan.pdf",
                                         "application/pdf", source="camera")

            if ocr:
                self._run_ocr(doc.id, data, doc.content_type)
            return doc

    # ---- OCR -------------------------------------------------------------

    def _run_ocr(self, doc_id: str, data: bytes, content_type: str) -> None:
        from ..ocr import default as default_ocr
        engine = default_ocr()
        if engine is None:
            return
        try:
            text = engine.extract(data, content_type)
            if text.strip():
                self.documents.put_artifact(doc_id, "ocr", text.encode("utf-8"),
                                            "text/plain")
        except Exception:
            # OCR must never break capture/storage.
            pass


def _guess_type(p: Path) -> str:
    ext = p.suffix.lower()
    return {
        ".pdf": "application/pdf", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".png": "image/png", ".webp": "image/webp", ".txt": "text/plain",
    }.get(ext, "application/octet-stream")
