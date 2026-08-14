"""OCR engine interface + registry."""

from __future__ import annotations

from typing import Protocol


class OcrEngine(Protocol):
    id: str
    display_name: str

    def is_available(self) -> bool: ...
    def extract(self, data: bytes, content_type: str) -> str: ...


_REGISTRY: dict[str, type[OcrEngine]] = {}


def register(cls: type[OcrEngine]) -> type[OcrEngine]:
    _REGISTRY[cls.id] = cls
    return cls


def available() -> list[OcrEngine]:
    out = []
    for cls in _REGISTRY.values():
        try:
            inst = cls()
            if inst.is_available():
                out.append(inst)
        except Exception:
            continue
    return out


def default() -> OcrEngine | None:
    for preferred in ("rapidocr", "tesseract"):
        for e in available():
            if e.id == preferred:
                return e
    eng = available()
    return eng[0] if eng else None
