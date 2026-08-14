# Building & running on Android

The app is a Python/Flet app and builds to a standard Android APK with
`flet build apk`. Google sign-in works on Android through Flet's built-in
OAuth (an in-app web view completes the flow and Flet intercepts the
callback) — there is no Kotlin/Java auth code to maintain.

## 1. Prerequisites

On the machine doing the build:

- Python 3.10+ with the project's virtualenv active (`pip install -e .`)
- The [Flet CLI](https://flet.dev/docs/publish/android/) (`flet build apk`
  bootstraps Flutter + the Android SDK on first run)
- A Java JDK (17 recommended)
- On Linux: `git`, `curl`, `unzip`, `xz-utils`, `zip`, `libglu1-mesa`
- Enough disk space (~first run downloads ~2 GB of Android toolchain)

## 2. Google Cloud setup (one-time)

Google sign-in needs two OAuth clients in
[Google Cloud Console](https://console.cloud.google.com/) for the same
project, with the **Google Drive API** enabled:

1. **OAuth consent screen** — User type "External", add yourself as a test
   user while publishing status is "Testing".
2. **Web application client** (this is what Flet uses for the token exchange,
   even on mobile). Note its **Client ID** and **Client secret**.
   - Authorized redirect URI: `http://localhost/oauth_callback`
3. **Android client** — this registers the app with Google so account
   selection works on-device. It has **no secret**.
   - Package name: `com.faseeu.medicalreports`
   - SHA-1 certificate fingerprint of the signing key (see below).

Put the **Web client's** id/secret into `.env`:

```
GOOGLE_CLIENT_ID=xxxxx.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=GOCSPX-xxxxx
```

The `.env` file is bundled at build time; to avoid embedding the secret in
the APK, you can instead pass them as build-time environment variables in
CI (see "Bundling config" below).

## 3. SHA-1 fingerprints

Google needs the SHA-1 of the key that signs the APK.

- **Debug** (for `flet run --android` or installing debug builds): the Flet/
  Flutter tooling generates a debug keystore at
  `~/.android/debug.keystore` (alias `androidandroid`, password `android`).
  Get its SHA-1 with:
  ```bash
  keytool -list -v -keystore ~/.android/debug.keystore \
    -alias androiddebugkey -storepass android -keypass android \
    | grep SHA1
  ```
- **Release** (for distribution): create your own upload keystore once:
  ```bash
  keytool -genkey -v -keystore upload-keystore.jks -keyalg RSA \
    -keysize 2048 -validity 10000 -alias upload
  ```
  Then build signed:
  ```bash
  flet build apk --release \
    --android-signing-key-store upload-keystore.jks \
    --android-signing-key-store-password "$STORE_PASS" \
    --android-signing-key-password "$KEY_PASS"
  ```
  Register **both** the debug and release SHA-1 fingerprints in the Android
  OAuth client so sign-in works in both modes.

## 4. Build & install

```bash
# Debug APK (output: build/apk/app-release.apk or build/app/outputs/... )
flet build apk

# Install on a connected device (USB debugging enabled):
flet install android

# Or run directly to a connected device/emulator:
flet run --android
```

The redirect URL is handled automatically:

- **Desktop/web:** browser redirects to `http://localhost/oauth_callback`.
- **Android:** Flet opens an in-app web view and catches the callback; no
  manual `intent-filter` is required beyond the deep-linking scheme in
  `pyproject.toml` (`[tool.flet.android.deep_linking] scheme = "flet"`).

## 5. Bundling config / avoiding secrets in the APK

`faseeh_scan/config.py` reads `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET`
from environment variables, falling back to a local `.env`.

For release builds, set them in the build environment instead of committing
`.env`:

```bash
GOOGLE_CLIENT_ID=... GOOGLE_CLIENT_SECRET=... flet build apk --release
```

> Note: the Web client secret cannot be truly hidden in an installed client
> app. This is inherent to OAuth for installed apps. Using the `drive.file`
> scope limits blast radius, and tokens are short-lived. A future hardening
> step can move the token exchange to a tiny server-side proxy if needed.

## 6. Troubleshooting

- **`redirect_uri_mismatch`** — the redirect URI in the Google Cloud Web
  client must be *exactly* `http://localhost/oauth_callback`.
- **`Access blocked: authorization error` / "app not verified"** — add your
  account as a test user on the OAuth consent screen, or publish/push the app
  to production.
- **Sign-in works on desktop but not on the phone** — almost always a missing
  SHA-1 for the signing key in the Android OAuth client, or a mismatch between
  the package name (`com.faseeu.medicalreports`) and what's registered.
- **403 / access denied after sign-in** — confirm the Drive API is enabled
  for the project.
