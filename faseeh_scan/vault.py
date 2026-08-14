"""
Vault: the local encrypted store + metadata index.

A vault lives in a single directory and contains:

    vault.key            <- password-wrapped master key (one file)
    meta.json            <- encrypted metadata index
    data/<id>.bin        <- one encrypted document/file per entry
    artifacts/<id>/<key>.bin  <- encrypted sidecars (OCR text, thumbnails...)

The vault NEVER stores plaintext on disk. The master key is held in memory
only after the user unlocks it.

Storage backends (see backends/) sync encrypted blobs to the user's own
cloud. The cloud provider never sees plaintext or even original filenames.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable

from . import crypto


@dataclass
class DocumentMeta:
    id: str
    name: str              # original file name, e.g. "blood-test-2024.pdf"
    content_type: str      # MIME type
    size: int              # plaintext size in bytes
    created_at: float
    encrypted_size: int = 0
    note: str = ""
    tags: list[str] = field(default_factory=list)
    starred: bool = False
    source: str = "import"  # "import" | "camera" | "share"
    original_sha256: str = ""
    # artifact_key -> {"size": int, "content_type": str, "created_at": float}
    artifacts: dict[str, dict] = field(default_factory=dict)
    # backend ids this document has been backed up to, e.g. ["gdrive"]
    backed_up_to: list[str] = field(default_factory=list)
    # 0 = not deleted; otherwise unix timestamp when moved to trash
    deleted_at: float = 0
    # List of prior versions: [{"artifact": "v0001", "size": int,
    #   "content_type": str, "created_at": float, "label": str}, ...]
    # The newest entry is the most recent previous version; current blob is
    # always data/<id>.bin.
    versions: list[dict] = field(default_factory=list)


class Vault:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.data_dir = self.path / "data"
        self.artifacts_dir = self.path / "artifacts"
        self.keyfile = self.path / crypto.KEYFILE_NAME
        self.metafile = self.path / "meta.json"
        self._master_key: bytes | None = None
        self._meta: dict[str, DocumentMeta] = {}

    # ---- lifecycle -------------------------------------------------------

    @property
    def exists(self) -> bool:
        return self.keyfile.exists()

    @property
    def is_unlocked(self) -> bool:
        return self._master_key is not None

    def create(self, password: str) -> None:
        if self.exists:
            raise FileExistsError(f"Vault already exists at {self.path}")
        self.path.mkdir(parents=True, exist_ok=True)
        self.data_dir.mkdir(exist_ok=True)
        self.artifacts_dir.mkdir(exist_ok=True)
        master_key, wrapped = crypto.create_wrapped_master_key(password)
        self.keyfile.write_text(wrapped.to_json())
        self._master_key = master_key
        self._meta = {}
        self._save_meta()

    def unlock(self, password: str) -> None:
        if not self.exists:
            raise FileNotFoundError(f"No vault at {self.path}")
        wrapped = crypto.WrappedMasterKey.from_json(self.keyfile.read_text())
        self._master_key = crypto.unwrap_master_key(wrapped, password)
        self._load_meta()

    def lock(self) -> None:
        self._master_key = None
        self._meta = {}

    def change_password(self, old_password: str, new_password: str) -> None:
        wrapped = crypto.WrappedMasterKey.from_json(self.keyfile.read_text())
        master_key = crypto.unwrap_master_key(wrapped, old_password)
        new_wrapped = crypto.wrap_master_key(master_key, new_password)
        tmp = self.keyfile.with_suffix(".key.tmp")
        tmp.write_text(new_wrapped.to_json())
        os.replace(tmp, self.keyfile)
        self._master_key = master_key

    # ---- metadata --------------------------------------------------------

    def _load_meta(self) -> None:
        if not self.metafile.exists():
            self._meta = {}
            return
        container = self.metafile.read_bytes()
        try:
            plaintext = crypto.decrypt_report(self._master_key, container)
            raw = json.loads(plaintext.decode("utf-8"))
            self._meta = {k: DocumentMeta(**v) for k, v in raw.items()}
        except Exception as e:
            raise crypto.VaultCorruptedError(f"Could not read metadata: {e}") from e

    def _save_meta(self) -> None:
        raw = {k: asdict(v) for k, v in self._meta.items()}
        plaintext = json.dumps(raw, indent=2).encode("utf-8")
        container = crypto.encrypt_report(self._master_key, plaintext)
        tmp = self.metafile.with_suffix(".json.tmp")
        tmp.write_bytes(container)
        os.replace(tmp, self.metafile)

    # ---- documents -------------------------------------------------------

    def add_document(
        self,
        data: bytes,
        name: str,
        content_type: str = "application/octet-stream",
        *,
        note: str = "",
        tags: list[str] | None = None,
        source: str = "import",
        original_sha256: str = "",
    ) -> DocumentMeta:
        self._require_unlocked()
        rid = crypto.new_report_id()
        if not original_sha256:
            import hashlib
            original_sha256 = hashlib.sha256(data).hexdigest()
        container = crypto.encrypt_report(self._master_key, data)
        report_path = self.data_dir / f"{rid}.bin"
        report_path.write_bytes(container)
        meta = DocumentMeta(
            id=rid,
            name=name,
            content_type=content_type,
            size=len(data),
            created_at=time.time(),
            encrypted_size=len(container),
            note=note,
            tags=tags or [],
            source=source,
            original_sha256=original_sha256,
        )
        self._meta[rid] = meta
        self._save_meta()
        return meta

    def list_documents(self, include_deleted: bool = False) -> list[DocumentMeta]:
        self._require_unlocked()
        docs = self._meta.values() if include_deleted else [
            d for d in self._meta.values() if not d.deleted_at]
        return sorted(docs, key=lambda d: d.created_at, reverse=True)

    def list_trash(self) -> list[DocumentMeta]:
        self._require_unlocked()
        return sorted((d for d in self._meta.values() if d.deleted_at),
                      key=lambda d: d.deleted_at, reverse=True)

    def get_document(self, document_id: str) -> tuple[DocumentMeta, bytes]:
        self._require_unlocked()
        meta = self._meta[document_id]
        container = (self.data_dir / f"{document_id}.bin").read_bytes()
        plaintext = crypto.decrypt_report(self._master_key, container)
        return meta, plaintext

    def get_meta(self, document_id: str) -> DocumentMeta:
        self._require_unlocked()
        return self._meta[document_id]

    def update_meta(self, meta: DocumentMeta) -> None:
        self._require_unlocked()
        self._meta[meta.id] = meta
        self._save_meta()

    # ---- version history -------------------------------------------------

    MAX_VERSIONS = 10

    def replace_blob(self, document_id: str, data: bytes, *,
                     content_type: str = "application/octet-stream",
                     label: str = "edit") -> DocumentMeta:
        """Replace a document's current bytes, saving the previous version as
        an encrypted sidecar. Returns the updated metadata."""
        self._require_unlocked()
        meta = self._meta[document_id]
        # Save the CURRENT blob as a version before overwriting.
        current_path = self.data_dir / f"{document_id}.bin"
        if current_path.exists():
            version_no = len(meta.versions) + 1
            key = f"v{version_no:04d}"
            vdir = self.artifacts_dir / document_id
            vdir.mkdir(parents=True, exist_ok=True)
            # Move current encrypted blob into versions.
            os.replace(current_path, vdir / f"{key}.bin")
            meta.versions.append({
                "artifact": key,
                "size": meta.size,
                "content_type": meta.content_type,
                "created_at": time.time(),
                "label": label,
            })
        # Write the new current blob.
        container = crypto.encrypt_report(self._master_key, data)
        current_path.write_bytes(container)
        meta.size = len(data)
        meta.encrypted_size = len(container)
        meta.content_type = content_type
        # Trim old versions beyond MAX_VERSIONS.
        while len(meta.versions) > self.MAX_VERSIONS:
            old = meta.versions.pop(0)
            op = self.artifacts_dir / document_id / f"{old['artifact']}.bin"
            if op.exists():
                crypto.secure_delete(str(op))
        self._save_meta()
        return meta

    def list_versions(self, document_id: str) -> list[dict]:
        self._require_unlocked()
        return list(self._meta[document_id].versions)

    def get_version(self, document_id: str, artifact_key: str) -> bytes:
        self._require_unlocked()
        p = self.artifacts_dir / document_id / f"{artifact_key}.bin"
        if not p.exists():
            raise KeyError(f"No version {artifact_key} for document {document_id}")
        return crypto.decrypt_report(self._master_key, p.read_bytes())

    def restore_version(self, document_id: str, artifact_key: str,
                        label: str = "restore") -> DocumentMeta:
        """Restore a prior version to be the current blob (keeps history)."""
        data = self.get_version(document_id, artifact_key)
        v = next((x for x in self._meta[document_id].versions
                   if x["artifact"] == artifact_key), {})
        return self.replace_blob(document_id, data,
                                 content_type=v.get("content_type",
                                                    "application/octet-stream"),
                                 label=label)

    def trash_document(self, document_id: str) -> None:
        """Soft-delete: hides the document but keeps its data for undo."""
        import time
        self._require_unlocked()
        d = self._meta[document_id]
        d.deleted_at = time.time()
        self._save_meta()

    def restore_document(self, document_id: str) -> DocumentMeta:
        self._require_unlocked()
        d = self._meta[document_id]
        d.deleted_at = 0
        self._save_meta()
        return d

    def empty_trash(self) -> int:
        """Permanently delete all trashed documents. Returns count removed."""
        self._require_unlocked()
        removed = 0
        for d in self.list_trash():
            self._purge_document(d.id)
            removed += 1
        return removed

    def delete_document(self, document_id: str) -> None:
        """Permanently delete a single document and its artifacts."""
        self._require_unlocked()
        self._purge_document(document_id)

    def _purge_document(self, document_id: str) -> None:
        path = self.data_dir / f"{document_id}.bin"
        if path.exists():
            crypto.secure_delete(str(path))
        art_dir = self.artifacts_dir / document_id
        if art_dir.exists():
            for p in art_dir.glob("*"):
                crypto.secure_delete(str(p))
            art_dir.rmdir()
        self._meta.pop(document_id, None)
        self._save_meta()

    # ---- artifacts (OCR text, thumbnails...) -----------------------------

    def put_artifact(self, document_id: str, key: str, data: bytes,
                     content_type: str = "application/octet-stream") -> None:
        self._require_unlocked()
        container = crypto.encrypt_report(self._master_key, data)
        d = self.artifacts_dir / document_id
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{key}.bin").write_bytes(container)
        meta = self._meta[document_id]
        meta.artifacts[key] = {
            "size": len(data),
            "encrypted_size": len(container),
            "content_type": content_type,
            "created_at": time.time(),
        }
        self._save_meta()

    def get_artifact(self, document_id: str, key: str) -> bytes:
        self._require_unlocked()
        p = self.artifacts_dir / document_id / f"{key}.bin"
        if not p.exists():
            raise KeyError(f"No artifact '{key}' for document {document_id}")
        return crypto.decrypt_report(self._master_key, p.read_bytes())

    def has_artifact(self, document_id: str, key: str) -> bool:
        self._require_unlocked()
        return key in self._meta.get(document_id, DocumentMeta(
            id="", name="", content_type="", size=0, created_at=0)).artifacts

    # ---- sync helpers ----------------------------------------------------

    def iter_encrypted_files(self) -> Iterable[tuple[str, Path]]:
        """Yield (relative_name, absolute_path) for every file a backend must sync."""
        for p in sorted(self.data_dir.glob("*.bin")):
            yield f"data/{p.name}", p
        if self.artifacts_dir.exists():
            for p in sorted(self.artifacts_dir.rglob("*.bin")):
                yield str(p.relative_to(self.path)), p
        if self.keyfile.exists():
            yield crypto.KEYFILE_NAME, self.keyfile
        if self.metafile.exists():
            yield "meta.json", self.metafile

    def mark_backed_up(self, document_id: str, backend_id: str) -> None:
        d = self._meta[document_id]
        if backend_id not in d.backed_up_to:
            d.backed_up_to.append(backend_id)
            self._save_meta()

    def _require_unlocked(self) -> None:
        if not self.is_unlocked:
            raise RuntimeError("Vault is locked.")
