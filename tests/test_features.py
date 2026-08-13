"""Feature tests: thumbnails, OCR pipeline, search over OCR text, settings."""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import cv2

from medical_reports.vault import Vault
from medical_reports.services import DocumentsService
from medical_reports.settings import Settings
from medical_reports.features.thumbnails import make_thumbnail
from medical_reports.features.ocr import available as ocr_available


def _text_image(path: Path, text="Hemoglobin 13.5 g/dL Date 2026"):
    img = np.full((500, 1000, 3), 255, dtype=np.uint8)
    cv2.putText(img, text, (40, 150), cv2.FONT_HERSHEY_SIMPLEX, 1.4, (0, 0, 0), 3)
    cv2.putText(img, "Total Cholesterol 180", (40, 280),
                cv2.FONT_HERSHEY_SIMPLEX, 1.4, (0, 0, 0), 3)
    cv2.imwrite(str(path), img)
    return path


def test_thumbnail_image():
    with tempfile.TemporaryDirectory() as d:
        p = _text_image(Path(d) / "a.jpg")
        thumb = make_thumbnail(p.read_bytes(), "image/jpeg")
        assert thumb is not None and thumb[:2] == b"\xff\xd8"  # JPEG magic
        assert len(thumb) < p.stat().st_size
        print("OK image thumbnail generated")


def test_ocr_and_search():
    engines = ocr_available()
    if not engines:
        print("SKIP ocr/search (no OCR engine installed)")
        return
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        v = Vault(d / "vault")
        v.create("pw")
        settings = Settings(ocr_enabled=True)
        docs = DocumentsService(v, settings)

        p = _text_image(d / "lab.jpg")
        meta = docs.add(p.read_bytes(), "lab.jpg", "image/jpeg")
        assert "ocr" in meta.artifacts, "OCR artifact should be created"
        # search finds the document by recognized text
        hits = docs.search("cholesterol")
        assert any(h.id == meta.id for h in hits), "search should match OCR text"
        # search by name still works
        assert any(h.id == meta.id for h in docs.search("lab"))
        print("OK OCR text indexed and searchable")


def test_thumbnail_artifact_created():
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        v = Vault(d / "vault")
        v.create("pw")
        docs = DocumentsService(v, Settings())
        p = _text_image(d / "img.jpg")
        meta = docs.add(p.read_bytes(), "img.jpg", "image/jpeg")
        assert "thumb" in meta.artifacts
        thumb = docs.get_artifact(meta.id, "thumb")
        assert thumb[:2] == b"\xff\xd8"
        print("OK thumbnail artifact attached on add")


def test_settings_save_load():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "settings.json"
        s = Settings(ocr_enabled=True, default_filter="gray")
        s.save(p)
        loaded = Settings.load(p)
        assert loaded.ocr_enabled is True
        assert loaded.default_filter == "gray"
        print("OK settings save/load")


if __name__ == "__main__":
    test_thumbnail_image()
    test_ocr_and_search()
    test_thumbnail_artifact_created()
    test_settings_save_load()
    print("\nFeature tests passed.")
