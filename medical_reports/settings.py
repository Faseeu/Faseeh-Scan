"""Simple local settings (non-secret preferences).

Stored as JSON inside the vault directory when unlocked, so preferences travel
with the vault but are independent of the encrypted index. A small plaintext
file in the app config dir is used before a vault exists (for things like the
last-used folder). Secrets never go here.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path


def _config_dir() -> Path:
    home = Path.home()
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", home))
    elif os.sys.platform == "darwin":
        base = home / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", home / ".config"))
    return base / "FaseehScan"


@dataclass
class Settings:
    ocr_enabled: bool = False
    ocr_engine_id: str = ""          # empty = auto
    default_filter: str = "magic"
    wifi_only_backup: bool = True
    default_as_pdf: bool = True
    dark_mode: str = "system"        # "system" | "light" | "dark"
    haptics: bool = True

    @classmethod
    def load(cls, path: Path | None = None) -> "Settings":
        path = path or (_config_dir() / "settings.json")
        if path.exists():
            try:
                return cls(**json.loads(path.read_text()))
            except Exception:
                return cls()
        return cls()

    def save(self, path: Path | None = None) -> Path:
        path = path or (_config_dir() / "settings.json")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2))
        return path
