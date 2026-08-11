# Medical Reports Backup

> **Status: planning / pre-implementation.** There is no usable application in this repository yet.

Medical Reports Backup is being designed as a **local-first, zero-knowledge medical document vault**. It will organize PDFs and scans into a searchable timeline, encrypt originals and metadata on the user's device, back ciphertext up to storage the user owns, and make recovery easy to verify.

## Product promise

- **Private:** report plaintext, filenames, OCR text, and medical metadata stay on the device.
- **Useful:** local OCR, search, tags, profiles, and a source-linked timeline make records easy to find.
- **Recoverable:** visible backup health, guided restore rehearsals, an offline recovery key, and a documented vault format.
- **Portable:** Google Drive is the first storage adapter, not a proprietary data silo.
- **Honest:** this is a personal archive, not a diagnostic tool or a compliance certification.

## Proposed MVP

1. Create a password-protected vault and offline recovery key.
2. Import PDF and image reports into encrypted local storage.
3. Organize reports and search on-device OCR text.
4. Upload only ciphertext to an app-created Google Drive folder.
5. Resume interrupted uploads and verify remote objects.
6. Restore the complete archive on a clean device with the password or recovery key.

The recommended implementation is a Tauri desktop app with a Rust security/storage core, React/TypeScript UI, SQLCipher local index, interoperable `age` encrypted objects, local OCR, and a least-privilege Google Drive adapter. The architecture remains subject to a Phase-0 security and recovery spike.

## Planning documents

- [Product and delivery plan](docs/PROJECT_PLAN.md)
- [Security architecture and threat model](docs/SECURITY_ARCHITECTURE.md)
- [Open-source projects to adopt, evaluate, or study](docs/OPEN_SOURCE_LANDSCAPE.md)

## Near-term milestone

The first engineering milestone is one end-to-end synthetic-data path:

```text
import → encrypt locally → upload ciphertext → remove local state → restore → verify
```

Implementation should not expand into AI, live EHR sync, sharing, or DICOM until that recovery path is reliable and reviewed.

## Security and medical disclaimer

This repository does not yet contain an audited implementation. Do not use it to store real medical records. Future software from this project will organize user-owned information; it must not be treated as medical advice, a diagnostic device, or proof of HIPAA/GDPR/FDA/CE compliance.

## License

[Apache License 2.0](LICENSE)
