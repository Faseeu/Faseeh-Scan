# Medical Reports Backup

A patient-owned, end-to-end encrypted backup for medical reports — stored in
**your own Google Drive**, readable only with **your password**.

Patients often travel hundreds of kilometers carrying a single folder of paper
reports. If that folder is lost, forgotten, or damaged, their medical history
is gone. This app turns a phone into a secure backup: photograph or import a
report, it is encrypted on-device, and the ciphertext is synced to the
patient's own cloud. No central server ever sees plaintext.

> **Zero-knowledge by design.** Files are encrypted with AES-256-GCM on the
> device before they leave it. The password never leaves the device. Google
> Drive only ever stores encrypted bytes — there is no password reset, and no
> one (including us) can recover the data if the password is lost.

---

## MVP status

This first version delivers the core that matters: **never lose a report**.

- 🔐 Create an encrypted vault protected by a password (Argon2id + AES-256-GCM)
- 📄 Add reports (PDF, images, documents) — encrypted instantly on disk
- 🔓 Unlock / lock the vault; change password without re-encrypting files
- 🗂️ List, open (decrypt to a file), and delete reports
- ☁️ Back up the encrypted vault to the user's **own Google Drive** (`drive.file` scope)
- 📱 **Google sign-in on desktop, web, and Android** through Flet's built-in OAuth (one code path, works in the APK)
- 📂 Local-folder backend (works immediately, no credentials — good for USB/SD backup)
- 📱 Cross-platform Python UI built with [Flet](https://flet.dev) — runs on desktop and builds to Android (`flet build apk`)

See **[PLAN.md](PLAN.md)** for the full feature roadmap, threat model, and the
open-source components chosen for scanning, OCR, search, and sharing. Android
build/sign-in instructions are in **[docs/ANDROID_BUILD.md](docs/ANDROID_BUILD.md)**.

OCR, auto-organization, and semantic search are intentionally **out of the MVP**
and tracked in the plan as opt-in features — the app is useful the moment a
report is encrypted and backed up.

---

## Project structure

```
medical_reports/
├── crypto.py              # Argon2id KDF + AES-256-GCM; wrapped master-key vault
├── vault.py               # Local encrypted store + metadata index
├── backends/
│   ├── base.py            # StorageBackend interface
│   ├── local.py           # Local folder / USB backup
│   └── gdrive.py          # Google Drive backup (optional)
└── ui/
    └── app.py             # Flet application (lock screen, reports, backup)
main.py                    # Entry point: python main.py
tests/test_core.py         # Core crypto/vault/backend tests
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
   `com.faseeu.medicalreports` and your signing key's SHA-1.
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
