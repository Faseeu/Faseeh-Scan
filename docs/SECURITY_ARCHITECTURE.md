# Security Architecture and Threat Model

> **Status:** proposed design for review, not a claim that an implementation has been audited.
>
> **Baseline:** 11 August 2026.

## 1. Security objective

A person who obtains the Google Drive folder, a copied remote vault, or a locked local application-data directory must not be able to read report contents, medical metadata, OCR text, original filenames, patient names, or provider names without the user's password or offline recovery key.

The system must also detect accidental corruption and malicious modification before presenting recovered plaintext as authentic archive content.

## 2. Data classification

### Highly sensitive

- Original reports, scans, images, and DICOM files.
- OCR text, thumbnails, page images, and extracted values.
- Patient/profile details, provider names, dates, diagnoses, medications, and tags.
- Original filenames and user notes.
- Vault data identity, database key, recovery private key.
- OAuth refresh tokens.

### Sensitive operational metadata

- Vault ID, device ID, object content hashes, sync history, local paths.
- Counts, sizes, timestamps, and error context that could reveal user behavior.

### Intentionally non-secret

Keep this set minimal:

- Vault container magic/version.
- Cryptographic suite identifier required for recovery.
- Random object IDs.
- Approximate ciphertext object size and cloud-created/modified times, which the storage provider necessarily sees.

No patient, provider, report type, event date, or original filename belongs in remote object names or Drive custom properties.

## 3. Trust boundaries

```text
Untrusted files ──► parser/OCR sandbox ──► Rust vault core
                                              │
React WebView ◄── narrow typed commands ──────┤
                                              │
OS keychain ◄──── token service               ├──► SQLCipher index
                                              │
Google Drive ◄──── ciphertext-only adapter ───┘
```

- **React WebView:** potentially exposed to UI injection; it does not receive raw vault keys, refresh tokens, unrestricted file paths, or arbitrary shell access.
- **Rust core:** trusted to enforce vault state and all sensitive I/O.
- **Parser/OCR workers:** assume malformed input is hostile; isolate from network and secrets.
- **Operating system:** trusted while the user session is uncompromised. The app cannot protect an unlocked machine controlled by malware or an attacker.
- **Google Drive/network:** untrusted for confidentiality and integrity; receives ciphertext.
- **Build/update infrastructure:** security-critical; compromise could ship a key-stealing client.

## 4. Threat actors and scenarios

### In scope

- Curious or compromised cloud-storage operator.
- Attacker who steals the Google account or obtains the Drive folder.
- Network attacker despite TLS.
- Attacker who copies the locked app-data directory from a lost device.
- Malicious report crafted to exploit PDF/image/OCR parsers.
- Corruption, truncation, replay, object replacement, or deletion in remote storage.
- OAuth token leakage through logs or insecure local storage.
- Dependency or update supply-chain attack.
- Accidental plaintext leakage through temp files, caches, logs, crash dumps, exports, or thumbnails.
- User mistakes: duplicate imports, password loss, wrong profile, interrupted upload, quota exhaustion, revoked Drive access.

### Out of scope for the first release, but disclosed

- Malware, a debugger, or an administrator controlling the device while the vault is unlocked.
- Hardware/firmware compromise, keylogger, malicious keyboard, or screen capture.
- An authorized recipient copying a plaintext export.
- Traffic analysis of ciphertext counts, sizes, and upload times.
- Guaranteed secure deletion from SSDs, cloud replicas, swap, hibernation, backups, or journaled filesystems.
- Coercion or disclosure of the password/recovery key.
- Availability when Google disables the account and no local/second backup exists.

“Zero knowledge” applies to stored report plaintext and keys at the provider boundary; it does not mean the provider sees no metadata at all.

## 5. Proposed key hierarchy

```text
User password ── age passphrase wrapper ──┐
                                          ├─► key bundle
Offline recovery public key ── age ───────┘    ├─ vault data identity
                                               └─ random SQLCipher key

Vault data recipient ── age ──► originals, OCR sidecars, manifests, thumbnails
```

### Requirements

- Generate vault and recovery keys with the operating system CSPRNG.
- Use the `age` format and maintained library APIs; write no cipher, KDF, nonce, or authentication implementation in this repository.
- Encrypt the same key-bundle plaintext separately for password and recovery unlock.
- The recovery private key is never uploaded. Show/export it once and make its power explicit.
- A password change replaces only the password-wrapped key bundle.
- A recovery-key rotation writes a new recovery wrapper and may require a carefully designed transition; never silently invalidate the only recovery path.
- Keep decrypted key material in the Rust process for the shortest practical duration and use zeroizing/locked-memory facilities where available.
- Never send a password or vault key to the WebView.

### Password policy

- Encourage long passphrases; allow password-manager paste.
- Do not impose composition theater such as mandatory symbols.
- Meter failed local attempts to reduce accidental rapid guessing, while acknowledging an attacker with the encrypted keyring can perform offline guessing.
- Display a strength estimate and explain that the offline recovery key is the only supported forgotten-password path.
- Never implement password recovery through a server backdoor.

## 6. Object and manifest integrity

- Each encrypted `age` object provides content authentication.
- Inside the encrypted manifest, record object ID, expected plaintext hash, ciphertext bytes, plaintext bytes, media type, and role.
- Manifests are immutable and include schema version, vault ID, parent manifest ID, device ID, and monotonically increasing local sequence.
- The encrypted head identifies the selected current manifest.
- On restore, authenticate/decrypt first, then compare manifest IDs, vault ID, and hashes before accepting content.
- Reject unknown future schema/algorithm versions safely; never attempt “best effort” decryption that skips authentication.
- Do not treat a Drive MD5 value as the cryptographic authenticity check. It may help transport diagnostics only.
- Keep previous manifests so head corruption or rollback can be diagnosed.

A cloud attacker can delete all copies and can replay a previously valid archive state. Detecting rollback across the loss of every trusted local state requires an external checkpoint or transparency service; the first release should disclose this limitation rather than overclaim. A locally stored last-seen manifest receipt can detect rollback on an existing device.

## 7. Local storage

- Store immutable originals and generated artifacts encrypted at rest as `age` objects.
- Store searchable metadata/OCR text in SQLCipher with a random key from the encrypted key bundle.
- Disable plaintext SQLite journals; verify WAL/temp configuration under SQLCipher on every platform.
- Do not use browser `localStorage`, IndexedDB, service-worker caches, or persisted Redux/query caches for PHI.
- Use random internal paths and restrictive file permissions.
- Back up a portable encrypted manifest, not only the raw database, so recovery does not depend on one SQLCipher build or schema.
- Lock on explicit action, timeout, OS session lock, and suspend where reliable. Clear UI and query caches on lock.

## 8. Temporary plaintext and viewers

Prefer streaming decrypted bytes through a restricted application protocol to the viewer rather than writing complete plaintext files.

If a third-party tool requires a file:

1. ask for explicit user action;
2. create it under an app-owned directory with owner-only permissions;
3. use an unpredictable name without medical metadata;
4. exclude it from indexing/backup where platform APIs allow;
5. remove it on close, lock, startup cleanup, and crash recovery;
6. explain that secure erasure on SSD/cloud-backed temp locations cannot be guaranteed.

Thumbnails and OCR intermediate images are medical data and follow the same rules as originals.

PDF JavaScript, embedded file launching, remote URL fetching, and form submission should be disabled in the in-app viewer unless a reviewed use case requires them.

## 9. Import and parser isolation

- Check file signatures and parse with bounded size/page/pixel limits.
- Disable optical-media autorun and never execute bundled DICOM viewers, scripts, or DICOM files from imported media.
- Treat archives and DICOM directories as decompression-bomb risks; validate or clear unknown DICOM preambles only in a derived working copy while preserving the encrypted original.
- Run OCR/PDF/image/DICOM processors out-of-process with no Drive token, vault key, home-directory access, or network access.
- Apply CPU, memory, file-count, and wall-time limits.
- Pin and promptly update Ghostscript, Tesseract, image codecs, and PDF components.
- Preserve the original bytes even when an OCR/PDF-A derivative is generated.
- Record tool/version and source-object provenance for every artifact.

## 10. Google Drive and OAuth

- Use the non-sensitive `drive.file` scope and an app-created or explicitly selected folder.
- Use OAuth authorization-code flow with PKCE and a loopback/custom URI appropriate to installed apps.
- Validate state, issuer, audience, redirect URI, and PKCE verifier.
- Store refresh tokens only in OS secure storage; keep access tokens in memory.
- Redact authorization headers, tokens, resumable-session URLs, Drive IDs, and response bodies from logs.
- A resumable-session URL is a bearer capability and must be protected like a credential.
- Use TLS with normal certificate validation; no bypass in production.
- Set uploads to `application/octet-stream`; do not request Drive content indexing.
- Correctly handle revoked access, account switch, folder deletion, quota exhaustion, 429/5xx responses, and expired upload sessions.
- Never show **Backed up** until object upload, manifest commit, and verification have all completed.

## 11. Application and WebView hardening

- Keep the Tauri capability/command allowlist minimal and deny arbitrary shell invocation.
- Validate every command payload in Rust; the UI is not a trust boundary.
- Use a strict Content Security Policy with no remote scripts and no `unsafe-eval`.
- Block navigation and new-window requests outside an explicit allowlist; open educational links through the OS after confirmation.
- Bundle fonts/assets or assess every remote request; the locked app should make no analytics/marketing calls.
- Sanitize OCR text and report metadata before rendering. Never inject it as HTML.
- Do not expose raw local paths or file URLs to the WebView.
- Sign application packages and updates; require authenticated update metadata.
- Provide a network activity document listing every production endpoint and purpose.

## 12. Logging, diagnostics, and support

Never log:

- filenames, titles, OCR text, extracted fields, profile/provider names;
- passwords, recovery keys, vault/database keys;
- OAuth tokens, authorization headers, session URLs;
- unredacted Drive IDs or local paths.

Use random correlation/job IDs, enum error codes, byte-count buckets, and durations. A diagnostics export must preview exactly what it contains and be safe to attach publicly. Crash reporting is off by default until a redacted, opt-in design is reviewed.

GitHub issue templates must warn users not to upload real reports, screenshots, tokens, or app data.

## 13. Sharing and export

Plaintext export is a deliberate crossing of the vault boundary:

- show recipient/purpose checklist and destination;
- default to a newly created directory, not a cloud-synced location;
- identify every selected document/profile;
- warn that the app cannot revoke a copied file;
- offer an encrypted archive or recipient-key export;
- expire and clean app-managed temporary bundles;
- do not claim a PDF is redacted until the output is rasterized/rebuilt as appropriate and visually verified.

Sharing features are post-MVP because recipient identity, expiration semantics, and revocation language require separate design.

## 14. Build and supply chain

- Lock dependencies and review lockfile changes.
- Run `cargo audit`, Rust/JavaScript license checks, secret scanning, and dependency review in CI.
- Generate CycloneDX or SPDX SBOM for releases.
- Use least-privilege, short-lived CI credentials and protected release environments.
- Pin CI actions by immutable commit.
- Build release artifacts from tagged source and sign them.
- Publish checksums, provenance/attestations, and a dependency notice file.
- Maintain a security disclosure policy and supported-release table.
- Review model and OCR language-data licenses separately from code licenses.

## 15. Verification strategy

### Unit/property tests

- Wrong password/recovery key.
- Truncated, reordered, duplicated, and bit-flipped ciphertext.
- Unknown vault/manifest versions.
- Path traversal and malicious filenames.
- Date precision and profile isolation.
- Manifest parent loops, object substitution, and hash mismatch.
- Token/error redaction.

### Fuzzing

- Manifest and key-bundle parsers.
- Import metadata boundaries.
- Tauri command payloads.
- Recovery with corrupt/missing remote objects.

Use upstream fuzzing coverage for PDF/image parsers in addition to local process isolation; do not expose complex parser code directly to secrets.

### Integration/fault tests

Inject failure before and after every local commit, object upload, manifest upload, and head update. Test:

- process kill and reboot;
- network drop and resumed upload;
- expired session URI;
- quota full, 401/403, 404 folder, 429, and 5xx;
- Drive object modification/deletion/replay;
- low disk during import and restore;
- clean-device restore with no database/config;
- password change followed by old/new password and recovery-key attempts.

### Release security tests

- Scan installed app-data and Drive fixtures for known plaintext canaries.
- Monitor network calls while importing, viewing, locking, and restoring.
- Verify locked-memory/key cleanup behavior with platform tools where possible.
- Restore a previous release's vault with the new release.
- Restore the current release's test vault with the documented independent tooling.

## 16. Security release gates

### Private beta

- Threat model reviewed.
- Cryptographic/key design reviewed externally.
- No known critical/high issue.
- Clean restore and corruption tests green on every target OS.
- Signed builds, SBOM, disclosure policy, and recovery guide available.

### Public stable

- Independent penetration test or equivalent public review completed and findings triaged.
- Published vault specification and migration policy.
- Update and release signing rehearsed.
- Privacy policy verified against captured network behavior.
- Incident-response owner and compromised-release procedure defined.

## 17. Compliance posture

This project handles highly sensitive health information, but software features alone do not create compliance. Obligations depend on who operates the software, for whom, where, and under what contracts.

- A personal local app is not automatically a HIPAA covered entity or business associate.
- A hosted service for providers may create very different HIPAA/GDPR/regional obligations.
- Encryption does not replace consent, access control, retention/deletion rules, audit procedures, breach response, vendor agreements, or clinical-device review.
- Structured extraction and AI can introduce patient-safety risk even when they are not marketed as diagnosis.

Obtain qualified legal/security advice before making compliance claims or offering a hosted/clinical version.
