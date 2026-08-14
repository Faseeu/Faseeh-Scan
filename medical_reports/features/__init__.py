"""Optional, pluggable features (capture, processing, OCR, search...).

Each subpackage defines an interface, backends that implement it, and a
registry. Backends register themselves on import; their heavy/optional
dependencies are imported lazily inside is_available() so a missing package
never breaks the app — that backend simply isn't offered.
"""
