"""Python side of the local_auth Flet extension."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from flet.core.page import Page


class LocalAuthBackend:
    def __init__(self, page: "Page"):
        self.page = page

    def is_available(self) -> bool:
        try:
            return bool(self.page.invoke_method(
                "faseeh_local_auth", "is_available", {}))
        except Exception:
            return False

    def can_check(self) -> bool:
        try:
            r = self.page.invoke_method(
                "faseeh_local_auth", "can_check_biometrics", {})
            return bool(r and r.get("canCheck", False))
        except Exception:
            return False

    def authenticate(self, reason: str = "Unlock Faseeh Scan") -> bool:
        try:
            r = self.page.invoke_method(
                "faseeh_local_auth", "authenticate", {"reason": reason})
            return bool(r and r.get("authenticated", False))
        except Exception:
            return False
