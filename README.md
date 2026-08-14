# Faseeh Scan

An encrypted personal document vault with a privacy-first scanner. Scan or
import any document — IDs, education papers, property files, receipts, and
yes, medical reports too — it is encrypted on your device and backed up to
**your own Google Drive**, readable only with **your password**.

It started from a simple problem: patients traveling hundreds of kilometers
with one folder of paper reports, losing everything if that folder was lost.
The same problem applies to almost every important paper a person owns, so
Faseeh Scan is a general vault, with great scanning at its heart. No central
server ever sees plaintext.

> **Zero-knowledge by design.** Files are encrypted with AES-256-GCM on the
> device before they leave it. The password never leaves the device. Google
> Drive only ever stores encrypted bytes — there is no password reset, and no
> one (including us) can recover the data if the password is lost.

---

## Current status

Core is in place and tested; features are added through pluggable backends.

- 🔐 Encrypted vault (Argon2id + AES-256-GCM, wrapped master key, tamper detection)
- 📄 Add any document (PDF/images/files) — originals stored as-is, encrypted on disk
- 🔓 Unlock/lock, change password without re-encrypting files
- 🗂️ List, decrypt-to-file, delete; tags, notes, star; OCR/thumbnail sidecars
- ☁️ Back up ciphertext to your **own Google Drive** (`drive.file` scope), or a local folder
- 📱 **Google sign-in on desktop, web, and Android** via Flet's built-in OAuth
- 🧩 **Pluggable architecture** for capture, processing, OCR, and storage — new backends
  register themselves; missing optional packages simply aren't offered
- 📷 Capture framework + OpenCV document processing (edge crop, perspective, filters,
  PDF assembly); ML Kit native scanner wired as a drop-in Flet extension (Android)
- 📱 Cross-platform Python UI built with [Flet](https://flet.dev) (`flet build apk`)

See **[ARCHITECTURE.md](ARCHITECTURE.md)** for the flexible-core design and build
order, **[PLAN.md](PLAN.md)** for the broader roadmap, and
**[docs/ANDROID_BUILD.md](docs/ANDROID_BUILD.md)** for Android signing/OAuth.

---

## Project structure

```
faseeh_scan/
├── crypto.py              # Argon2id + AES-256-GCM, wrapped master key
├── vault.py               # Local encrypted store + metadata + artifacts
├── services.py            # Thin orchestrators (vault/documents/backup)
├── backends/              # Pluggable storage (local, Google Drive)
├── features/
│   ├── capture/           # Pluggable capture providers + service
│   │   ├── base.py        # registry: filepicker (always), mlkit (Android)
│   │   └── service.py     # capture -> process -> PDF -> encrypt
│   ├── processing/        # OpenCV pipeline: crop, perspective, filters
│   └── ocr/               # Pluggable OCR (RapidOCR/Tesseract), English only
└── ui/app.py              # Flet application
extensions/faseeh_scan_mlkit/  # Flet extension wrapping Google ML Kit scanner
main.py
tests/test_core.py
```

### How the encryption works

1. A random **master key** (256-bit) is generated on vault creation. Every
   report is encrypted with AES-256-GCM under this key.
2. The master key is **wrapped** (encrypted) with a **key-encryption key**
   derived from the user's password via **Argon2id** (memory-hard,
   brute-force resistant).
3. Changing the password only re-wraps the master key — reports are not
   re-encrypted.
4. Each report is a self-contained container: `magic | version | nonce |
   ciphertext+tag`. GCM authenticates the data, so a corrupted or tampered
   file is detected and refused.

---

## Getting started (desktop)

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
pip install -e .
python main.py                     # opens the desktop app
```

Run the core tests (no GUI):

```bash
python -m tests.test_core
```

---

## Enabling Google Drive backup

The local-folder backend works with zero setup. To back up to Google Drive,
sign in with Google inside the app ("Sign in with Google" in the sidebar).

### Configure OAuth credentials

1. Copy `.env.example` to `.env`.
2. In [Google Cloud Console](https://console.cloud.google.com/), create a
   project and enable the **Google Drive API**.
3. Configure the OAuth consent screen and create a **Web application** OAuth
   client (Flet performs the token exchange server-side, even on mobile). Add
   the redirect URI `http://localhost/oauth_callback`.
4. For Android, also create an **Android** OAuth client with package name
   `com.faseeh.scan` and your signing key's SHA-1.
5. Put the **Web client's** id/secret in `.env` as `GOOGLE_CLIENT_ID` and
   `GOOGLE_CLIENT_SECRET`.

Both `.env` and `credentials/` are git-ignored — never commit them.

Full Android build, SHA-1, and release-signing instructions:
[docs/ANDROID_BUILD.md](docs/ANDROID_BUILD.md).

### Building for Android

```bash
flet build apk
```

The Flet OAuth flow opens an in-app web view on Android and intercepts the
callback automatically — no platform-specific auth code is needed.

---

## Roadmap

- [ ] Android OAuth flow for Google Drive
- [ ] **Document scanning** — OpenCV edge detection / perspective crop / de-skew (the "CamScanner" step), with an optional high-performance C++ path
- [ ] **OCR** — Tesseract and/or PaddleOCR/docTR (on-device; extract text so reports become searchable)
- [ ] **Auto-organize** — detect report type, lab, date; smart folders
- [ ] **Vector search** (opt-in) — local embeddings + FAISS/Chroma for "find my cholesterol test from 2023"
- [ ] **Share access** — time-limited, per-report decryption tokens / capability links for a doctor
- [ ] Multiple cloud providers (OneDrive, Dropbox, S3-compatible)
- [ ] Biometric unlock on mobile

## Security notes

- There is **no password reset**. If the password is lost, data is unrecoverable. This is the cost of zero-knowledge encryption; the app warns about this at setup.
- Argon2 parameters can be tuned in `crypto.py` for device capability.
- `secure_delete` is best-effort; on flash storage the hardware may retain copies.
- This is an early MVP. Before relying on it for irreplaceable data, get a security review of `crypto.py` and `vault.py`.

## License

Apache License 2.0 — see [LICENSE](LICENSE).
