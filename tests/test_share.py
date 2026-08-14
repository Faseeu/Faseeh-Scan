"""Tests for incoming-share routing and the share service."""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from faseeh_scan.vault import Vault
from faseeh_scan.services import DocumentsService
from faseeh_scan.features.share_intent import ShareIntentService, mime_to_content_type


def test_callback_and_drain():
    svc = ShareIntentService()
    received = []
    svc.on_incoming(lambda files: received.extend(files))
    svc.set_incoming_files([{"path": "/tmp/a.pdf", "mime": "application/pdf"}])
    assert len(received) == 1
    assert svc.has_pending()
    items = svc.drain()
    assert items and items[0].path == "/tmp/a.pdf"
    assert not svc.has_pending()
    print("OK share service callback + drain")


def test_mime_fallback():
    assert mime_to_content_type("image/png", "x.JPG") == "image/png"
    assert mime_to_content_type("", "x.pdf") == "application/pdf"
    assert mime_to_content_type("", "x.bin") == "application/octet-stream"
    print("OK mime/content-type mapping")


def test_ingest_shared_files(tmp_path=None):
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        f = d / "shared.pdf"
        f.write_bytes(b"%PDF shared bytes")
        v = Vault(d / "vault")
        v.create("pw")
        docs = DocumentsService(v)
        svc = ShareIntentService()
        added = []
        svc.set_incoming_files([{"path": str(f), "mime": "application/pdf"}])
        for item in svc.drain():
            p = Path(item.path)
            docs.add(p.read_bytes(), p.name,
                     mime_to_content_type(item.mime, item.path), source="share")
            added.append(p.name)
        assert added == ["shared.pdf"]
        all_docs = docs.list()
        assert len(all_docs) == 1 and all_docs[0].source == "share"
        print("OK shared files ingested with source='share'")


if __name__ == "__main__":
    test_callback_and_drain()
    test_mime_fallback()
    test_ingest_shared_files()
    print("\nShare tests passed.")
