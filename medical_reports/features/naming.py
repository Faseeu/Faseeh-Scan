"""Smart document naming from OCR text.

Heuristic, on-device, no network. Produces a short, filesystem-safe
suggestion by looking for dates, likely titles, and first meaningful line.
This is intentionally conservative — the user always confirms.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

_DATE_PATTERNS = [
    re.compile(r"\b(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})\b"),
    re.compile(r"\b(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})\b"),
    re.compile(r"\b(\d{1,2}) (Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* (\d{4})\b", re.I),
    re.compile(r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* (\d{1,2}),? (\d{4})\b", re.I),
]


def suggest_name(ocr_text: str, fallback: str = "document") -> str:
    text = (ocr_text or "").strip()
    if not text:
        return fallback
    lines = [re.sub(r"\s+", " ", ln).strip(" -:|\t")
             for ln in text.splitlines()]
    lines = [ln for ln in lines if 3 <= len(ln) <= 80]
    date = _find_date(text)
    title = _find_title(lines)
    parts = []
    if date:
        parts.append(date)
    if title:
        parts.append(title[:60])
    if not parts:
        return fallback
    name = " — ".join(parts)
    return _safe_filename(name) or fallback


def _find_date(text: str) -> str | None:
    for pat in _DATE_PATTERNS:
        m = pat.search(text)
        if not m:
            continue
        groups = m.groups()
        try:
            if len(groups[0]) == 4:  # YYYY-MM-DD
                return datetime(int(groups[0]), int(groups[1]), int(groups[2])).strftime("%Y-%m-%d")
            if groups[0].isdigit() and len(groups) == 3 and len(groups[2]) == 4:
                # DD-MM-YYYY
                return datetime(int(groups[2]), int(groups[1]), int(groups[0])).strftime("%Y-%m-%d")
            if groups[0].isalpha():
                dt = datetime.strptime(f"{groups[0]} {groups[1]} {groups[2]}", "%b %d %Y")
                return dt.strftime("%Y-%m-%d")
        except Exception:
            continue
    return None


def _find_title(lines: list[str]) -> str | None:
    skip = {"invoice", "receipt", "statement", "page", "date", "total",
            "amount", "balance", "account", "reference", "tel", "fax"}
    for ln in lines[:12]:
        low = ln.lower()
        if any(w in low for w in skip) and len(low) < 20:
            continue
        # Prefer lines with at least one letter and not mostly digits.
        letters = sum(c.isalpha() for c in ln)
        digits = sum(c.isdigit() for c in ln)
        if letters >= 4 and letters > digits:
            return ln
    return None


def _safe_filename(name: str) -> str:
    name = re.sub(r'[\\/:*?"<>|\n\r\t]+', " ", name)
    name = re.sub(r"\s+", " ", name).strip(" .")
    return name[:80]
