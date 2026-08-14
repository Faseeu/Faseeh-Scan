"""
Thin service layer that orchestrates core + pluggable features.

The UI talks to services; services talk to the vault, backends, and feature
registries. This keeps UI code simple and means new features register
themselves without editing call sites.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from .vault import Vault, DocumentMeta


class VaultService:
    """Create/unlock/lock/password for a vault."""

    def __init__(self, vault: Vault):
        self.vault = vault

    @property
    def exists(self) -> bool:
        return self.vault.exists

    @property
    def is_unlocked(self) -> bool:
        return self.vault.is_unlocked

    def create(self, password: str) -> None:
        self.vault.create(password)

    def unlock(self, password: str) -> None:
        self.vault.unlock(password)

    def lock(self) -> None:
        self.vault.lock()

    def change_password(self, old: str, new: str) -> None:
        self.vault.change_password(old, new)


class DocumentsService:
    """Add/list/get/delete/tag/star documents and attach artifacts."""

    def __init__(self, vault: Vault, settings: "Settings | None" = None):
        self.vault = vault
        self.settings = settings

    def add(self, data: bytes, name: str, content_type: str = "application/octet-stream",
            *, source: str = "import", tags: list[str] | None = None,
            note: str = "", make_thumbnail: bool = True,
            run_ocr: bool | None = None) -> DocumentMeta:
        meta = self.vault.add_document(
            data, name, content_type, source=source, tags=tags or [], note=note
        )
        # Sidecars are best-effort and must never break adding the original.
        if make_thumbnail:
            self._try_thumbnail(meta.id, data, content_type)
        should_ocr = (self.settings.ocr_enabled if self.settings else False) \
            if run_ocr is None else run_ocr
        if should_ocr:
            self._try_ocr(meta.id, data, content_type)
        return meta

    def _try_thumbnail(self, doc_id: str, data: bytes, content_type: str) -> None:
        try:
            from .features.thumbnails import make_thumbnail
            thumb = make_thumbnail(data, content_type)
            if thumb:
                self.vault.put_artifact(doc_id, "thumb", thumb, "image/jpeg")
        except Exception:
            pass

    def _try_ocr(self, doc_id: str, data: bytes, content_type: str) -> None:
        try:
            from .features.ocr import default as default_ocr
            engine = default_ocr()
            if engine is None:
                return
            text = engine.extract(data, content_type)
            if text and text.strip():
                self.vault.put_artifact(doc_id, "ocr", text.encode("utf-8"),
                                        "text/plain")
        except Exception:
            pass


    def list(self) -> list[DocumentMeta]:
        return self.vault.list_documents()

    def list_trash(self) -> list[DocumentMeta]:
        return self.vault.list_trash()

    def trash(self, doc_id: str) -> None:
        self.vault.trash_document(doc_id)

    def restore(self, doc_id: str) -> DocumentMeta:
        return self.vault.restore_document(doc_id)

    def empty_trash(self) -> int:
        return self.vault.empty_trash()

    def get(self, doc_id: str) -> tuple[DocumentMeta, bytes]:
        return self.vault.get_document(doc_id)

    def delete(self, doc_id: str) -> None:
        self.vault.delete_document(doc_id)

    def rename(self, doc_id: str, name: str) -> DocumentMeta:
        m = self.vault.get_meta(doc_id)
        m.name = name
        self.vault.update_meta(m)
        return m

    def set_starred(self, doc_id: str, starred: bool) -> DocumentMeta:
        m = self.vault.get_meta(doc_id)
        m.starred = starred
        self.vault.update_meta(m)
        return m

    def set_tags(self, doc_id: str, tags: list[str]) -> DocumentMeta:
        m = self.vault.get_meta(doc_id)
        m.tags = tags
        self.vault.update_meta(m)
        return m

    def set_note(self, doc_id: str, note: str) -> DocumentMeta:
        m = self.vault.get_meta(doc_id)
        m.note = note
        self.vault.update_meta(m)
        return m

    def put_artifact(self, doc_id: str, key: str, data: bytes,
                     content_type: str = "application/octet-stream") -> None:
        self.vault.put_artifact(doc_id, key, data, content_type)

    def get_artifact(self, doc_id: str, key: str) -> bytes:
        return self.vault.get_artifact(doc_id, key)

    def has_artifact(self, doc_id: str, key: str) -> bool:
        return self.vault.has_artifact(doc_id, key)

    def replace_blob(self, document_id: str, data: bytes, *,
                     name: str | None = None,
                     content_type: str = "application/pdf",
                     make_thumbnail: bool = True,
                     label: str = "edit") -> DocumentMeta:
        """Replace a document's encrypted bytes (e.g. after editing a PDF),
        keeping its id, tags, note, and a versioned history of prior blobs."""
        meta = self.vault.replace_blob(
            document_id, data, content_type=content_type, label=label)
        if name:
            meta.name = name
        if "thumb" in meta.artifacts:
            self._try_thumbnail(document_id, data, content_type)
        self.vault.update_meta(meta)
        return meta

    def list_versions(self, doc_id: str) -> list[dict]:
        return self.vault.list_versions(doc_id)

    def get_version(self, doc_id: str, artifact_key: str) -> bytes:
        return self.vault.get_version(doc_id, artifact_key)

    def restore_version(self, doc_id: str, artifact_key: str) -> DocumentMeta:
        return self.vault.restore_version(doc_id, artifact_key, label="restore")

    def search(self, query: str) -> list[DocumentMeta]:
        """Simple filename/note/tag search. OCR text is searched when an
        'ocr' artifact exists; semantic search is a later pluggable engine."""
        q = (query or "").lower().strip()
        if not q:
            return self.list()
        out: list[DocumentMeta] = []
        for d in self.list():  # excludes trash
            haystack = " ".join([d.name, d.note, " ".join(d.tags)]).lower()
            if q in haystack:
                out.append(d)
                continue
            if self.has_artifact(d.id, "ocr"):
                try:
                    text = self.get_artifact(d.id, "ocr").decode("utf-8", "ignore").lower()
                    if q in text:
                        out.append(d)
                except Exception:
                    pass
        return out


class BackupService:
    """Choose a storage backend and run backup/restore."""

    def __init__(self, vault: Vault):
        self.vault = vault
        self._backend = None

    def use(self, backend) -> None:
        self._backend = backend

    @property
    def backend(self):
        return self._backend

    def backup(self) -> int:
        if self._backend is None:
            raise RuntimeError("No storage backend selected.")
        return self._backend.backup_vault(self.vault)

    def restore(self) -> int:
        if self._backend is None:
            raise RuntimeError("No storage backend selected.")
        return self._backend.restore_vault(self.vault)

    def pending_count(self) -> int:
        """Documents not yet backed up to the current backend."""
        if self._backend is None:
            return 0
        bid = self._backend.id
        return sum(1 for d in self.vault.list_documents() if bid not in d.backed_up_to)

    def last_backup_time(self) -> float | None:
        """Newest mtime among files the backend would sync, or None."""
        if self._backend is None:
            return None
        times = []
        for _, p in self.vault.iter_encrypted_files():
            try:
                times.append(p.stat().st_mtime)
            except OSError:
                pass
        return max(times) if times else None

    def health(self) -> dict:
        """Summary used by the UI's backup indicator."""
        pending = self.pending_count()
        last = self.last_backup_time()
        return {
            "has_backend": self._backend is not None,
            "pending": pending,
            "last_backup": last,
            "ok": self._backend is not None and pending == 0,
        }

    def auto_backup_if_needed(self, *, wifi_only: bool = False) -> int:
        """Run a backup if anything is pending. Returns number of files uploaded
        (0 when nothing to do). wifi_only is enforced by the caller based on
        platform connectivity; here we simply skip when there is no backend."""
        if self._backend is None:
            return 0
        if self.pending_count() == 0:
            return 0
        return self._backend.backup_vault(self.vault)
