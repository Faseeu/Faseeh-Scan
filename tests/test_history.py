"""Version history + backup health tests."""
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from medical_reports.vault import Vault
from medical_reports.services import DocumentsService, BackupService
from medical_reports.backends.local import LocalBackend


def test_version_history_restore():
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        v = Vault(d / "v")
        v.create("pw")
        docs = DocumentsService(v)
        doc = docs.add(b"version one", "doc.pdf", "application/pdf",
                       make_thumbnail=False)
        # Edit twice
        docs.replace_blob(doc.id, b"version two", label="arrange")
        docs.replace_blob(doc.id, b"version three", label="edit")
        _, current = docs.get(doc.id)
        assert current == b"version three"
        versions = docs.list_versions(doc.id)
        assert len(versions) == 2
        # first saved version should be 'version one'
        v1 = docs.get_version(doc.id, versions[0]["artifact"])
        assert v1 == b"version one"
        # restore first version -> becomes current
        docs.restore_version(doc.id, versions[0]["artifact"])
        _, restored = docs.get(doc.id)
        assert restored == b"version one"
        # history grows (now 3 prior versions)
        assert len(docs.list_versions(doc.id)) == 3
        print("OK version history + restore")


def test_max_versions_trimmed():
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        v = Vault(d / "v")
        v.create("pw")
        docs = DocumentsService(v)
        doc = docs.add(b"orig", "d.pdf", "application/pdf", make_thumbnail=False)
        for i in range(Vault.MAX_VERSIONS + 3):
            docs.replace_blob(doc.id, f"v{i}".encode())
        assert len(docs.list_versions(doc.id)) == Vault.MAX_VERSIONS
        print("OK old versions trimmed")


def test_backup_health_and_auto():
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        v = Vault(d / "v")
        v.create("pw")
        be = LocalBackend(d / "backup")
        svc = BackupService(v)
        h = svc.health()
        assert h["has_backend"] is False
        svc.use(be)
        v.add_document(b"a", "a.pdf", "application/pdf")
        h = svc.health()
        assert h["pending"] == 1
        assert h["ok"] is False
        n = svc.auto_backup_if_needed()
        assert n >= 1
        assert svc.pending_count() == 0
        assert svc.health()["ok"] is True
        assert svc.health()["last_backup"] is not None
        # no-op when nothing pending
        assert svc.auto_backup_if_needed() == 0
        print("OK backup health + auto backup")


if __name__ == "__main__":
    test_version_history_restore()
    test_max_versions_trimmed()
    test_backup_health_and_auto()
    print("\nHistory/backup tests passed.")
