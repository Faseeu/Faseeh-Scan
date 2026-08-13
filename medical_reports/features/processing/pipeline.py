"""
Cross-platform document image processing.

Provides the classic "CamScanner-like" cleanup using OpenCV:
  * edge detection + largest-quadrilateral contour -> auto crop & perspective
  * manual corner override
  * filters: original / color enhance / grayscale / b&w adaptive threshold /
    "magic" (shadow/background removal)
  * rotation

Outputs are clean JPEGs (and optionally a single PDF assembled with img2pdf).

OpenCV is imported lazily so the app runs without it if scanning isn't used.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Sequence

try:  # lazy, optional dependency
    import cv2  # type: ignore
    import numpy as np  # type: ignore
    SUPPORTED = True
except Exception:  # pragma: no cover
    cv2 = None
    np = None
    SUPPORTED = False


FILTERS = ("original", "color", "gray", "bw", "magic")


@dataclass
class ProcessOptions:
    filter: str = "magic"         # one of FILTERS
    auto_crop: bool = True
    corners: Optional[Sequence[tuple[int, int]]] = None  # 4 points override
    rotate: int = 0               # 0, 90, 180, 270


# --------------------------------------------------------------------------
# IO
# --------------------------------------------------------------------------

def _require_cv():
    if not SUPPORTED:
        raise RuntimeError(
            "Image processing requires opencv-python-headless, numpy, and Pillow. "
            "Install with: pip install -e .[scan]"
        )


def load_image(path: str | Path):
    _require_cv()
    data = Path(path).read_bytes()
    buf = np.frombuffer(data, dtype=np.uint8)
    img = cv2.imdecode(buf, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError(f"Could not read image: {path}")
    return img


def save_image(img, path: str | Path, quality: int = 92) -> Path:
    _require_cv()
    path = Path(path)
    ok, buf = cv2.imencode(path.suffix or ".jpg", img,
                           [int(cv2.IMWRITE_JPEG_QUALITY), int(quality)])
    if not ok:
        raise RuntimeError("Failed to encode image")
    path.write_bytes(buf.tobytes())
    return path


# --------------------------------------------------------------------------
# Geometry
# --------------------------------------------------------------------------

def order_points(pts):
    """Return points ordered top-left, top-right, bottom-right, bottom-left."""
    rect = np.zeros((4, 2), dtype="float32")
    s = pts.sum(axis=1)
    rect[0] = pts[np.argmin(s)]
    rect[2] = pts[np.argmax(s)]
    diff = np.diff(pts, axis=1)
    rect[1] = pts[np.argmin(diff)]
    rect[3] = pts[np.argmax(diff)]
    return rect


def detect_document_corners(img):
    """Find the 4 corners of the dominant document, or None."""
    ratio = 1000.0 / img.shape[0]
    small = cv2.resize(img, (int(img.shape[1] * ratio), int(img.shape[0] * ratio)))
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(gray, 50, 150)
    edges = cv2.dilate(edges, np.ones((3, 3), np.uint8), iterations=1)
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    contours = sorted(contours, key=cv2.contourArea, reverse=True)[:5]
    for c in contours:
        peri = cv2.arcLength(c, True)
        approx = cv2.approxPolyDP(c, 0.02 * peri, True)
        if len(approx) == 4:
            pts = approx.reshape(4, 2).astype("float32") / ratio
            return order_points(pts)
    return None


def four_point_transform(img, pts):
    rect = order_points(np.array(pts, dtype="float32"))
    (tl, tr, br, bl) = rect
    width_a = np.linalg.norm(br - bl)
    width_b = np.linalg.norm(tr - tl)
    max_w = int(max(width_a, width_b))
    height_a = np.linalg.norm(tr - br)
    height_b = np.linalg.norm(tl - bl)
    max_h = int(max(height_a, height_b))
    dst = np.array([[0, 0], [max_w - 1, 0], [max_w - 1, max_h - 1], [0, max_h - 1]],
                   dtype="float32")
    m = cv2.getPerspectiveTransform(rect, dst)
    return cv2.warpPerspective(img, m, (max_w, max_h))


# --------------------------------------------------------------------------
# Filters
# --------------------------------------------------------------------------

def _rotate(img, angle):
    if angle == 0:
        return img
    opts = {90: cv2.ROTATE_90_CLOCKWISE, 180: cv2.ROTATE_180,
            270: cv2.ROTATE_90_COUNTERCLOCKWISE}
    return cv2.rotate(img, opts.get(angle, cv2.ROTATE_90_CLOCKWISE))


def filter_color(img):
    """Gentle enhancement: white balance-ish + contrast via CLAHE on L channel."""
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    l = clahe.apply(l)
    return cv2.cvtColor(cv2.merge((l, a, b)), cv2.COLOR_LAB2BGR)


def filter_gray(img):
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    g = cv2.GaussianBlur(g, (0, 0), 1.0)
    return g


def filter_bw(img):
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    g = cv2.medianBlur(g, 3)
    bw = cv2.adaptiveThreshold(g, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                               cv2.THRESH_BINARY, 35, 12)
    return bw


def filter_magic(img):
    """Background / shadow removal: estimate background and divide it out."""
    img = filter_color(img)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    bg = cv2.dilate(gray, np.ones((7, 7), np.uint8), iterations=3)
    bg = cv2.medianBlur(bg, 21)
    diff = cv2.divide(gray, bg, scale=255)
    norm = cv2.normalize(diff, None, 0, 255, cv2.NORM_MINMAX)
    return norm


_FILTERS = {
    "original": lambda x: x,
    "color": filter_color,
    "gray": filter_gray,
    "bw": filter_bw,
    "magic": filter_magic,
}


# --------------------------------------------------------------------------
# Public
# --------------------------------------------------------------------------

def process_image(img, options: ProcessOptions | None = None):
    _require_cv()
    options = options or ProcessOptions()
    img = _rotate(img, options.rotate)

    # Crop / perspective
    corners = options.corners
    if corners is None and options.auto_crop:
        corners = detect_document_corners(img)
    if corners is not None:
        try:
            img = four_point_transform(img, corners)
        except Exception:
            pass  # bad geometry -> keep original

    fn = _FILTERS.get(options.filter, filter_magic)
    return fn(img)


def images_to_pdf(image_paths: Sequence[str | Path], out_path: str | Path) -> Path:
    """Losslessly bundle JPEG pages into a PDF. Uses img2pdf if available,
    else falls back to Pillow (which re-encodes)."""
    image_paths = [Path(p) for p in image_paths]
    out_path = Path(out_path)
    try:
        import img2pdf  # type: ignore
        out_path.write_bytes(img2pdf.convert([str(p) for p in image_paths]))
        return out_path
    except Exception:
        from PIL import Image  # type: ignore
        imgs = []
        for p in image_paths:
            im = Image.open(p).convert("RGB")
            imgs.append(im)
        first, rest = imgs[0], imgs[1:]
        first.save(out_path, "PDF", resolution=150.0, save_all=True,
                   append_images=rest)
        return out_path
