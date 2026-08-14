"""
Incoming shares from other apps ("Share to Faseeh Scan").

On Android, the native `receive_sharing_intent` plugin delivers files shared
from a file manager, WhatsApp, Gmail, etc. We expose it through a small
interface the app polls/subscribes to. On desktop/web (where there is no OS
share intent), a file list can be injected (e.g. from the CLI or tests) via
:class:`StubShareIntent`, so the routing logic stays testable.

The native Flet extension (extensions/faseeh_share) calls `set_incoming_files`
when the OS hands us files.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable


@dataclass
class IncomingFile:
    path: str
    mime: str = "application/octet-stream"
    text: str = ""
    source: str = "share"


class ShareIntentService:
    """Receives files/text sent from other apps and dispatches them."""

    def __init__(self) -> None:
        self._pending: list[IncomingFile] = []
        self._callbacks: list[Callable[[list[IncomingFile]], None]] = []

    # ---- native/bridge entry point ---------------------------------------

    def set_incoming_files(self, files: Iterable[dict]) -> list[IncomingFile]:
        """Called by the native bridge (or tests) with shared payloads."""
        incoming = [
            IncomingFile(
                path=f.get("path", ""),
                mime=f.get("mime", "application/octet-stream"),
                text=f.get("text", ""),
                source=f.get("source", "share"),
            )
            for f in files
            if f.get("path") or f.get("text")
        ]
        if incoming:
            self._pending.extend(incoming)
            for cb in list(self._callbacks):
                try:
                    cb(incoming)
                except Exception:
                    pass
        return incoming

    # ---- public API ------------------------------------------------------

    def on_incoming(self, cb: Callable[[list[IncomingFile]], None]) -> None:
        self._callbacks.append(cb)

    def drain(self) -> list[IncomingFile]:
        items, self._pending = self._pending, []
        return items

    def has_pending(self) -> bool:
        return bool(self._pending)

    def files_only(self) -> list[IncomingFile]:
        return [f for f in self._pending if f.path]


def create_share_service(page=None) -> ShareIntentService:
    """Create a share service. If a Flet extension exposing
    `faseeh_share.receive` is available, wire it; otherwise return a plain
    service that tests/CLI can populate."""
    svc = ShareIntentService()
    if page is None:
        return svc
    # The native extension, when present, pushes events into a page session
    # key. We poll it defensively; absence is normal on desktop/web.
    try:
        def _bridge(event):
            files = getattr(event, "files", None) or []
            svc.set_incoming_files(files)
        # Extension hook (see extensions/faseeh_share).
        if hasattr(page, "faseeh_share"):
            page.faseeh_share.on_receive(_bridge)  # type: ignore[attr-defined]
    except Exception:
        pass
    return svc


def mime_to_content_type(mime: str, path: str = "") -> str:
    if mime:
        return mime
    return {
        ".pdf": "application/pdf", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".png": "image/png", ".webp": "image/webp", ".txt": "text/plain",
    }.get(Path(path).suffix.lower(), "application/octet-stream")
