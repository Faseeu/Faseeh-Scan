"""
Home-screen quick actions / app shortcuts.

On Android/iOS, long-pressing the app icon can offer a "Scan document"
shortcut, implemented by the Flutter `quick_actions` plugin and exposed to
Python via the Flet extension under `extensions/faseeh_quick_actions`.

On desktop/web this is a no-op; the same shortcuts are reachable from the
sidebar.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from flet.core.page import Page


def attach(page: "Page", on_scan: Callable[[], None]) -> None:
    """Register a 'Scan document' shortcut. Best-effort; no-op if the native
    extension isn't present (desktop/web)."""
    items = [
        {"type": "scan", "localizedTitle": "Scan document",
         "icon": "ic_scan"},
    ]
    try:
        if hasattr(page, "faseeh_quick_actions"):
            page.faseeh_quick_actions.set_items(items)  # type: ignore[attr-defined]

            def _on_action(event):
                if getattr(event, "action", None) == "scan":
                    on_scan()
            page.on_event("faseeh_shortcut", _on_action)
    except Exception:
        pass
