# Medical Reports Backup — Product and Delivery Plan

> **Planning baseline:** 11 August 2026
>
> **Repository state at the start of planning:** concept only; there was no application code.

## 1. Product direction

### One-sentence pitch

**A local-first, zero-knowledge medical document vault that turns scattered reports into a searchable health timeline and continuously backs the encrypted vault up to storage the user already owns.**

The strongest version of this project is not “another Google Drive uploader.” It is a **recovery-first personal medical archive**:

- useful every day for finding and understanding records;
- private by design, with plaintext processed on the user's device;
- portable, with a documented recovery path that does not depend on this app surviving;
- trustworthy, because backup health and restore tests are visible rather than assumed.

### Primary users

1. **Individual:** wants all scans, reports, prescriptions, and lab PDFs in one safe place.
2. **Caregiver:** manages records for children, parents, or another dependent without mixing profiles.
3. **Chronic-care patient:** needs a longitudinal timeline and lab trends across many providers.

### Core jobs to be done

- “When I receive a report, help me save it once, classify it, and know it is protected.”
- “When a doctor asks about an old result, help me find the source document in seconds.”
- “When my laptop is lost, help me prove that I can recover the complete archive.”
- “When I share records, help me send only the relevant documents and understand the privacy impact.”

### Product principles

1. **Recovery over storage:** a backup is not successful until it has been verified and restored.
2. **Local plaintext only:** cloud storage receives ciphertext and non-sensitive transport metadata only.
3. **Source before summary:** every extracted value or generated summary links to its page and original report.
4. **Human confirmation:** OCR, classification, and clinical extraction may propose; they never silently overwrite source facts.
5. **Least privilege:** request only the narrowest cloud and operating-system permissions.
6. **Portable by construction:** version the vault format, publish it, and offer an independent recovery procedure.
7. **No medical-advice claims:** organize and present user-owned information; do not diagnose or recommend treatment.

## 2. Scope

### MVP promise

A user can create a password-protected vault, save PDF/image reports, organize and search them locally, back ciphertext up to a folder in their Google Drive, and restore the complete vault on a clean device using either the password or an offline recovery key.

### MVP features

- Desktop app for Windows and macOS first; Linux is supported as a beta target.
- One local vault and one patient profile.
- Import PDF, PNG, JPEG, and TIFF by picker or drag-and-drop.
- Password unlock, auto-lock, and offline recovery key.
- Original file encryption before persistent app storage or network transfer.
- App-created Google Drive folder using the narrow `drive.file` OAuth scope.
- Resumable background uploads, retries, pause/resume, and clear progress.
- Immutable document versions and duplicate detection.
- Manual date, provider, report type, profile, and tags.
- On-device OCR for scanned PDFs/images.
- Full-text and metadata search.
- Timeline and document list views.
- Encrypted manifests sufficient to rebuild the local index.
- Backup-health screen and a guided test restore.
- Export selected original documents after an explicit plaintext warning.

### Explicit MVP non-goals

- No hosted multi-tenant server.
- No clinician/practice-management workflow, billing, e-prescribing, or diagnosis.
- No automatic advice from lab values.
- No cloud LLM processing.
- No direct patient-portal/EHR synchronization.
- No real-time multi-device editing.
- No sharing links or collaboration.
- No DICOM PACS server.
- No promise of HIPAA, GDPR, FDA, CE, or other certification merely because encryption is present.

These are deliberate boundaries, not missing ambition. They keep the first release focused on the hardest promise: **safe, understandable recovery**.

## 3. Ideas that can make the product stand out

### Build now — high value and defining

| Idea | User value | Effort | Why it matters |
|---|---:|---:|---|
| **Restore Confidence** | Very high | Medium | Show last verified backup, object count, bytes, integrity result, and last clean-device restore. This is more honest than a generic green cloud icon. |
| **Smart Inbox** | High | Medium | Suggest report date, provider, profile, and type from local OCR; require confirmation before filing. |
| **Source-linked timeline** | High | Medium | Every timeline card opens the exact report and page that supports it. |
| **Immutable originals** | High | Low | Edits change metadata or create a new version; the imported source is never rewritten. |
| **Recovery rehearsal** | Very high | Medium | A wizard downloads a sample from Drive, decrypts it, verifies hashes, and records a local success receipt. |
| **Privacy-safe search** | High | Medium | OCR and index stay inside the encrypted local database; Drive cannot index medical text. |
| **Duplicate/version detection** | Medium | Low | Detect byte-identical files and likely revised copies before wasting storage or confusing the timeline. |

### Build next — turns a vault into a health record

| Idea | Value | Guardrail |
|---|---|---|
| **Family spaces** | Keep records for dependents separate while allowing a caregiver view. | Separate keys/permissions should be designed before sharing is added. |
| **Lab trend extraction** | Plot repeated biomarkers with units and reference ranges. | User confirms every extracted result; preserve original units and lab-specific ranges. |
| **Care bundle builder** | Select a condition/date range and produce a visit packet with index and originals. | Plaintext export expires locally and requires a privacy warning. |
| **FHIR R4 import/export** | Port structured data to and from compatible health apps. | Validate resources and retain provenance; avoid pretending all source PDFs can be losslessly converted. |
| **Redacted export** | Detect likely identifiers and help make a shareable copy. | Redaction must be burned into the export and verified visually; hiding PDF layers is insufficient. |
| **Emergency card** | Generate a compact, user-approved allergies/medications/contact packet. | It must show generation date and “verify before use”; never infer missing facts. |
| **Multilingual OCR** | Support records from different countries and scripts. | Language is selected/confirmed locally; test accuracy per language. |
| **DICOM handoff/viewer** | Keep imaging studies with reports and open them in a proper viewer. | Treat diagnostic viewing and storage as an optional, separately hardened module. |

### Explore later — exciting but easy to get wrong

| Idea | Product opportunity | Minimum safety bar |
|---|---|---|
| **Grounded local assistant** | “Which report mentioned X?” or “Summarize changes,” with page citations. | On-device by default, answer only from selected records, cite every claim, clear uncertainty, no diagnosis, evaluation with synthetic data. |
| **Time-boxed caregiver sharing** | Encrypt a care bundle to a recipient key and revoke future access. | Explain that already-downloaded plaintext cannot be revoked; never call a link “revoked” without that caveat. |
| **Patient portal sync** | Pull FHIR records from Epic/Cerner/other SMART-on-FHIR endpoints. | Separate OAuth threat model, provider registration, token security, and conflict/provenance model. |
| **Storage adapters** | OneDrive, S3, WebDAV, local NAS, and external disk. | A storage abstraction and conformance suite must exist before adding adapters. |
| **Record-gap detector** | Notice missing report attachments or unexplained date gaps. | Present as archive completeness, not clinical judgment. |
| **Trusted research links** | Link terms to MedlinePlus/PubMed/ClinicalTrials.gov. | Distinguish source record, educational material, and generated text. |

### Ideas to avoid

- Blockchain/IPFS for ordinary personal records: it complicates deletion, key recovery, metadata privacy, and user support without solving the core backup problem.
- Home-grown cryptographic algorithms or an undocumented file format.
- Uploading plaintext to Drive and relying only on Drive's server-side encryption.
- A cloud AI feature enabled by default.
- “HIPAA compliant” or “military-grade encryption” marketing without an audited system, operating procedures, and a defined legal context.
- Auto-deleting local data immediately after upload; this turns a transient cloud or account failure into data loss.

## 4. Recommended experience

### First-run flow

1. Explain in plain language what is protected and what is not.
2. Create vault and password.
3. Generate a separate offline recovery key; ask the user to save/print it and confirm selected words/characters.
4. Create the first profile.
5. Connect Google Drive with the app-limited scope.
6. Import a sample or first real document.
7. Show three separate states: **saved locally**, **encrypted**, **backed up and verified**.

Do not block local use when Google Drive is unavailable.

### Import flow

1. Validate format, size, and file signature; reject misleading extensions.
2. Copy into a guarded staging area with restrictive permissions.
3. Calculate a content hash locally and check duplicates.
4. Encrypt the immutable original into the local object store.
5. Render/OCR locally in a sandboxed worker.
6. Suggest metadata and ask the user to confirm uncertain fields.
7. Commit source metadata and OCR text to the encrypted index.
8. Queue ciphertext object and encrypted manifest for Drive.
9. Securely remove best-effort staging files and record completion without logging PHI.

### Recovery flow

1. Install app and select **Restore existing vault**.
2. Connect the Google account and select the app-created vault folder.
3. Unlock with password, or scan/import the offline recovery key.
4. Download and authenticate the encrypted head manifest.
5. Show archive summary before downloading all objects.
6. Restore and verify every object; make failures visible and retryable.
7. Rebuild the local encrypted search index from manifest metadata and OCR sidecars.
8. Offer a full integrity check and record its result locally.

### Daily dashboard

- Backup status: pending / uploading / verified / attention needed.
- Last successful backup and last recovery rehearsal.
- Recently imported reports.
- Documents needing metadata confirmation.
- Storage used locally and remotely.
- Search as the primary action.

## 5. Recommended technical architecture

### Application shape

```text
┌──────────────────────────────────────────────────────────────┐
│ Tauri desktop application                                   │
│                                                              │
│  React + TypeScript UI                                       │
│  ├─ Inbox, timeline, search, viewer, backup health           │
│  └─ No direct filesystem, key, or Drive token access         │
│                         │ typed Tauri commands                │
│  Rust core                                                   │
│  ├─ Vault/key service       ├─ Import/OCR worker coordinator │
│  ├─ Encrypted object store  ├─ Manifest/recovery service     │
│  ├─ SQLCipher index         ├─ Google Drive adapter          │
│  └─ Audit-safe event log    └─ Job queue                     │
└──────────────────────────────────────────────────────────────┘
                  │ ciphertext only
                  ▼
        User-owned Google Drive folder
```

### Suggested stack

- **Desktop:** Tauri 2, Rust, React, TypeScript.
- **UI state/data:** a small query/cache layer; avoid putting report text in global browser state or persistent web storage.
- **Local metadata/search:** SQLite with SQLCipher and FTS, unlocked with a random database key from the vault keyring.
- **File encryption:** the interoperable `age` format through the Rust `age`/`rage` implementation; do not implement cryptographic primitives in this project.
- **PDF:** PDF.js for viewing; OCRmyPDF/Tesseract as a sandboxed local worker where packaging permits.
- **Cloud:** direct Google Drive API adapter with resumable uploads.
- **Credentials:** operating-system keychain for OAuth refresh tokens; never store them in the vault database or logs.
- **Testing records:** Synthea and hand-built synthetic documents only. No real patient files in fixtures, CI, screenshots, or issue reports.

### Vault key model

Use envelope encryption so a password change does not require re-encrypting every report:

1. Generate a random **vault data identity** and random SQLCipher key.
2. Encrypt every immutable object to the vault data recipient using `age`.
3. Store a key bundle containing the vault identity and database key in two encrypted forms:
   - passphrase-protected key bundle for normal unlock;
   - recovery-recipient-protected key bundle for the offline recovery key.
4. Upload only encrypted key bundles.
5. Keep the recovery private key offline and display/export it once with explicit warnings.

A security review must validate this design and the exact library APIs before implementation is frozen. The application should also ship a documented command-line recovery recipe using independent `age` tooling where practical.

### Remote layout

Names are random and contain no patient, provider, report type, or date:

```text
<user-selected neutral folder>/
├── vault.json                 # format version, vault ID, no health data
├── keys/
│   ├── password.age           # wrapped key bundle
│   └── recovery.age           # wrapped key bundle
├── objects/
│   ├── 6f/<random-id>.age     # immutable encrypted originals/sidecars
│   └── ...
├── manifests/
│   └── <random-id>.age        # encrypted portable metadata snapshot
└── head.age                   # encrypted pointer to current manifest
```

Cloud-visible metadata still includes approximate object sizes, counts, and upload times. State this limitation clearly. A neutral folder name should be offered so the folder name itself need not reveal that the user has a medical archive.

### Drive integration rules

- Request `https://www.googleapis.com/auth/drive.file`, not broad access to all Drive files.
- Create and access only files created by or explicitly opened with the app.
- Send ciphertext as `application/octet-stream` and never mark it as indexable text.
- Use resumable uploads, persisted job state, exponential backoff with jitter, and idempotency.
- Keep ciphertext locally until the server object and its hash/size have been verified.
- Do not depend on Drive revision retention as the only history. Manifests and immutable objects define archive history.
- Abstract the provider behind a conformance-tested `VaultStorage` interface.

### Data model

Minimum entities:

- `Vault`: format version, ID, created time, devices.
- `Profile`: user-entered display identity, never included in remote filenames.
- `Document`: stable ID, profile, type, event date, provider, title, tags, status.
- `DocumentVersion`: immutable object ID, content hash, MIME, bytes, page count, import provenance.
- `TextArtifact`: OCR version, language, page spans, confidence, source version.
- `Extraction`: proposed field/value/unit/range, page evidence, model/rule version, confirmation state.
- `Manifest`: schema version, parent, referenced objects, created by device, integrity metadata.
- `SyncJob`: operation, state, attempts, resumable session, local/remote IDs, last non-sensitive error.
- `IntegrityCheck`: scope, timestamp, counts, bytes, result, app version.

Store dates with precision (`year`, `month`, `day`, `instant`) instead of inventing a day when a report only supplies a month or year.

### Write and sync semantics

1. Finish local encryption before committing a document as imported.
2. Treat encrypted objects as immutable.
3. Upload missing objects.
4. Upload a new encrypted manifest referencing only confirmed remote objects.
5. Atomically update the encrypted head pointer as the final step.
6. If interrupted, resume idempotently; an unreferenced remote object is safe to garbage-collect later.
7. MVP is **single-writer**. A second device restores a read-only copy unless the user explicitly transfers writer ownership. Design multi-device merge only after the manifest format has device IDs and conflict tests.

## 6. Security and privacy gates

A more detailed threat model is in [SECURITY_ARCHITECTURE.md](SECURITY_ARCHITECTURE.md).

### Must pass before private beta

- Key and vault design reviewed by an experienced application-security/cryptography engineer.
- No plaintext report, OCR text, filename, provider, or patient name reaches Drive.
- App locks and cryptographic keys are zeroized/released on timeout and suspend as far as platform APIs permit.
- Viewer and OCR temporary files have restrictive permissions and deterministic cleanup tests.
- OAuth tokens are in OS secure storage and redacted from diagnostics.
- Tauri command allowlist, CSP, navigation restrictions, and updater signing are configured.
- File parser/OCR processes are sandboxed or isolated with resource/time limits.
- Dependency audit, secret scan, SBOM, signed builds, and reproducible release notes are in CI.
- Fuzz/property tests cover manifest parsing, damaged ciphertext, wrong keys, truncated files, duplicate chunks, and interrupted uploads.
- Recovery works when the local database and app settings are completely absent.
- Logs and crash reports contain no document content or identifying metadata.

### Must pass before public release

- Independent penetration test or public security review.
- Published threat model, vault format, recovery guide, disclosure policy, and supported-version policy.
- Migration test from every released vault format.
- Tested uninstall/data-retention behavior on each OS.
- Accessibility audit and keyboard-only use for critical flows.
- Plain-language privacy policy that matches actual network behavior.

## 7. Delivery roadmap

Time estimates assume one experienced full-time engineer with part-time design and security review. A solo part-time effort should use the same gates and expect a longer calendar.

### Phase 0 — validate the promise (1–2 weeks)

**Outputs**

- Five interviews or workflow observations with individuals/caregivers.
- Confirm top formats, typical archive size, and what “restore” means to users.
- Architecture decision records for app shell, vault format, Drive scope, and recovery model.
- Three technical spikes:
  1. encrypt/decrypt a 2 GB synthetic file with bounded memory;
  2. resumable ciphertext upload, interruption, and resume with `drive.file`;
  3. clean-device recovery using only Drive plus password/recovery key.
- Synthetic test corpus and data-handling policy.

**Exit gate:** the vertical recovery spike works and the design review finds no blocker.

### Phase 1 — secure local vault (2 weeks)

- Tauri shell, locked/unlocked state, auto-lock, and OS keychain integration.
- Key creation, password wrapper, recovery-key ceremony.
- Encrypted immutable object store and SQLCipher migrations.
- Import validation for PDF/images.
- Basic list and metadata editor.

**Exit gate:** restart/unlock, wrong-password, corrupt-keyring, and recovery-key tests pass on all target OSes.

### Phase 2 — Drive backup and restore (3 weeks)

- Google OAuth, app-created folder, direct storage adapter.
- Persistent queue and resumable upload.
- Encrypted manifest/head protocol.
- Fresh-install restore and index rebuild.
- Backup status, verification, and recovery rehearsal.
- Offline behavior and quota/auth-revocation handling.

**Exit gate:** a fault-injection test interrupts every stage and produces either a complete verified archive or an explainable retry state—never a false success.

### Phase 3 — useful organization (3 weeks)

- Local PDF/image viewer.
- OCR worker and encrypted FTS index.
- Smart Inbox metadata suggestions with confidence and confirmation.
- Timeline, filters, tags, duplicate/version handling.
- Selected-document export with plaintext warning.

**Exit gate:** a user can import and locate a chosen record from a 500-document synthetic archive in under 30 seconds.

### Phase 4 — hardening and private beta (3 weeks)

- Security checklist, fuzzing, parser isolation, SBOM, signed updater.
- Accessibility and usability pass.
- Diagnostics bundle with strict redaction.
- Vault format/recovery documentation.
- 10–20 private beta users using synthetic or their own local data under clear beta warnings.

**Exit gate:** no unresolved critical/high security issue; all beta users can complete a guided test restore.

### Phase 5 — public beta (2–3 weeks)

- Packaging, onboarding, support and disclosure channels.
- Opt-in, privacy-preserving operational metrics limited to non-health events.
- Data export/deletion flows.
- Public roadmap and contribution guide.

**Exit gate:** release checklist and rollback plan are rehearsed.

### After MVP

Recommended order:

1. Family profiles.
2. FHIR Bundle import/export.
3. Confirmed lab extraction and trends.
4. Redacted/care-bundle exports.
5. Additional storage adapters.
6. DICOM viewer integration.
7. Patient-portal sync.
8. Carefully evaluated, local, source-citing assistant.

## 8. First 30 days of engineering

### Week 1

- Record product assumptions and interview script.
- Create ADRs for Tauri, age-based object vault, SQLCipher, and Drive scope.
- Define threat model and synthetic-only fixture policy.
- Scaffold app and CI; add format/lint/test, secret scanning, dependency audit, and license inventory.

### Week 2

- Implement keyring proof of concept and offline recovery-key flow.
- Stream a large synthetic object into local encrypted storage with bounded memory.
- Prototype locked database and verify that filenames/OCR text do not appear in plaintext on disk.

### Week 3

- Complete Drive OAuth proof with `drive.file`.
- Upload ciphertext using the resumable protocol; persist and resume an interrupted session.
- Implement storage adapter contract tests against an in-memory fake and Drive sandbox account.

### Week 4

- Write/read encrypted manifests.
- Delete all local state and restore the synthetic vault from Drive.
- Run design review; decide whether the age object layout is sufficient or whether to adopt an established restic-compatible repository via `rustic_core` before product code grows around the format.
- Demo one vertical path: import → encrypt → upload → delete local state → restore → verify.

## 9. Backlog by epic

### Vault and identity

- Create, unlock, lock, auto-lock, password change.
- Recovery key create/confirm/export/import.
- Key zeroization and suspended-app behavior.
- Versioned keyring migration.

### Import and archive

- MIME/signature validation and size limits.
- Immutable original and version model.
- Duplicate detection and guarded staging cleanup.
- Metadata editing and profile assignment.

### Backup engine

- Provider interface and fake provider.
- Drive OAuth and secure token handling.
- Job queue, resume, retry, cancellation, quota state.
- Manifests, head updates, garbage collection, integrity checks.

### Discovery

- PDF/image viewer.
- OCR languages and page-level text.
- FTS, filters, tags, and timeline.
- Source-page deep links.

### Trust

- Backup-health dashboard and restore rehearsal.
- Recovery CLI/guide and vault specification.
- Audit-safe diagnostics and support bundle.
- Security policy, signed releases, SBOM, and migration tests.

## 10. Definition of done

A feature touching medical files is not done until:

- security and privacy abuse cases are documented;
- no PHI is added to logs, analytics, crash reports, filenames, screenshots, or test fixtures;
- locked, offline, low-disk, revoked-auth, interrupted-operation, and corrupt-input paths are tested;
- accessibility labels and keyboard flow exist;
- migration/recovery impact is tested;
- user-facing failure states say what is safe, what is pending, and what action is needed;
- docs and the vault-format changelog are updated.

## 11. Success measures

Prefer local, user-visible measures over surveillance analytics:

- **Restore readiness:** percentage of vault objects verified and date of last rehearsal.
- **Backup lag:** time from local import to verified remote manifest.
- **Recovery success:** clean-device synthetic restore pass rate in release CI.
- **Findability:** median time in usability tests to locate a named report.
- **Inbox quality:** percentage of suggested fields accepted, corrected, or left unknown.
- **Reliability:** jobs ending in false-success state must remain zero.
- **Security:** time to remediate critical/high issues and percentage of releases with signed SBOM.

If aggregate product analytics are ever added, make them opt-in, collect no document/profile/provider names or report-derived values, and document the exact event schema.

## 12. Product decisions still needed

These choices do not block the first technical spikes, but they should be answered before MVP UX is frozen:

1. Initial audience: individual only, or caregiver/family from day one?
2. Launch platforms: Windows + macOS, or one platform first?
3. Is a local encrypted copy always retained, or can advanced users choose cloud-only after a warning?
4. Should the Drive folder have a neutral default name?
5. Which OCR languages are required for the first release?
6. Is Google Drive the permanent primary provider or merely the first adapter?
7. What is the project's distribution model: fully open-source desktop app, paid signed builds/support, or both?

The recommended defaults are: individual-first data model with profile support, Windows/macOS first, always retain local encrypted objects, neutral folder-name option, English plus one user-selected OCR language, provider abstraction from day one, and an open core with no hosted plaintext service.
