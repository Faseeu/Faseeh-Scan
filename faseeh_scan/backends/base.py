from __future__ import annotations

import abc
from pathlib import Path


class StorageBackend(abc.ABC):
    """A backend syncs encrypted vault files to some destination."""

    id: str = "base"
    display_name: str = "Base"

    @abc.abstractmethod
    def is_configured(self) -> bool:
        """True if this backend has valid credentials / config."""

    @abc.abstractmethod
    def authenticate(self, parent_window=None) -> None:
        """Run any interactive login needed. Idempotent if already logged in."""

    @abc.abstractmethod
    def upload(self, relative_path: str, local_path: Path) -> str:
        """Upload one file. Returns a backend-specific remote id/path."""

    @abc.abstractmethod
    def download(self, relative_path: str, local_path: Path) -> None:
        """Download one file to local_path."""

    @abc.abstractmethod
    def list_remote(self) -> list[str]:
        """List relative paths available remotely."""

    def backup_vault(self, vault) -> int:
        """Upload every encrypted file in the vault. Returns count uploaded."""
        count = 0
        for rel, abs_path in vault.iter_encrypted_files():
            self.upload(rel, abs_path)
            count += 1
            if rel.startswith("data/") and rel.endswith(".bin"):
                document_id = rel[len("data/") : -len(".bin")]
                try:
                    vault.mark_backed_up(document_id, self.id)
                except KeyError:
                    # metadata may not yet include a just-written file
                    pass
        return count

    def restore_vault(self, vault) -> int:
        """Download every remote encrypted file into the vault dir. Returns count."""
        count = 0
        for rel in self.list_remote():
            local = vault.path / rel
            local.parent.mkdir(parents=True, exist_ok=True)
            self.download(rel, local)
            count += 1
        return count
