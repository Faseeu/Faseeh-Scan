"""Tests for PDF page tools and trash/undo."""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from faseeh_scan.vault import Vault
from faseeh_scan.services import DocumentsService
from faseeh_scan.features.pdf_tools import (
    images_to_pdf_bytes, rearrange_pdf, delete_pages, rotate_pages,
    merge_pdfs, page_count,
)


def _make_pdf(num_pages: int = 3) -> bytes:
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import letter
    import io
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    for i in range(num_pages):
        c.drawString(100, 700, f"Page {i+1}")
        c.showPage()
    c.save()
    return buf.getvalue()


def test_page_count_and_rearrange():
    pdf = _make_pdf(4)
    assert page_count(pdf) == 4
    # reverse order, dropping page index 1
    reordered = rearrange_pdf(pdf, [3, 2, 0])
    assert page_count(reordered) == 3
    print("OK rearrange/delete pages")


def test_delete_and_rotate():
    pdf = _make_pdf(3)
    assert page_count(delete_pages(pdf, [0, 2])) == 1
    rotated = rotate_pages(pdf, 90, indices=[0])
    assert page_count(rotated) == 3
    print("OK delete/rotate pages")


def test_merge():
    a = _make_pdf(2)
    b = _make_pdf(3)
    merged = merge_pdfs([a, b])
    assert page_count(merged) == 5
    print("OK merge PDFs")


def test_images_to_pdf(tmp=None):
    import cv2, numpy as np
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        paths = []
        for i in range(3):
            img = np.full((400, 300, 3), 255, np.uint8)
            cv2.putText(img, f"p{i}", (50, 200), cv2.FONT_HERSHEY_SIMPLEX, 2, (0, 0, 0), 3)
            p = d / f"p{i}.jpg"
            cv2.imwrite(str(p), img)
            paths.append(p)
        data = images_to_pdf_bytes(paths, rotation_degrees=[0, 90, 0])
        assert data[:4] == b"%PDF"
        assert page_count(data) == 3
        print("OK images -> multi-page PDF with rotation")


def test_trash_restore_and_purge():
    with tempfile.TemporaryDirectory() as d:
        v = Vault(Path(d) / "v")
        v.create("pw")
        svc = DocumentsService(v)
        a = svc.add(b"a", "a.pdf")
        b = svc.add(b"b", "b.pdf")
        svc.trash(a.id)
        assert [d.id for d in svc.list()] == [b.id]
        assert [d.id for d in svc.list_trash()] == [a.id]
        svc.restore(a.id)
        assert {d.id for d in svc.list()} == {a.id, b.id}
        svc.trash(a.id)
        removed = svc.empty_trash()
        assert removed == 1
        assert [d.id for d in svc.list_trash()] == []
        print("OK trash / restore / empty trash")


def test_replace_blob_keeps_id():
    with tempfile.TemporaryDirectory() as d:
        v = Vault(Path(d) / "v")
        v.create("pw")
        svc = DocumentsService(v)
        doc = svc.add(b"old", "old.pdf", "application/pdf", make_thumbnail=False)
        new_pdf = _make_pdf(2)
        updated = svc.replace_blob(doc.id, new_pdf, name="new.pdf")
        assert updated.id == doc.id
        assert updated.name == "new.pdf"
        _, data = svc.get(doc.id)
        assert data == new_pdf
        print("OK replace blob (PDF edit) keeps identity")


if __name__ == "__main__":
    test_page_count_and_rearrange()
    test_delete_and_rotate()
    test_merge()
    test_images_to_pdf()
    test_trash_restore_and_purge()
    test_replace_blob_keeps_id()
    print("\nPDF/trash tests passed.")
