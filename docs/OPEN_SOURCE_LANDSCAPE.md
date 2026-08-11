# Open-Source Landscape

> Researched and checked against upstream repositories on **11 August 2026**. Licenses and project status can change; pin exact versions, retain notices, generate an SBOM, and repeat the review before distribution. This is engineering guidance, not legal advice.

## Executive recommendation

Do not fork a full EMR and do not build a generic backup engine from scratch.

Build a focused desktop experience with:

1. **Tauri + React/TypeScript** for a local-first app.
2. **The interoperable age format through the Rust `age`/`rage` library** for encrypted objects and recoverability.
3. **SQLCipher** for the encrypted local search/index database.
4. **A direct, least-privilege Google Drive adapter** for the first storage provider.
5. **PDF.js + OCRmyPDF/Tesseract** for local document viewing and searchable scans.
6. **Synthea** for safe synthetic test data.

Use medical-record projects as references and optional interoperability modules, not as the product foundation. The closest useful reference is **Mere Medical** for its local-first timeline and SMART-on-FHIR work. **Fasten On-Prem is archived**, so it should not become a new dependency.

## 1. Recommended foundation

| Project | License | What it offers | Recommendation | Important caution |
|---|---|---|---|---|
| [Tauri](https://github.com/tauri-apps/tauri) | MIT OR Apache-2.0 | Small cross-platform desktop shell with a Rust core and web UI. | **Adopt.** Keep file, key, DB, and Drive operations in Rust behind narrow commands. | Tauri does not make an app secure automatically. Lock down capabilities, navigation, CSP, updater, and plugins. |
| [rage / age Rust library](https://github.com/str4d/rage) and [age specification](https://age-encryption.org/v1) | MIT OR Apache-2.0 | Maintained Rust implementation of a documented, interoperable streaming encryption format. | **Prototype and adopt if the security review approves.** It gives an independent recovery path and avoids implementing primitives. | The Rust crate describes itself as beta; wrap it behind an internal interface, pin it, and test format compatibility. Design password/recovery envelope semantics carefully. |
| [SQLCipher](https://github.com/sqlcipher/sqlcipher) | BSD-3-Clause | SQLite fork with authenticated 256-bit database encryption and familiar SQL/FTS behavior. | **Adopt** for local metadata and OCR search. | Validate build flags, key handling, WAL/temp behavior, migrations, and packaging on each OS. Some vendor tooling/support is commercial. |
| [PDF.js](https://github.com/mozilla/pdf.js) | Apache-2.0 | Widely used JavaScript PDF renderer/viewer. | **Adopt** for the in-app PDF experience. | Disable PDF JavaScript, external fetches, embedded launches, and unsafe viewer features. Keep it patched. |
| [OCRmyPDF](https://github.com/ocrmypdf/OCRmyPDF) | MPL-2.0 | Adds searchable OCR layers to PDFs, deskews pages, supports PDF/A, and uses Tesseract. | **Integrate as an isolated worker** or use its pipeline as the benchmark. Preserve the original file. | It also depends on native tools such as Ghostscript and Tesseract. Packaging, sandboxing, binary licenses, and parser CVEs need active management. MPL modifications have file-level source obligations. |
| [Tesseract OCR](https://github.com/tesseract-ocr/tesseract) | Apache-2.0 | Mature local OCR engine with many language packs. | **Adopt through the OCR worker.** Start with a small, tested language set. | OCR text is untrusted and often wrong. Language-data/model licenses and download size need separate review. |
| [Synthea](https://github.com/synthetichealth/synthea) | Apache-2.0 | Synthetic patient histories and FHIR data. | **Adopt for fixtures, demos, and integration tests.** | Generate document-like fixtures around the synthetic data; never copy real reports into tests or bug reports. |

## 2. Backup and cloud projects to reuse or study

| Project | License | Useful capability | Decision |
|---|---|---|---|
| [rclone](https://github.com/rclone/rclone) | MIT | Mature Google Drive and many other storage adapters; `crypt` adds encrypted remotes. | **Study and keep as an escape hatch/provider option.** A bundled subprocess could accelerate multi-cloud support, but direct Drive integration gives a cleaner OAuth UX and smaller permission surface for MVP. |
| [rustic_core](https://github.com/rustic-rs/rustic_core) | MIT OR Apache-2.0 | Embeddable Rust library for encrypted, deduplicated, restic-compatible repositories and snapshots. | **Run a Phase-0 comparison spike.** It may be better than an app-specific object layout if archive sizes or multi-storage needs are large. Its API is explicitly early/subject to change, so hide it behind an internal interface. |
| [restic](https://github.com/restic/restic) | BSD-2-Clause | Mature, documented encrypted backup repository with verification, deduplication, snapshots, and independent restore tooling. | **Study its threat model, append-only object design, verification, and recovery UX.** It is an excellent reference even if not embedded. Google Drive generally requires an rclone bridge. |
| [Kopia](https://github.com/kopia/kopia) | Apache-2.0 | Encrypted, compressed, deduplicated snapshots with a GUI, APIs, and a layered repository design. | **Study its envelope encryption and content-addressed architecture.** Embedding a Go subsystem in a Tauri/Rust app is more operationally complex than needed for MVP. |
| [Cryptomator](https://github.com/cryptomator/cryptomator) | GPL-3.0 | Auditable client-side encryption for cloud-synced files, including names and directory structure; documented vault cryptography. | **Study and use as a competitor/security benchmark.** Do not copy/link GPL code into this Apache-licensed project without an explicit licensing decision. Cryptomator interoperability could be an external integration later. |

### Age objects versus a restic-compatible repository

Resolve this in the first month rather than after UI code depends on storage details.

| Criterion | App-native age objects | `rustic_core` / restic format |
|---|---|---|
| Independent decryption | Excellent: standard age tooling per object | Excellent: restic/rustic tools |
| Selective document access | Simple, one immutable object per artifact | Supported through repository APIs, but more abstraction |
| Deduplication/compression | Must be added or omitted | Built in |
| Snapshot/retention/verification | Must implement a small manifest protocol | Mature model already exists |
| Direct Drive UX | Straightforward custom adapter | Likely custom backend or rclone bridge |
| Rust embedding | `age` library | `rustic_core`, but API is early |
| Format complexity owned here | Manifest/head/key wrappers | Integration and repository semantics |
| Large archives/DICOM | Less efficient without chunk dedupe | Strong fit |

**Initial recommendation:** age-based immutable objects are the clearest fit for a document product and provide easy emergency recovery. Switch to `rustic_core` during Phase 0 if tests show unacceptable Drive object counts, storage use, upload behavior, or recovery complexity. Do not maintain two production vault formats in MVP.

## 3. Personal health record and FHIR references

| Project | License/status on 2026-08-11 | Useful ideas/code | Recommendation |
|---|---|---|---|
| [Mere Medical](https://github.com/cfu288/mere-medical) | MIT; active | Offline-first personal health record, unified timeline, local data, SMART-on-FHIR connections, lab trends, document search. | **Primary product/FHIR reference.** Evaluate reusable FHIR clients and timeline data transforms, but keep backup/security architecture independent. |
| [Medplum](https://github.com/medplum/medplum) | Apache-2.0; active | TypeScript FHIR data types, client libraries, validation and a full healthcare platform. | **Use selected packages, not the entire server**, when FHIR import/export begins. Audit package boundaries and browser persistence behavior. |
| [HAPI FHIR](https://github.com/hapifhir/hapi-fhir) | Apache-2.0; active | Mature Java FHIR client/server/validation ecosystem. | **Use as a conformance test/reference server**, not an embedded desktop dependency. Valuable in CI for FHIR round trips. |
| [Android FHIR SDK / Open Health Stack](https://github.com/ohs-foundation/android-fhir) | Apache-2.0; active | Offline-capable FHIR engine, structured data capture and clinical workflow libraries for Android. | **Revisit for a native Android app.** It is not the right dependency for the desktop MVP, but its offline patterns are relevant. |
| [Fasten On-Prem](https://github.com/fastenhealth/fasten-onprem) | GPL-3.0; archived | Family-oriented PHR, FHIR bundle import, condition dashboards, record aggregation concepts. | **Study only. Do not fork as the base.** It is archived and its current open-source edition does not directly import provider records. |
| [OpenEMR](https://github.com/openemr/openemr) | GPL-3.0; active | Full clinical EHR/practice management and FHIR APIs. | **Do not use as the product base.** It solves provider workflows, not a lightweight patient-owned backup vault. Use only for interoperability testing if needed. |

### FHIR strategy

- MVP stores document-centric records in a small internal model.
- Add FHIR R4 `DocumentReference`, `Binary`, `DiagnosticReport`, `Observation`, `Patient`, `Organization`, and `Provenance` mappings after backup/restore is stable.
- Keep the source artifact and extraction provenance even when a FHIR resource is generated.
- Use FHIR import/export as a portability feature before attempting live patient-portal connections.
- Test with Synthea, Mere Medical exports where compatible, and an isolated Medplum/HAPI test server.

## 4. Imaging, privacy, and local intelligence

| Project | License | Capability | Recommendation |
|---|---|---|---|
| [OHIF Viewer](https://github.com/OHIF/Viewers) | MIT | Extensible web DICOM viewer with DICOMweb support, 2D/3D rendering, annotations, segmentations, and reports. | **Best later DICOM viewer integration.** Keep it optional/lazy-loaded and do not imply the product is a diagnostic workstation. |
| [Cornerstone3D](https://github.com/cornerstonejs/cornerstone3D) | MIT | Browser imaging libraries used to build focused medical viewers, including OHIF. | **Evaluate if OHIF is too large** for the in-app study viewer. Keep decoding and file access behind a hardened boundary. |
| [3D Slicer](https://github.com/Slicer/Slicer) | BSD-style Slicer license | Advanced DICOM import/export, PET/CT visualization, volume rendering, segmentation, registration, and model export. | **Integrate as an external advanced workspace**, not by rebuilding it. Preserve provenance when handing off or importing SEG/STL/OBJ outputs. |
| [pydicom](https://github.com/pydicom/pydicom) | MIT for most code; bundled portions have additional notices | Python DICOM parsing and metadata handling. | **Useful in an isolated import worker** for detecting studies, removing display metadata from filenames, and synthetic tests. Keep originals immutable. |
| [dcmqi](https://github.com/QIICR/dcmqi) | BSD-3-Clause | Conversion between DICOM quantitative-imaging objects and research formats. | **Use later for SEG/RTSTRUCT interoperability** behind a tested worker interface. |
| [highdicom](https://github.com/ImagingDataCommons/highdicom) | MIT | High-level Python APIs for DICOM images, segmentation, structured reports, and related objects. | **Use for synthetic fixtures and conversion prototypes**; isolate it from vault keys and review transitive codecs. |
| [Presidio](https://github.com/data-privacy-stack/presidio) | MIT | PII detection, masking, redaction and anonymization across text/images/structured data. | **Prototype for redacted exports**, not for vault security. Healthcare identifiers and multilingual accuracy require custom evaluation and visual confirmation. |
| [OpenMed](https://github.com/maziyarpanahi/openmed) | Apache-2.0 | Local-first clinical NER and PII de-identification with multiple runtimes/models. | **Evaluate after OCR is stable** for local entity suggestions. Pin exact models and review each model/dataset license, accuracy, download source, and hardware requirement. |
| [health-assistant](https://github.com/health-assistant-io/health-assistant) | Apache-2.0; beta/very early | Privacy-first record aggregation, biomarker trends, OCR, AI assistant concepts. | **Idea/reference watchlist only** until it matures. Its “AI proposes but never writes” interaction is a useful pattern. |
| [Oncofiles](https://github.com/peter-fusek/oncofiles) | MIT; early | Google Drive medical-document organization, treatment timeline, lab tracking, source metadata and MCP tools. | **Product inspiration only.** Its oncology workflows and care timeline are worth studying, but sending data to configured cloud AI conflicts with this project's default zero-knowledge boundary. |

## 5. What to borrow from each project

### From Cryptomator

- Explicitly document both protected and leaked metadata.
- Encrypt/obfuscate names and structure, not only file bytes.
- Make recovery keys and vault format first-class product surfaces.
- Publish accepted risks rather than claiming perfect security.

### From restic/rustic/Kopia

- Immutable/content-addressed writes before manifest commits.
- Encryption and authentication for metadata as well as payloads.
- Interrupted operations that are safe to resume.
- Repository checks and restore tests as normal operations.
- Multiple key wrappers so password changes do not re-encrypt the archive.
- Independent recovery tooling and a documented on-disk format.

### From Mere Medical

- A unified timeline is more useful to a patient than a directory tree.
- Offline/local-first operation and no mandatory account reduce trust requirements.
- FHIR patient access can be added around a patient-controlled local record.
- Lab trends and source documents should coexist.

### From Fasten

- Profiles and caregiver/family use are core personal-record needs.
- FHIR Bundle upload is a practical first interoperability step.
- Avoid depending on a proprietary gateway for the app's core promise.

### From OHIF

- Do not write a medical image viewer from scratch.
- Isolate DICOM-specific workflows behind a standard DICOMweb/viewer boundary.

### From OCRmyPDF and Presidio

- Keep document transformation separate from the immutable source.
- Every OCR/redaction output records tool version and provenance.
- Human verification remains necessary.

## 6. Dependency adoption checklist

Before adding any project/package:

- [ ] Confirm exact package/repository and SPDX license.
- [ ] Check whether data/model assets have different terms.
- [ ] Check maintenance, release cadence, security policy, advisories, and unresolved critical issues.
- [ ] Decide library, subprocess, optional plugin, dev/test-only, or design-reference use.
- [ ] Pin version and integrity hash; commit lockfile.
- [ ] Record why it needs network, filesystem, child-process, or key access.
- [ ] Add it to SBOM and third-party notices.
- [ ] Add failure, timeout, malformed-input, and upgrade/migration tests.
- [ ] Verify it does not emit telemetry or download runtime assets without informed consent.
- [ ] Confirm no PHI appears in its default logs, caches, crash dumps, or temp paths.
- [ ] Re-run license/security review before release.

## 7. Useful official references

- [Google Drive: choose OAuth scopes](https://developers.google.com/workspace/drive/api/guides/api-specific-auth)
- [Google Drive: resumable uploads](https://developers.google.com/workspace/drive/api/guides/manage-uploads)
- [Google Drive: app-specific data folder](https://developers.google.com/workspace/drive/api/guides/appdata)
- [Cryptomator security target](https://docs.cryptomator.org/security/security-target/)
- [Cryptomator vault cryptography](https://docs.cryptomator.org/security/vault/)
- [restic repository design](https://github.com/restic/restic/blob/master/doc/design.rst)
- [Kopia architecture](https://kopia.io/docs/advanced/architecture/)
- [Kopia encryption](https://kopia.io/docs/advanced/encryption/)
- [HL7 FHIR R4 specification](https://hl7.org/fhir/R4/)
- [SMART App Launch](https://hl7.org/fhir/smart-app-launch/)
- [Open Health Stack Android FHIR SDK](https://developers.google.com/open-health-stack/android-fhir)
