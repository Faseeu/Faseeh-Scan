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

    def list_documents(self) -> list[DocumentMeta]:
        self._require_unlocked()
        return sorted(self._meta.values(), key=lambda d: d.created_at, reverse=True)

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

    def delete_document(self, document_id: str) -> None:
        self._require_unlocked()
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
