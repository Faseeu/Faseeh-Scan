# Building Faseeh Scan

## Quickest safe test — run in your browser

No phone, no emulator, no risk to any device data:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[scan,pdf,gdrive]"
pip install flet-desktop
flet run --web main.py
```

Then open the printed URL (typically http://localhost:8550) in your browser.
This runs the full app UI exactly as it will appear on Android — file picker,
scan review, drag-and-drop, search, dark mode, etc.

## Online emulator

A free browser Android emulator (e.g. Appetize.io) can load a debug APK, but
producing the APK still requires the Android/Flutter SDK. The browser run above
is simpler and just as representative for UI testing.

## Build the Android APK

Requires JDK 17, Android SDK, and internet access so Flet can download Flutter:

```bash
pip install -e ".[scan,pdf,gdrive,ocr]"
pip install flet flet-desktop

# install the Flet native extensions (share, quick actions, biometrics)
./scripts/build_apk.sh release
```

The script runs `flet build apk`, which bootstraps Flutter, compiles the app and
extensions, and produces `build/apk/build/app/outputs/flutter-apk/app-release.apk`.

### What gets compiled in

- Core: encryption, vault, OCR (RapidOCR/ONNX), PDF tools, thumbnails
- Flet extensions: `faseeh_share` (receive shared files),
  `faseeh_quick_actions` (long-press shortcut), `faseeh_local_auth` (biometrics)
- ML Kit document scanner is off by default; uncomment the dependency in
  `pyproject.toml` and install `extensions/faseeh_scan_mlkit` to enable it.
