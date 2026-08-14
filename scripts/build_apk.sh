#!/usr/bin/env bash
# Build the Faseeh Scan Android APK with native Flet extensions wired in.
#
# Usage:
#   ./scripts/build_apk.sh [debug|release]
#
# Prerequisites:
#   - Python 3.10+ venv with the project installed: pip install -e .[scan,ocr,pdf]
#   - JDK 17, Android SDK (flet build bootstraps the Flutter toolchain on first run)
#   - For release signing, set FASEEH_KEYSTORE / *_PASSWORD env vars (see below).
#
# Native Flet extensions are discovered automatically once their Python packages
# are installed: Flet scans each installed package for a flutter/ directory and
# adds it to the generated pubspec.yaml.

set -euo pipefail
cd "$(dirname "$0")/.."

BUILD_MODE="${1:-release}"

echo "==> Installing Faseeh Scan Flet extensions (editable)"
pip install -q -e ./extensions/faseeh_share
pip install -q -e ./extensions/faseeh_quick_actions
pip install -q -e ./extensions/faseeh_local_auth
# ML Kit scanner extension is enabled by uncommenting the dependency in
# pyproject.toml and installing it:
if [ -d ./extensions/faseeh_scan_mlkit ]; then
  pip install -q -e ./extensions/faseeh_scan_mlkit || true
fi

echo "==> Checking Flet sees the extensions"
python - <<'PY'
import importlib.util as u
for name in ("faseeh_share", "faseeh_quick_actions"):
    print(f"  {name}: {'installed' if u.find_spec(name) else 'MISSING'}")
PY

EXTRA_ARGS=()
if [ "$BUILD_MODE" = "release" ] && [ -n "${FASEEH_KEYSTORE:-}" ]; then
  EXTRA_ARGS+=(
    --android-signing-key-store "$FASEEH_KEYSTORE"
    --android-signing-key-store-password "${FASEEH_STORE_PASS:-}"
    --android-signing-key-password "${FASEEH_KEY_PASS:-}"
  )
fi

echo "==> Running flet build apk ($BUILD_MODE)"
flet build apk --$BUILD_MODE "${EXTRA_ARGS[@]}"

cat <<'TIP'

==> Build complete.
APK output: build/apk/

IMPORTANT — apply the share intent filters to the generated manifest:
  build/flutter/android/app/src/main/AndroidManifest.xml
Add the snippet from docs/SHARING_AND_SHORTCUTS.md inside the main <activity>.
Then rebuild with: flet build apk --no-pub --$BUILD_MODE  (or re-run this script)

To register an Android OAuth client for Google Drive sign-in, see
docs/ANDROID_BUILD.md (package name: com.faseeh.scan).
TIP
