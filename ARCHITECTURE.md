# Architecture — Faseeh Scan (feature plan)

This document describes HOW features are added. The goal: after a short
foundation refactor, adding a feature (scanner, OCR, PDF tools, a cloud
provider, a search engine) is as close to "install a package + register a
class" as possible.

The product is a **general, encrypted document vault** with a great scanner
built in. "Medical reports" is just one use, not a hardcoded category.

---

## 1. Guiding principles

1. **Core is small and stable.** Encryption, storage, and the document model
   never import OpenCV, OCR, or cloud SDKs. Features cannot break the vault.
2. **Everything is a backend behind a Protocol/ABC.** A feature implements an
   interface and registers itself. The app picks the best available backend at
   runtime.
3. **The original file is sacred.** We store the PDF/image exactly as captured.
   Derived data (OCR text, thumbnails, AI guesses) is a separate *artifact*,
   also encrypted, and never overwrites the original.
4. **Offline first, optional network.** All capture/processing/viewing works
   without internet. Network is only for backup.
5. **Graceful degradation.** If ML Kit or an optional dependency isn't present
   (wrong platform, missing package), the app falls back to the next backend —
   it never crashes on import. Optional packages are lazy-imported inside their
   backend classes.
6. **Plain English OCR only.** No Urdu/Arabic/Hindi OCR in v1.

---

## 2. Layered architecture

```
┌──────────────────────────── Flet UI (thin) ────────────────────────────┐
│  lock │ home/timeline │ capture flow │ document viewer │ settings       │
└───────────────────────────────┬────────────────────────────────────────┘
                                │ uses services (interfaces)
┌───────────────────────────────▼────────────────────────────────────────┐
│  services/  — orchestration, no UI                                     │
│    vault_service   capture_service   documents_service                  │
│    backup_service  search_service                                    │
└──┬───────────────┬───────────────┬───────────────┬────────────────────┘
   │               │               │               │
┌──▼─────┐   ┌─────▼──────┐   ┌────▼─────┐   ┌─────▼──────┐
│ vault  │   │ capture/   │   │ ocr/     │   │ backends/  │
│ crypto │   │ processing │   │ search   │   │ storage    │
└────────┘   └────────────┘   └──────────┘   └────────────┘
   core = stable, no optional deps; feature dirs = pluggable packages
```

---

## 3. Plugin / extension model

Each optional capability has:

- a **Protocol/ABC** in that feature's `base.py`;
- a **registry** mapping a string id → class;
- a `register()` decorator;
- a `available()` function listing backends whose imports succeed;
- a `default()` function that picks the best available one.

Example shape (used everywhere):

```python
class OcrEngine(Protocol):
    id: str
    def is_available(self) -> bool: ...
    def extract(self, image_or_pdf: bytes, content_type: str) -> str: ...

_ENGINES: dict[str, type[OcrEngine]] = {}

def register(cls): _ENGINES[cls.id] = cls; return cls

def available() -> list[OcrEngine]:
    out = []
    for cls in _ENGINES.values():
        try:
            inst = cls()
            if inst.is_available(): out.append(inst)
        except Exception:
            continue  # optional dependency missing
    return out
```

A new feature is therefore: **write a class, decorate `@register`, add its
dependency to `extras_require`/requirements.** No edits to core or UI call
sites — the UI asks the registry for the default backend.

Native ML Kit is delivered as a **Flet extension** (a small Flutter package we
add to `pyproject.toml`). The Python `capture` backend imports it lazily; if
it isn't present (desktop/web), it reports unavailable and the app uses the
gallery/file picker and OpenCV processing instead.

---

## 4. Flexible core changes (do these FIRST)

### 4.1 Generalize the domain object
- Rename `ReportMeta` → `DocumentMeta`.
- Fields: `id, name, content_type, size, created_at, encrypted_size,
  note, tags[], starred, source, original_sha256, artifacts{}, backed_up_to[]`.
- A document can be a **multi-page file** (PDF) or a single image.
- `artifacts{}` maps keys like `"ocr"`, `"thumb"`, `"scan_enhanced"` →
  encrypted sidecar file ids. Originals are never replaced.

### 4.2 Storage paths & filenames
- Store data as `data/<id>.bin` (content type lives in metadata). Backups sync
  ciphertext blobs; we don't leak original filenames to the cloud.
- Consider encrypting file names too (Cryptomator-style AES-SIV) in a later pass.

### 4.3 Service layer (`services/`)
Thin orchestrators so the UI never talks to vault+backend+ocr directly:
- `VaultService` — create/unlock/lock/change password/recovery key.
- `DocumentsService` — add/get/delete/list/tag/star; attach artifacts.
- `CaptureService` — run a capture provider through a processing pipeline, then
  hand the final PDF/image to `DocumentsService`.
- `BackupService` — choose a storage backend, back up/restore, report health.
- `SearchService` — filename + OCR text search; pluggable later (full-text now,
  semantic later).

### 4.4 Feature flags / settings
A simple `Settings` object (stored locally, encrypted where sensitive):
which capture backend, OCR on/off, Wi-Fi-only upload, default filter, etc.
Allows features to be toggled without code changes.

---

## 5. Feature build order, code sources & libraries

### Phase F — Flexible foundation (this turn)
- Refactor to the `documents` model, services, registries.
- **Libraries:** existing `cryptography`, `argon2-cffi` only.
- Keep all tests green; update them to the new names.

### Phase 1 — Capture & scanner
Two separable parts:
- **Capture (native):** Google ML Kit Document Scanner
  (`play-services-mlkit-document-scanner`) wrapped in a **Flet extension**
  (`src/flutter/faseeh_scan_mlkit/`). On-device; returns PDF + JPEGs.
  Fallback on all platforms: Flet `FilePicker` (gallery/files).
- **Processing (cross-platform, Python):**
  - `opencv-python-headless` + `numpy` — page crop, perspective warp,
    adaptive threshold, shadow cleanup, magic-color.
  - `Pillow` — image i/o, filters, thumbnail.
  - `img2pdf` — lossless JPEG→PDF assembly (no re-encoding).
  Code sources/references: the well-established OpenCV "document scanner"
  pipeline, and open apps Scanly / MakeACopy (MIT/Apache) for filter tuning.
- Result: scan → processed **PDF and/or image**, stored as the original.

### Phase 2 — Organize & find (no bloat)
- Folders/tags, star, rename, notes, sort, grid/list, multi-select.
- **OCR (English only):** pluggable backend.
  - On Android ML Kit text recognition via the Flet extension (best, on-device).
  - Cross-platform fallback: **RapidOCR** (PaddleOCR via ONNX) — pip-install,
    CPU, no system binary, ~50–80 MB.
  - Text saved as encrypted `ocr` artifact; used for search only.
- Search: filename + OCR text, local, instant. (Chroma/vector is a later opt-in.)

### Phase 3 — Smooth workflows
- "Share to Faseeh Scan" system share-sheet target.
- Home-screen quick-action / shortcut straight to scan.
- Wi-Fi-only auto-backup + backup health dot; undo-delete; recent docs row.
- PDF page tools: reorder/rotate/delete, merge documents (using `pypdf`).
- Compression quality (small/recommended/original).
- Full export of decrypted originals (no lock-in).
- Biometric lock later (Flet/Flutter plugin).

### Deferred explicitly
Sign/stamp, expiry dashboard, non-English OCR, AI diagnosis chat, family
sharing — not in v1.

---

## 6. Where code comes from (honest list)

| Need | Library / source | License | Installs as |
|---|---|---|---|
| Encryption | `cryptography`, `argon2-cffi` | BSD/Apache/MIT | pip (core) |
| Native scanner (Android) | Google ML Kit Doc Scanner via Flet extension | Apache 2.0 | pyproject flutter dep |
| Image processing | `opencv-python-headless`, `numpy`, `Pillow` | Apache/BSD | pip extra `[scan]` |
| Images→PDF | `img2pdf` | LGPL | pip extra `[scan]` |
| OCR (cross-platform) | RapidOCR / ONNX Runtime | Apache 2.0 | pip extra `[ocr]` |
| PDF page tools | `pypdf` | BSD | pip extra `[pdf]` |
| Drive backup | `google-api-python-client`, `google-auth*` | Apache 2.0 | pip extra `[gdrive]` |
| UI | Flet | Apache 2.0 | pip core |

All optional heavy deps are **extras**, not forced on everyone:
`pip install faseeh-scan[scan,ocr]`, etc.
