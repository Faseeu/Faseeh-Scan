# faseeh_scan_mlkit (Flet extension)

A Flet extension that exposes Google's on-device
[ML Kit Document Scanner](https://developers.google.com/ml-kit/vision/doc-scanner)
to the Python app. The entire scan flow — edge detection, auto-capture,
perspective correction, filters, multi-page — runs **on the phone**, and the
extension returns a PDF and/or JPEGs, which Faseeh Scan then encrypts.

## Status

Scaffold. The Flutter/Dart side mirrors the Flet extension structure and wraps
`google_mlkit_document_scanner`. It must be built with the Flutter SDK and
linked into the main app before the APK can use it (see main app's
`pyproject.toml` → `[tool.flet.flutter.pubspec.dependencies]`). On desktop/web
this extension is absent and the file-picker capture backend is used
automatically.

## Layout

```
faseeh_scan_mlkit/            # Python package (importable)
src/flutter/faseeh_scan_mlkit/
  pubspec.yaml
  lib/faseeh_scan_mlkit.dart  # wraps the ML Kit plugin
```

## Notes

- ML Kit Document Scanner is Android-only and requires Google Play Services.
  The cross-platform fallback is OpenCV processing + system file picker.
- No document data leaves the device during scanning.
