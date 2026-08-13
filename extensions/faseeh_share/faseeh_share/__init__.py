"""Python side of the incoming-share Flet extension.

Usage from the app:

    from faseeh_share import attach_share_receiver
    svc = attach_share_receiver(page)
    svc.on_incoming(lambda files: ...)

The extension is optional and only meaningful on mobile. On desktop/web the
returned service simply stays empty (or can be populated by tests).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from flet.core.page import Page

from medical_reports.features.share_intent import (  # noqa: F401
    IncomingFile, ShareIntentService, mime_to_content_type,
)


def attach_share_receiver(page: "Page") -> ShareIntentService:
    svc = ShareIntentService()
    try:
        # The Dart control (src/flutter/faseeh_share) registers a page event
        # named 'faseeh_share_receive' with a list of {path, mime, text}.
        def _on_event(e):
            files = getattr(e, "files", None) or []
            svc.set_incoming_files(files)

        if hasattr(page, "on_event"):
            page.on_event("faseeh_share_receive", _on_event)
    except Exception:
        pass
    return svc
