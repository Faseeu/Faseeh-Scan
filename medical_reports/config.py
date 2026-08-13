"""
Configuration loaded from environment variables (and a local .env if present).

OAuth credentials are NOT committed to the repo. Copy .env.example to .env and
fill in the values, or set the variables in your shell / CI / Flet build config.

For Android you create an **Android** OAuth client in Google Cloud Console
(package name + SHA-1) AND a **Web application** client. The token exchange uses
the WEB client's id/secret (Flet's flow exchanges the code server-side); the
Android client establishes that the app is allowed to use the Google account on
the device. The redirect on Android is the Flet custom scheme `flet://...`.
"""

from __future__ import annotations

import os
import platform
from dataclasses import dataclass
from pathlib import Path


def _load_dotenv(path: str | Path = ".env") -> None:
    """Minimal .env loader (no extra dependency). Lines: KEY=VALUE (# comments ok)."""
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        os.environ.setdefault(key, val)


_load_dotenv()

# Flet exposes the running platform. Detect it best-effort.
def _is_android() -> bool:
    # Flet/Flutter sets this; also bridged via the page object at runtime.
    return "ANDROID_ROOT" in os.environ or "ANDROID_DATA" in os.environ or \
           platform.system().lower() == "android"


@dataclass(frozen=True)
class Settings:
    google_client_id: str = os.environ.get("GOOGLE_CLIENT_ID", "")
    google_client_secret: str = os.environ.get("GOOGLE_CLIENT_SECRET", "")
    # Flet's web/desktop callback endpoint is "/oauth_callback".
    # On Android, Flet opens an in-app web view and intercepts the redirect
    # internally; the exact host is ignored, so the same value works.
    # For a deployed web build set OAUTH_REDIRECT_URL to
    # https://<your-host>/oauth_callback.
    oauth_redirect_url: str = os.environ.get(
        "OAUTH_REDIRECT_URL", "http://localhost/oauth_callback"
    )

    @property
    def google_oauth_configured(self) -> bool:
        return bool(self.google_client_id and self.google_client_secret)


settings = Settings()
