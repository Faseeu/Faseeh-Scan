"""Image processing pipeline for scanned documents.

Pure-Python/OpenCV, works on desktop and mobile (opencv-python-headless is
cross-platform). None of this is required for backup: importing a file as-is
goes straight to the vault. Processing only runs when the user chooses a
filter for a camera capture.
"""

from .pipeline import (
    ProcessOptions,
    load_image,
    process_image,
    save_image,
    images_to_pdf,
    SUPPORTED,
)

__all__ = [
    "ProcessOptions",
    "load_image",
    "process_image",
    "save_image",
    "images_to_pdf",
    "SUPPORTED",
]
