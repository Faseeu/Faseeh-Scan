"""End-to-end test: capture service processes images, bundles a PDF, encrypts."""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import cv2

from medical_reports.vault import Vault
from medical_reports.services import DocumentsService
from medical_reports.features.capture import CaptureService, CaptureResult, CapturedPage
from medical_reports.features.processing import ProcessOptions


def _make_page(path: Path):
    # White "paper" on dark background with some text-like marks.
    img = np.zeros((1000, 800, 3), dtype=np.uint8)
    img[120:880, 90:710] = 240
    cv2.putText(img, "FASEEH SCAN TEST", (140, 300), cv2.FONT_HERSHEY_SIMPLEX,
                1.2, (20, 20, 20), 3)
    cv2.imwrite(str(path), img)
    return path


def test_scan_multi_page_pdf():
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        v = Vault(d / "vault")
        v.create("pw")
        docs = DocumentsService(v)
        svc = CaptureService(docs)

        pages = []
        for i in range(2):
            p = _make_page(d / f"p{i}.jpg")
            pages.append(CapturedPage(path=p, content_type="image/jpeg", source="camera"))

        result = CaptureResult(pages=pages)
        doc = svc.store_result(
            result, name="multi.pdf",
            process=True, options=ProcessOptions(filter="magic", auto_crop=True),
            as_pdf=True, ocr=False, source="camera",
        )
        assert doc.content_type == "application/pdf"
        assert doc.source == "camera"
        meta, data = docs.get(doc.id)
        assert data[:4] == b"%PDF"
        assert meta.size > 0
        print("OK multi-page scan -> encrypted PDF")


def test_scan_single_image_no_pdf():
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        v = Vault(d / "vault")
        v.create("pw")
        docs = DocumentsService(v)
        svc = CaptureService(docs)

        p = _make_page(d / "single.jpg")
        result = CaptureResult(pages=[CapturedPage(path=p, content_type="image/jpeg")])
        doc = svc.store_result(
            result, name="single.jpg", process=False, as_pdf=False, ocr=False)
        assert doc.content_type == "image/jpeg"
        print("OK single image stored as-is")


def test_import_files_as_is():
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        v = Vault(d / "vault")
        v.create("pw")
        docs = DocumentsService(v)
        svc = CaptureService(docs)
        f = d / "doc.pdf"
        f.write_bytes(b"%PDF-1.4 original bytes")
        added = svc.import_files([f])
        assert len(added) == 1
        _, data = docs.get(added[0].id)
        assert data == b"%PDF-1.4 original bytes"
        print("OK file imported as-is (no processing)")


if __name__ == "__main__":
    test_scan_multi_page_pdf()
    test_scan_single_image_no_pdf()
    test_import_files_as_is()
    print("\nScan flow tests passed.")
