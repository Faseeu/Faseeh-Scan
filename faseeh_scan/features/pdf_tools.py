"""PDF page tools: assemble, reorder, rotate, delete, and merge.

These operate on plaintext PDF bytes (called before encryption) and never
touch the vault directly. Images are bundled losslessly via img2pdf when
available, falling back to Pillow. Everything is pure-Python and optional —
pypdf is only required when these tools are used.
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Iterable, Sequence


def _require_pypdf():
    try:
        import pypdf  # type: ignore
        return pypdf
    except ImportError as e:  # pragma: no cover
        raise RuntimeError(
            "PDF tools need pypdf. Install with: pip install -e .[pdf]"
        ) from e


# --------------------------------------------------------------------------
# Build a PDF from image file paths (and optional existing PDFs).
# --------------------------------------------------------------------------

def images_to_pdf_bytes(image_paths: Sequence[str | Path],
                        rotation_degrees: Sequence[int] | None = None) -> bytes:
    """Bundle one or more images into a (multi-page) PDF, returned as bytes."""
    image_paths = [Path(p) for p in image_paths]
    if not image_paths:
        raise ValueError("No pages provided.")
    rotation_degrees = rotation_degrees or [0] * len(image_paths)
    if len(rotation_degrees) != len(image_paths):
        raise ValueError("rotation_degrees length must match image_paths length")

    # 1) Lossless JPEG->PDF via img2pdf when all inputs are JPEG.
    try:
        import img2pdf  # type: ignore
        if all(p.suffix.lower() in (".jpg", ".jpeg") for p in image_paths):
            data = img2pdf.convert([str(p) for p in image_paths])
            if any(r % 360 for r in rotation_degrees):
                return _apply_rotations(data, rotation_degrees)
            return data
    except Exception:
        pass

    # 2) Pillow fallback (handles PNG/WEBP; re-encodes).
    from PIL import Image  # type: ignore
    pages = []
    first = None
    for i, p in enumerate(image_paths):
        im = Image.open(p).convert("RGB")
        r = rotation_degrees[i] % 360
        if r:
            im = im.rotate({90: 90, 180: 180, 270: 270}.get(r, 0), expand=True)
        pages.append(im)
        if first is None:
            first = im
    out = io.BytesIO()
    first.save(out, "PDF", resolution=150.0, save_all=True, append_images=pages[1:])
    return out.getvalue()


def _apply_rotations(pdf_bytes: bytes, rotations: Sequence[int]) -> bytes:
    pypdf = _require_pypdf()
    reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
    writer = pypdf.PdfWriter()
    for i, page in enumerate(reader.pages):
        if i < len(rotations) and rotations[i] % 360:
            page = page.rotate(rotations[i] % 360)
        writer.add_page(page)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


# --------------------------------------------------------------------------
# Reorder / rotate / delete pages of an existing PDF.
# --------------------------------------------------------------------------

def rearrange_pdf(pdf_bytes: bytes, page_order: Sequence[int],
                  rotations: dict[int, int] | None = None) -> bytes:
    """Return a new PDF with pages in `page_order` (0-indexed), optionally
    rotating individual pages. page_order may omit indices to delete pages."""
    pypdf = _require_pypdf()
    reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
    n = len(reader.pages)
    if any(i < 0 or i >= n for i in page_order):
        raise ValueError(f"page index out of range (PDF has {n} pages)")
    writer = pypdf.PdfWriter()
    for idx in page_order:
        page = reader.pages[idx]
        deg = (rotations or {}).get(idx, 0) % 360
        if deg:
            page = page.rotate(deg)
        writer.add_page(page)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def delete_pages(pdf_bytes: bytes, indices: Iterable[int]) -> bytes:
    remove = set(indices)
    reader = _require_pypdf().PdfReader(io.BytesIO(pdf_bytes))
    keep = [i for i in range(len(reader.pages)) if i not in remove]
    return rearrange_pdf(pdf_bytes, keep)


def rotate_pages(pdf_bytes: bytes, degrees: int, indices: Iterable[int] | None = None) -> bytes:
    """Rotate given pages (or all pages if indices is None) by `degrees` (90/180/270)."""
    pypdf = _require_pypdf()
    reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
    target = set(indices) if indices is not None else set(range(len(reader.pages)))
    order = list(range(len(reader.pages)))
    return rearrange_pdf(pdf_bytes, order, rotations={i: degrees for i in target})


# --------------------------------------------------------------------------
# Merge multiple PDFs together.
# --------------------------------------------------------------------------

def merge_pdfs(pdf_bytes_list: Sequence[bytes]) -> bytes:
    pypdf = _require_pypdf()
    writer = pypdf.PdfWriter()
    for data in pdf_bytes_list:
        reader = pypdf.PdfReader(io.BytesIO(data))
        for page in reader.pages:
            writer.add_page(page)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def page_count(pdf_bytes: bytes) -> int:
    return len(_require_pypdf().PdfReader(io.BytesIO(pdf_bytes)).pages)
