"""
Vault: the local encrypted store + metadata index.

A vault lives in a single directory and contains:

    vault.key            <- password-wrapped master key (one file)
    meta.json            <- encrypted metadata index (names, dates, hashes...)
    data/<id>.mrbk       <- one encrypted report per file

The vault NEVER stores plaintext on disk. The master key is held in memory
only after the user unlocks it.

Storage backends (see backends/) sync the encrypted `data/` and `vault.key`
to the user's own cloud. Since everything is ciphertext, the cloud provider
(Google Drive) never sees report contents, names, or metadata.
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
class ReportMeta:
    id: str
    name: str              # original file name, e.g. "blood-test-2024.pdf"
    size: int              # plaintext size in bytes
    created_at: float
    encrypted_size: int = 0
    content_type: str = "application/octet-stream"
    note: str = ""
    # ids of backends this report has been backed up to, e.g. {"gdrive"}
    backed_up_to: list[str] = field(default_factory=list)


class Vault:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.data_dir = self.path / "data"
        self.keyfile = self.path / crypto.KEYFILE_NAME
        self.metafile = self.path / "meta.json"
        self._master_key: bytes | None = None
        self._meta: dict[str, ReportMeta] = {}

    # ---- lifecycle -------------------------------------------------------

    @property
    def exists(self) -> bool:
        return self.keyfile.exists()

    @property
    def is_unlocked(self) -> bool:
        return self._master_key is not None

    def create(self, password: str) -> None:
        """Create a brand-new vault. Errors if one already exists."""
        if self.exists:
            raise FileExistsError(f"Vault already exists at {self.path}")
        self.path.mkdir(parents=True, exist_ok=True)
        self.data_dir.mkdir(exist_ok=True)
        master_key, wrapped = crypto.create_wrapped_master_key(password)
        self.keyfile.write_text(wrapped.to_json())
        self._master_key = master_key
        self._meta = {}
        self._save_meta()

    def unlock(self, password: str) -> None:
        """Unlock an existing vault with the user's password."""
        if not self.exists:
            raise FileNotFoundError(f"No vault at {self.path}")
        wrapped = crypto.WrappedMasterKey.from_json(self.keyfile.read_text())
        self._master_key = crypto.unwrap_master_key(wrapped, password)
        self._load_meta()

    def lock(self) -> None:
        self._master_key = None
        self._meta = {}

    def change_password(self, old_password: str, new_password: str) -> None:
        # Re-derive master key from old password to prove identity.
        wrapped = crypto.WrappedMasterKey.from_json(self.keyfile.read_text())
        master_key = crypto.unwrap_master_key(wrapped, old_password)
        new_wrapped = crypto.wrap_master_key(master_key, new_password)
        # Write atomically-ish.
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
            self._meta = {k: ReportMeta(**v) for k, v in raw.items()}
        except Exception as e:
            raise crypto.VaultCorruptedError(f"Could not read metadata: {e}") from e

    def _save_meta(self) -> None:
        raw = {k: asdict(v) for k, v in self._meta.items()}
        plaintext = json.dumps(raw, indent=2).encode("utf-8")
        container = crypto.encrypt_report(self._master_key, plaintext)
        tmp = self.metafile.with_suffix(".json.tmp")
        tmp.write_bytes(container)
        os.replace(tmp, self.metafile)

    # ---- reports ---------------------------------------------------------

    def add_report(
        self,
        data: bytes,
        name: str,
        content_type: str = "application/octet-stream",
        note: str = "",
    ) -> ReportMeta:
        self._require_unlocked()
        rid = crypto.new_report_id()
        container = crypto.encrypt_report(self._master_key, data)
        report_path = self.data_dir / f"{rid}.mrbk"
        report_path.write_bytes(container)
        meta = ReportMeta(
            id=rid,
            name=name,
            size=len(data),
            created_at=time.time(),
            encrypted_size=len(container),
            content_type=content_type,
            note=note,
        )
        self._meta[rid] = meta
        self._save_meta()
        return meta

    def list_reports(self) -> list[ReportMeta]:
        self._require_unlocked()
        return sorted(self._meta.values(), key=lambda r: r.created_at, reverse=True)

    def get_report(self, report_id: str) -> tuple[ReportMeta, bytes]:
        self._require_unlocked()
        meta = self._meta[report_id]
        container = (self.data_dir / f"{report_id}.mrbk").read_bytes()
        plaintext = crypto.decrypt_report(self._master_key, container)
        return meta, plaintext

    def delete_report(self, report_id: str) -> None:
        self._require_unlocked()
        path = self.data_dir / f"{report_id}.mrbk"
        if path.exists():
            crypto.secure_delete(str(path))
        self._meta.pop(report_id, None)
        self._save_meta()

    def iter_encrypted_files(self) -> Iterable[tuple[str, Path]]:
        """Yield (relative_name, absolute_path) for every file a backend must sync."""
        for p in sorted(self.data_dir.glob("*.mrbk")):
            yield f"data/{p.name}", p
        if self.keyfile.exists():
            yield crypto.KEYFILE_NAME, self.keyfile
        if self.metafile.exists():
            yield "meta.json", self.metafile

    def mark_backed_up(self, report_id: str, backend_id: str) -> None:
        r = self._meta[report_id]
        if backend_id not in r.backed_up_to:
            r.backed_up_to.append(backend_id)
            self._save_meta()

    def _require_unlocked(self) -> None:
        if not self.is_unlocked:
            raise RuntimeError("Vault is locked.")
