"""Core tests — run with: python -m tests.test_core"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from faseeh_scan import crypto
from faseeh_scan.vault import Vault
from faseeh_scan.services import DocumentsService, BackupService
from faseeh_scan.backends.local import LocalBackend
from faseeh_scan.features import capture as capture_mod
from faseeh_scan.features.processing import SUPPORTED as PROC_SUPPORTED


def test_report_roundtrip():
    key = b"0" * 32
    pt = b"%PDF-1.4 fake report contents \x00\x01\x02"
    ct = crypto.encrypt_report(key, pt)
    assert ct != pt
    assert crypto.decrypt_report(key, ct) == pt
    print("OK report roundtrip")


def test_wrong_password():
    _, wrapped = crypto.create_wrapped_master_key("correct horse")
    mk = crypto.unwrap_master_key(wrapped, "correct horse")
    assert len(mk) == 32
    try:
        crypto.unwrap_master_key(wrapped, "wrong")
        assert False, "should have raised"
    except crypto.WrongPasswordError:
        pass
    print("OK wrong password rejected")


def test_tamper_detection():
    key = b"1" * 32
    ct = bytearray(crypto.encrypt_report(key, b"hello"))
    ct[-1] ^= 0xFF
    try:
        crypto.decrypt_report(key, bytes(ct))
        assert False
    except crypto.VaultCorruptedError:
        pass
    print("OK tamper detected")


def test_vault_lifecycle():
    with tempfile.TemporaryDirectory() as d:
        v = Vault(Path(d) / "vault")
        v.create("mypassword")
        v.add_document(b"report one bytes", "blood-test.pdf", "application/pdf", tags=["lab"])
        v.add_document(b"report two bytes", "xray.jpg", "image/jpeg", note="chest")
        docs = v.list_documents()
        assert len(docs) == 2
        v.lock()
        try:
            v.unlock("nope")
            assert False
        except crypto.WrongPasswordError:
            pass
        v.unlock("mypassword")
        docs = v.list_documents()
        meta, data = v.get_document(docs[0].id)
        assert data in (b"report one bytes", b"report two bytes")
        # tags/note persisted
        assert any(d.tags == ["lab"] for d in docs)
        v.change_password("mypassword", "newpassword")
        v.lock()
        v.unlock("newpassword")
        assert len(v.list_documents()) == 2
        print("OK vault lifecycle")


def test_artifacts_and_search():
    with tempfile.TemporaryDirectory() as d:
        v = Vault(Path(d) / "vault")
        v.create("pw")
        svc = DocumentsService(v)
        doc = svc.add(b"hello", "invoice.pdf", "application/pdf", tags=["bills"])
        svc.put_artifact(doc.id, "ocr", b"total amount 1500", "text/plain")
        assert svc.has_artifact(doc.id, "ocr")
        # search by tag
        assert any(d.id == doc.id for d in svc.search("bills"))
        # search by OCR text
        assert any(d.id == doc.id for d in svc.search("1500"))
        print("OK artifacts + search")


def test_local_backend_roundtrip():
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        v = Vault(d / "vault")
        v.create("pw")
        v.add_document(b"data123", "a.pdf")
        be = LocalBackend(d / "backup")
        n = be.backup_vault(v)
        assert n >= 2
        v2 = Vault(d / "restored")
        v2.path.mkdir(parents=True)
        n2 = be.restore_vault(v2)
        assert n2 == n
        v2.unlock("pw")
        restored = v2.list_documents()
        assert len(restored) == 1
        _, data = v2.get_document(restored[0].id)
        assert data == b"data123"
        print("OK local backend backup/restore")


def test_backup_service():
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        v = Vault(d / "vault")
        v.create("pw")
        v.add_document(b"x", "a.pdf")
        svc = BackupService(v)
        be = LocalBackend(d / "backup")
        svc.use(be)
        assert svc.pending_count() == 1
        n = svc.backup()
        assert n >= 1
        assert svc.pending_count() == 0
        print("OK backup service")


def test_capture_registry_and_filepicker():
    providers = capture_mod.available()
    ids = {p.id for p in providers}
    assert "filepicker" in ids
    # default is filepicker (mlkit unavailable off-device)
    assert capture_mod.default() is not None
    assert capture_mod.default().id in ("filepicker", "mlkit")

    # filepicker capture via opener callback
    from faseeh_scan.features.capture.filepicker import FilePickerCapture
    fp = FilePickerCapture(opener=lambda multi: [])
    assert fp.is_available()
    res = fp.capture()
    assert res.is_empty
    print("OK capture registry + filepicker")


def test_processing_pipeline_available():
    # OpenCV is installed in the test env; confirm the pipeline at least loads.
    assert PROC_SUPPORTED, "opencv should be installed in test env"
    import numpy as np
    from faseeh_scan.features.processing import pipeline as P
    # A white "page" on a dark background.
    img = np.zeros((800, 600, 3), dtype=np.uint8)
    img[100:700, 80:520] = 245
    for f in ("original", "color", "gray", "bw", "magic"):
        out = P.process_image(img, P.ProcessOptions(filter=f, auto_crop=False))
        assert out is not None and out.size > 0
    print("OK processing pipeline filters")


if __name__ == "__main__":
    test_report_roundtrip()
    test_wrong_password()
    test_tamper_detection()
    test_vault_lifecycle()
    test_artifacts_and_search()
    test_local_backend_roundtrip()
    test_backup_service()
    test_capture_registry_and_filepicker()
    test_processing_pipeline_available()
    print("\nAll core tests passed.")
