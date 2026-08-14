# Product & Technical Plan — Medical Reports Backup

> Status: draft for review. Nothing here is implemented unless checked off in
> the "Build status" column. This document exists so we agree on *what* to
> build and *which open-source pieces* do the heavy lifting before code is
> written.

## 1. The problem (in the patient's words)

- Patients travel hours / hundreds of km to see specialists, carrying a single
  physical folder of reports.
- Losing that folder — or forgetting one report at home on the way — means the
  consultation can't happen or has to be repeated.
- There is no backup they control, and no easy way to know what they even have.

## 2. Core promise

**A patient-owned, end-to-end encrypted copy of every report, in the patient's
own Google Drive, reachable from their phone. No central server sees plaintext.**

Everything else (OCR, search, smart organization, sharing) is a layer on top of
that promise and must not weaken it.

## 3. Threat model & non-negotiables

- **Zero-knowledge storage.** The cloud (Google Drive) stores only
  AES-256-GCM ciphertext. The password and master key never leave the device.
- **No password reset.** Loss of password = loss of data (warned at setup).
  This is the trade-off for zero-knowledge.
- **Local-first.** The app works offline for capture/view; sync is background.
- **Least-privilege OAuth.** `drive.file` scope only — the app sees just the
  folder it created, nothing else in the user's Drive.
- **Tamper detection.** GCM authentication tags reject corrupted/modified files.
- **No analytics / no telemetry of report content.** Crash reporting, if added,
  must be opt-in and contain no PHI.
- Before a 1.0 release, `crypto.py` + key handling need an independent security
  review. This is an MVP, not yet medical-grade certified software.

## 4. Feature map

Legend: 🔴 MVP · 🟡 next · 🟢 later / opt-in

| # | Feature | Why it matters | Pri | Open-source building blocks |
|---|---------|----------------|-----|------------------------------|
| 1 | Encrypted local vault | Never lose a report locally | 🔴 | `cryptography` (AES-256-GCM), `argon2-cffi` |
| 2 | Password / change password | Access control | 🔴 | Argon2id KDF (in `cryptography`/`argon2-cffi`) |
| 3 | Google Drive backup (own account) | Off-device backup, patient-owned | 🔴 | Google Drive API v3, Flet `GoogleOAuthProvider` |
| 4 | Local-folder backup (USB/SD) | Works with zero accounts | 🔴 | Python stdlib |
| 5 | Android Google login | Mobile is the real device | 🔴 | Flet `page.login()` (OAuth, works on Android via `flet://` redirect) |
| 6 | Camera capture + "scan" a page | Replace CamScanner; paper → digital | 🟡 | Flet camera / `image_picker`; **OpenCV** edge detect + perspective warp + adaptive threshold (see §5) |
| 7 | OCR → searchable text | Know what a report *says* | 🟡 | **RapidOCR** (PaddleOCR models via ONNX, ~50–80MB, CPU, no system binary); Tesseract as fallback |
| 8 | Metadata / tagging / dates | Organize, find by hospital/date | 🟡 | stdlib; OCR-assisted date/title detection |
| 9 | In-app report viewer | Show PDFs/images without leaving app | 🟡 | Flet PDF/image viewers; or decrypt-to-cache + system viewer |
| 10 | Multi-profile (family members) | One phone, several family members' files | 🟡 | Separate wrapped master keys per profile |
| 11 | Full-text + semantic search | "Find my 2023 cholesterol test" | 🟢 | **Chroma** (local, embedded, metadata filter, HNSW, Apache-2.0) + ONNX embeddings (e.g. `bge-small` via `fastembed`) |
| 12 | Secure share with a doctor | Time-limited access to one report | 🟢 | Per-report content key + capability link; **`age`** public-key encryption (`pyrage`) or libsodium sealed boxes |
| 13 | Document auto-classification | Blood test vs X-ray vs prescription | 🟢 | Lightweight classifier on OCR text / image embeddings |
| 14 | Other clouds (OneDrive/Dropbox/S3) | Vendor choice | 🟢 | MS Graph / Dropbox / boto3 behind the same `StorageBackend` interface |
| 15 | Biometric unlock | Convenience on mobile | 🟢 | Platform keychain via Flet/Flutter plugins |
| 16 | Conflict-free sync / multi-device | Phone + laptop edits | 🟢 | File manifest with content hashes; last-writer-wins per report |

## 5. Recommended open-source stack (with rationale)

### UI / app shell
- **Flet** (Apache-2.0) — one Python codebase → desktop, web, **Android APK**
  (`flet build apk`) and iOS. We're already on it. It also ships the OAuth and
  camera/file-picker controls we need, so no Kotlin/Swift is required.

### Encryption
- **`cryptography`** (Apache-2.0/BSD) — AES-256-GCM primitives.
- **`argon2-cffi`** — Argon2id memory-hard KDF for password → key.
- Sharing (later): **`pyrage`** (Python bindings for **age**, BSD-3) — modern,
  audited file encryption with public-key recipients; ideal for "encrypt this
  one report to the doctor's public key" without exposing the master key.

### Document scanning (the "CamScanner" step)
OpenCV-based pipeline, reusing the well-established approach from projects like
[`LiteObject/doc-scanner`](https://github.com/LiteObject/doc-scanner) and
[`YegorCherov/document-scanner`](https://github.com/YegorCherov/document-scanner)
(both MIT):
1. grayscale → Gaussian blur → Canny edges
2. largest 4-point contour → order corners → `getPerspectiveTransform` + warp
3. adaptive threshold / CLAHE / unsharp mask for a clean "scan"

`opencv-python` + `numpy` is enough for a Python-first version. If profiling
shows the warp/threshold loop is too slow on low-end Android phones, the same
OpenCV calls exist natively in C++ (OpenCV *is* C++ under the hood) and can be
moved behind a native extension — but **measure first**; Python OpenCV calls
into C++ per operation, so it's usually fast enough.

### OCR
- **RapidOCR** (Apache-2.0) is the recommended default: it runs PaddleOCR's
  trained models through **ONNX Runtime**, so there's no PaddlePaddle framework
  dependency, ~50–80MB install, CPU-only, and no system binary to ship — which
  matters enormously on Android.
- **Tesseract** (Apache-2.0) via `pytesseract` as a tiny fallback for clean
  scans, but it requires shipping the native binary + language packs and is
  weak on noisy phone photos.
- Keep OCR **behind an interface and a settings toggle**, and store extracted
  text encrypted alongside the report — it should never be required for backup.

### Search
- For a personal vault (hundreds to low thousands of reports), **Chroma**
  (embedded, HNSW, SQLite metadata, Apache-2.0) is the right default: zero
  server, easy persistence, metadata filtering by date/type.
- **FAISS** (MIT, Meta) stays as a future swap if we ever need raw speed at
  scale, but it's a library without persistence or metadata, so it's more code.
- Embeddings via **`fastembed`** (Apache-2.0) running a small model like
  `BAAI/bge-small-en-v1.5` locally on ONNX Runtime — no API calls, no cloud.

### Cloud storage
- **Google Drive API v3** (`google-api-python-client`, Apache-2.0) with the
  `drive.file` scope. The same `StorageBackend` abstraction already in
  `backends/` lets us add OneDrive (MS Graph), Dropbox, or S3-compatible
  storage later without touching crypto.

## 6. Architecture (target)

```
┌──────────────────────────── Flet UI (desktop/web/android) ────────────────────────────┐
│  lock screen │ reports list │ camera/scan │ add file │ search │ share │ settings       │
└───────────────┬───────────────────────────────────────────────────────────────────────┘
                │
        ┌───────▼────────┐
        │  vault.py       │  encrypted local store + metadata
        └───────┬────────┘
                │ uses
        ┌───────▼────────┐
        │  crypto.py      │  Argon2id → KEK → wrap master key; AES-256-GCM per report
        └─────────────────┘
                │ syncs ciphertext only
   ┌────────────▼───────────────────────────────────┐
   │ StorageBackend (interface)                      │
   │  LocalBackend │ GoogleDriveBackend │ (future)…  │
   └─────────────────────────────────────────────────┘

Optional layers (each reads plaintext only after unlock, on-device):
   scanner.py (OpenCV)  →  ocr.py (RapidOCR)  →  search.py (Chroma + fastembed)
```

Key principle: **capture → encrypt → sync is the critical path.** Scanning,
OCR, and search are optional post-processing steps that run on decrypted data
on the device and store their derived artifacts *also encrypted*.

## 7. Data model

```
ReportMeta:
  id              random hex
  name            original filename
  content_type    MIME
  size            plaintext bytes
  created_at      unix ts
  encrypted_size  bytes on disk
  note            user note
  tags[]          user/auto tags
  report_date     detected or user-set
  ocr_text_ref    id of encrypted OCR artifact (nullable)
  backed_up_to[]  backend ids
```

The master key wraps per-report content keys in a future version (so a single
report can be shared without exposing everything). For the MVP, all reports
live under the master key, which is simpler and correct for single-user.

## 8. Build phases (proposed order)

- **Phase 0 — foundation (done):** crypto, vault, backends, Flet shell, tests.
- **Phase 1 — mobile login & Drive (in progress):** Flet Google OAuth that
  works on Android; feed access token into `GoogleDriveBackend`; APK build.
- **Phase 2 — capture & scan:** camera/gallery import; OpenCV scan pipeline;
  encrypt the scanned image/PDF.
- **Phase 3 — OCR & organize:** RapidOCR toggle; extract text; tags/dates;
  in-app viewer.
- **Phase 4 — search:** encrypted full-text first, then optional local
  embeddings + Chroma for semantic search.
- **Phase 5 — secure share:** per-report keys + age recipients / capability
  links with expiry.
- **Hardening pass:** biometric unlock, multi-profile, multi-cloud, audit.

## 9. Open questions for you

1. **Distribution** — side-loaded APK first, or aim for Google Play (which adds
   review/policy steps, especially for health-related apps)?
2. **Languages/region** — do we need Urdu/Arabic/Hindi OCR and UI translation
   early? This affects OCR model choice and UX.
3. **Accounts** — strictly "bring your own Google," or is a no-account local /
   LAN-share mode important for patients without Google accounts?
4. **Doctor share model** — should sharing be a link the doctor opens in a
   browser (we'd host a tiny static decrypt page), or an in-app code?
5. **Compliance posture** — is this personal/community tooling, or do you
   eventually need to think about HIPAA/equivalent regulation? (This changes
   scope substantially.)
