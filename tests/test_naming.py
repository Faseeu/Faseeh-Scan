"""Tests for smart OCR-based naming."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from medical_reports.features.naming import suggest_name  # type: ignore  # noqa


def test_date_and_title():
    text = "INVOICE\nAcme Corporation\nDate 2026-08-13\nTotal 1500"
    name = suggest_name(text, fallback="doc")
    assert "2026-08-13" in name
    assert "Acme" in name or "INVOICE" in name
    print("OK date + title extracted")


def test_fallback_when_empty():
    assert suggest_name("", fallback="x.pdf") == "x.pdf"
    print("OK empty fallback")


def test_no_unsafe_chars():
    text = "Report / Q3: *final* <version>"
    name = suggest_name(text, fallback="doc")
    for ch in '\\/:*?"<>|':
        assert ch not in name
    print("OK filename is safe")


def test_alt_date_format():
    name = suggest_name("Statement dated 13 Aug 2026\nBank Ltd", "doc")
    assert "2026" in name
    print("OK alt date format")


if __name__ == "__main__":
    test_date_and_title()
    test_fallback_when_empty()
    test_no_unsafe_chars()
    test_alt_date_format()
    print("\nNaming tests passed.")
