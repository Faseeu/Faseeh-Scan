"""Local filesystem backend — useful as a "USB stick / folder backup" target
and for offline development without any cloud credentials."""

from __future__ import annotations

import shutil
from pathlib import Path

from .base import StorageBackend


class LocalBackend(StorageBackend):
    id = "local"
    display_name = "Local folder"

    def __init__(self, destination: str | Path):
        self.destination = Path(destination)
        self.destination.mkdir(parents=True, exist_ok=True)

    def is_configured(self) -> bool:
        return self.destination.exists()

    def authenticate(self, parent_window=None) -> None:
        return None

    def _remote_path(self, relative_path: str) -> Path:
        # Prevent path traversal.
        p = (self.destination / relative_path).resolve()
        if not str(p).startswith(str(self.destination.resolve())):
            raise ValueError(f"Unsafe path: {relative_path}")
        return p

    def upload(self, relative_path: str, local_path: Path) -> str:
        dest = self._remote_path(relative_path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(local_path, dest)
        return str(dest)

    def download(self, relative_path: str, local_path: Path) -> None:
        src = self._remote_path(relative_path)
        local_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, local_path)

    def list_remote(self) -> list[str]:
        out: list[str] = []
        for p in self.destination.rglob("*"):
            if p.is_file():
                out.append(str(p.relative_to(self.destination)))
        return out
