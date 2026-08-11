# Medical Imaging, CDs, DICOM, and 3D Data

> **Planning and patient-education note:** this explains common imaging workflows; it is not medical or legal advice. Access rights, fees, formats, and retention periods vary by country and facility. For records in Pakistan, ask the imaging center's radiology records/PACS desk what it retains and how it releases patient copies.

## 1. Why PET/CT, CT, MRI, and other scans still arrive on CDs

Not every center uses CDs now—many offer a portal, QR code, secure download, USB, or direct hospital-to-hospital transfer—but CDs remain common because they are:

- **Portable across institutions:** the receiving hospital does not need an account in the sender's portal.
- **Based on a medical standard:** most discs contain DICOM files, the standard form used by scanners, viewers, and PACS archives.
- **Offline and write-once:** a CD-R is easy to hand to a patient and hard to change accidentally.
- **Cheap and operationally familiar:** imaging centers already have PACS “disc burner” workflows.
- **Large enough for many studies:** one scan may contain hundreds or thousands of high-bit-depth images plus metadata and cannot safely be reduced to a few JPEGs.
- **A fallback for weak interoperability or bandwidth:** different hospitals and vendors do not always have a trusted network exchange.

The DICOM standard explicitly defines media profiles for CD, DVD, USB/flash, and other media. A normal imaging disc commonly contains:

```text
DICOMDIR                 # index/table of contents
DICOM/...                # CT, PET, MR, report, or related DICOM instances
VIEWER/ or viewer.exe    # optional portable viewer
REPORT.pdf               # sometimes present; not guaranteed
README / autorun files   # optional
```

`DICOMDIR` organizes the hierarchy **patient → study → series → image/instance**. The individual DICOM instances usually contain both image pixels and embedded patient/acquisition metadata. The official DICOM media standard supports more than images: structured reports, presentation states, waveforms, segmentations, and other objects may be included.

### Why not just JPEG or PDF?

A screenshot or JPEG usually loses clinically useful properties such as:

- original bit depth and pixel values (for example, CT Hounsfield units);
- window/level flexibility;
- slice geometry and spacing;
- scanner and acquisition parameters;
- study/series relationships and frame-of-reference information;
- PET quantitative metadata needed for SUV display;
- lossless source quality and provenance.

A PDF report is important, but it is the radiologist's interpretation—not a replacement for the image study.

## 2. What happens if the CD is scratched, corrupted, or broken?

### If it is only lightly scratched or dirty

The drive's error correction may still read it. Try, in this order:

1. Do not keep opening the built-in viewer; first copy/image the media once.
2. Handle the disc only by the edge and center hole.
3. Remove dust with clean air or a soft lint-free cloth.
4. If cleaning is necessary, wipe **radially from the center outward**, not in circles.
5. Try a second good-quality optical drive; drives differ in their ability to read marginal media.
6. Create a read-only disc image or rescued file copy and work from that copy.
7. Hash and verify every recovered file; a folder that “looks copied” can still have unreadable instances.

Do not use aggressive polishing, solvents, heat, toothpaste, or repeated high-speed reads on irreplaceable media.

### If it is cracked, snapped, warped, or delaminating

Do **not** put a cracked disc into a drive. It can fail at high rotational speed and damage the drive. A physically broken data layer is generally not something normal software can reconstruct. A specialist may recover parts from some damaged media, but success is uncertain and can be expensive.

### If files copy but some images are missing

The disc may still partially work. A DICOM-aware validator should compare:

- records in `DICOMDIR` with files actually present;
- expected versus readable SOP Instance UIDs;
- slice positions and instance numbers for gaps;
- study/series/frame-of-reference relationships;
- transfer syntax and decompression success;
- final report and non-image objects.

Keep the partial recovery, its error log, and hashes. Do not silently present an incomplete series as complete.

### Can the imaging center make another copy?

Often yes, **if the study still exists in its PACS/archive**. Contact the radiology records, image library, PACS, or medical-records desk with:

- patient name/ID and proof of identity;
- scan modality and body area;
- scan date and facility;
- accession/visit number if available;
- request for the complete study in native DICOM plus the final signed report.

Retention periods differ, and old studies may be migrated, offline, or deleted under local policy. Request a replacement promptly rather than assuming the center will retain it forever.

### CDs are transfer media, not a safe lifetime archive

The Library of Congress warns that CDs/DVDs are poor sole long-term storage: scratches and smudges can cause read failures, recordable-disc dyes degrade, and drives/software become obsolete. The right response is migration, not a nicer disc case:

- preserve one encrypted copy on the local computer;
- preserve one encrypted copy on a second device or external disk;
- preserve one encrypted off-site/cloud copy;
- keep checksums and run periodic integrity checks;
- test a restore, not only an upload;
- retain the original disc as provenance, but do not depend on it.

## 3. Can we extract everything already on the CD—and ask for more?

Yes. The current disc can be preserved in either of two useful forms:

- **Complete file-tree copy:** copy every file and folder, including `DICOMDIR`, files without `.dcm` extensions, reports, and unreferenced objects. This is easiest to inspect and deduplicate.
- **Read-only ISO/disc image:** preserves the exact filesystem and non-DICOM extras for provenance or later recovery. It should be encrypted because it may contain PHI and old executable software.

For either method, record the total bytes, file count, per-file hashes, read errors, and the source-disc label. Verify the copy before trusting it, and never copy only the bundled viewer or only the files that happen to end in `.dcm`.

You can also ask the center for more than the disc contains. What it can or must provide depends on local rules and what it actually retained, but the request should be precise.

### Ask first for the useful clinical archive

Request:

- the **complete native DICOM study**, not screenshots or JPEGs;
- every available study, series, and instance from the examination;
- the `DICOMDIR` or a standard DICOM ZIP/download;
- the final signed radiology/nuclear-medicine report;
- original reconstructed axial images at full available matrix/bit depth;
- thin-slice reconstruction if it was created and retained;
- coronal/sagittal/MPR, MIP, and other derived series if retained;
- presentation states, key images, measurements, and structured reports if retained;
- dose report / Radiation Dose SR if retained;
- segmentations, RT Structure Sets, annotations, and registrations if created;
- any encapsulated STL/OBJ or other 3D model if one was created;
- a checksum or export manifest if the center can provide one.

Avoid asking only for “raw files,” because that term means different things to patients, radiologists, and scanner engineers.

### For PET/CT specifically

Ask whether the export includes:

- the PET emission series;
- attenuation-corrected PET and, if retained/needed, non-attenuation-corrected PET;
- the CT used for attenuation correction;
- any separate diagnostic-quality CT, with and without contrast as applicable;
- PET and CT registration/spatial-reference data;
- fused/derived display series if the workstation stored them;
- quantitative metadata required for SUV calculation/display;
- gated/dynamic/time-point series if the examination used them;
- the final nuclear-medicine report and dose information.

A fused PET/CT picture may simply be a viewer combining registered PET and CT volumes at display time. The two source series and their spatial relationship are often more valuable than exported fused screenshots.

### “Original DICOM” is not always scanner-detector raw data

There are three different layers:

1. **Original reconstructed DICOM images:** clinically viewable slices/frames reconstructed from the scanner measurements. These are normally what to request for care, comparison, volume rendering, and most 3D work.
2. **Derived images:** reformats, thick slices, screenshots, fused captures, MIPs, filtered series, and other processed outputs.
3. **Vendor-native acquisition data:** CT projection/sinogram data, PET list-mode/sinograms, or MRI k-space. These are the measurements before normal image reconstruction.

The third category is commonly huge, vendor-specific, short-lived, absent from PACS, and unusable without scanner-specific calibration/reconstruction software. A patient may ask whether it was retained and can be released, particularly for research, but should not expect it on an ordinary CD.

The best practical wording is: **“Please include the complete original reconstructed DICOM series at the finest slice thickness/full available resolution, plus all available derived series and non-image DICOM objects.”** Then ask for scanner-native raw acquisition data as a separate request if there is a real research need.

## 4. Can we ask for a 3D model?

Yes—but first distinguish a **3D volume** from a **3D model**.

### 3D volume

A CT, PET, or MRI series is usually a stack of spatially located 2D slices/frames. A viewer combines the voxels and can show:

- axial, coronal, and sagittal planes;
- multiplanar reconstruction;
- MIP/minIP;
- volume rendering;
- PET/CT fusion.

The center may never save a separate “3D file” because the workstation generates these views from DICOM on demand.

### Segmentation

A segmentation labels which voxels belong to a structure—bone, organ, lesion, vessel, implant, and so on. This is an additional analysis step and may be represented as:

- DICOM SEG (binary, fractional, or label-map segmentation);
- DICOM Surface Segmentation;
- RT Structure Set (`RTSTRUCT`), especially in radiotherapy;
- NIfTI/NRRD label map in research workflows.

### Surface model

A mesh such as STL or OBJ represents a selected surface, not all scanner information. Creating it requires segmentation and introduces operator/algorithm choices. DICOM supports encapsulated STL and OBJ models, but most routine scans do not automatically produce or store them.

Therefore:

- **If the center created a segmentation/model for surgical planning, radiotherapy, or 3D printing:** ask for that exact object in DICOM SEG/Surface/RTSTRUCT and STL/OBJ/3MF if available.
- **If no model exists:** ask for the best original reconstructed DICOM series. A specialist can segment it later with software such as 3D Slicer.
- **For clinical or surgical use:** have the segmentation/model validated by a qualified radiologist/engineer. A visually impressive self-generated STL is not automatically anatomically accurate or fit for treatment.

Thin, near-isotropic slices generally help 3D reconstruction. Thick or gapped slices, motion, metal artifacts, limited field of view, low-dose protocols, and lossy/derived exports can reduce model quality.

## 5. Suggested request text

A patient can adapt this without claiming a right the local law may not provide:

> Please provide a complete electronic copy of my **[PET/CT, CT, MRI, etc.]** examination performed on **[date]**, preferably by secure download/USB or replacement disc. Please export the complete study in native DICOM format, preserving all available studies, series, instances, UIDs, geometry, bit depth, and acquisition metadata—not JPEG screenshots only. Please include the final signed report, original reconstructed thin-slice series at the finest retained resolution, all available derived/reformatted series, presentation states/key images, structured and dose reports, registrations, measurements, and any DICOM SEG, RTSTRUCT, Surface Segmentation, STL, OBJ, or other 3D model that was created and retained. For PET/CT, please include the PET and CT source series, attenuation-corrected data and other retained correction/diagnostic series, quantitative SUV metadata, and fused/registered series if stored. Please tell me separately whether scanner-native raw acquisition data (such as CT projections, PET list-mode/sinograms, or MRI k-space) is retained and available.

If another doctor needs the study urgently, also ask the center to send it directly through its normal secure image-exchange/PACS channel.

## 6. Imaging features that could level up this project

### A. Disc Rescue Inbox

Treat optical media as endangered at import time:

- detect CD/DVD/USB/ZIP/portal exports;
- disable autorun and never execute bundled viewers;
- create a sector/file rescue copy with resumable reads;
- retry unreadable regions and preserve an error map;
- calculate hashes immediately;
- parse `DICOMDIR` and scan unreferenced DICOM files;
- quarantine executable content;
- preserve the exact source tree or optional ISO as encrypted evidence;
- show **complete**, **partial**, or **unreadable**, never just “imported.”

### B. DICOM Completeness Report

For every imported study, show:

- studies, series, instances, modalities, and total bytes;
- missing `DICOMDIR` references and orphan files;
- geometry/slice gaps and inconsistent frame-of-reference UIDs;
- original versus derived image classification;
- lossless versus lossy transfer syntax;
- image matrix, bit depth, slice thickness/spacing, and voxel size;
- presence of final report, dose SR, presentation states, SEG, RTSTRUCT, and models;
- whether PET quantitative fields required for SUV display appear present;
- a warning that technical completeness is not a medical interpretation.

This could generate a ready-to-send “missing data” request for the imaging center.

### C. 3D Readiness Score

Explain—not clinically judge—whether an image series is technically suited to later modeling:

- complete contiguous coverage;
- thin/near-isotropic voxels;
- original reconstructed rather than screenshot/secondary capture;
- full matrix/bit depth;
- no lossy compression flag;
- known spatial geometry;
- segmentation/model already present.

Always show the contributing facts. Do not reduce them to a mysterious AI score.

### D. PET/CT-aware archive

- Pair PET and CT series by study and frame of reference.
- Provide synchronized crosshairs and fused display through a proven viewer.
- Track tracer, uptake/reconstruction time, corrections, and quantitative metadata as source metadata—not user-entered diagnosis.
- Keep the nuclear-medicine report linked to the exact study.
- Compare study availability over time without automatically interpreting disease response.

### E. “Ask the Lab” generator

Given modality and use case—second opinion, surgery, 3D printing, radiotherapy, research—the app generates a precise records request and tracks:

- requested date;
- facility/PACS contact;
- series expected;
- response/replacement media;
- missing components;
- consent/authorization documents.

### F. Model and segmentation vault

Store the relationship:

```text
source DICOM series
    └── segmentation + author/tool/version
          └── surface model + export parameters
                └── print/manufacturing file
```

Never let an STL replace its source DICOM and segmentation. Preserve coordinate system, frame of reference, labels, algorithm/operator, version, and validation state.

### G. Safe viewer handoff

- Basic viewing in-app with OHIF/Cornerstone3D.
- “Open advanced workspace” handoff to 3D Slicer without plaintext persistence longer than necessary.
- Optional local Orthanc/DICOMweb bridge for large studies.
- No bundled disc viewer execution.
- Sandboxed parsing, no network access for imported files, and aggressive patching.

### H. Imaging integrity patrol

- Periodically authenticate/decrypt a rotating sample and hash-check all objects on schedule.
- Alert before the only local optical copy ages further.
- Show two-copy/three-copy coverage by study.
- Perform a real restore rehearsal of a large DICOM study.
- Record which application/version successfully opened each transfer syntax.

### I. Privacy lens

DICOM headers can contain names, IDs, birth dates, facility/physician names, dates, accession numbers, device identifiers, burned-in annotations, and private vendor tags. The app should:

- encrypt originals and all metadata by default;
- show a PHI exposure preview before export;
- produce a separate de-identified derivative while preserving the encrypted original;
- detect burned-in text separately from header fields;
- remove/re-map UIDs consistently rather than deleting random tags;
- warn that face-bearing CT/MRI can remain identifiable even after header removal.

### J. Study handoff package

Create a standards-friendly, encrypted care bundle containing selected complete series, `DICOMDIR`, report, checksums, and an HTML inventory—without adding a proprietary viewer that may become unsafe or obsolete.

## 7. Open-source imaging projects worth integrating or studying

| Project | Role | Recommended use |
|---|---|---|
| [OHIF Viewer](https://github.com/OHIF/Viewers) | MIT web DICOM viewer | In-app 2D/3D and PET/CT viewing through an isolated local DICOMweb boundary. |
| [Cornerstone3D](https://github.com/cornerstonejs/cornerstone3D) | MIT browser imaging libraries underlying OHIF | Lower-level option for a focused viewer without adopting the whole OHIF application. |
| [3D Slicer](https://github.com/Slicer/Slicer) | BSD-style licensed medical visualization, volume rendering, segmentation, DICOM import/export | External advanced workspace and benchmark for 3D/segmentation workflows; do not rebuild its specialist tools. |
| [DCMTK](https://github.com/DCMTK/dcmtk) / [GDCM](https://github.com/malaterre/GDCM) | Mature DICOM codecs, parsers, networking, and validation tools | Sandboxed import/validation workers; test difficult transfer syntaxes with both where useful. |
| [dcmqi](https://github.com/QIICR/dcmqi) | BSD-3-Clause conversion for quantitative imaging results | SEG/RTSTRUCT/research-format interoperability. |
| [highdicom](https://github.com/ImagingDataCommons/highdicom) | MIT high-level Python DICOM abstractions | Synthetic SEG/SR fixtures and isolated conversion services. |
| [Orthanc](https://github.com/orthanc-mirrors/orthanc) | GPL-3.0 lightweight DICOM server/PACS with REST/DICOMweb plugins | Optional separate local imaging service, not a linked core dependency without a licensing/deployment decision. |
| [Weasis](https://github.com/nroduit/Weasis) | Mature desktop DICOM viewer with CD/DICOMDIR import/export | Compatibility and user-workflow benchmark; potentially an external “open with” option. |

## 8. Security warning for imaging media

A disc may contain old executable viewers, autorun files, malformed images, and sensitive metadata. The DICOM Security Group advises disabling file execution when reading CD/DVD media and never executing DICOM files. Viewer vulnerabilities also occur, so this project should:

- disable operating-system autorun;
- never launch `viewer.exe` or scripts from imported media;
- scan/quarantine executable files;
- parse in a low-privilege, network-disabled worker;
- treat every DICOM, PDF, image, ZIP, and viewer as hostile input;
- keep viewers and codecs patched;
- never upload unencrypted DICOM to a public sharing service or general AI tool.

## 9. Sources and standards

- [DICOM PS3.11 — Media Storage Application Profiles](https://dicom.nema.org/medical/dicom/current/output/html/part11.html)
- [NEMA — Displaying Medical Images from a CD](https://dicom.nema.org/documents/Displaying-Medical-Images-from-a-CD-2014-05-09.pdf)
- [DICOM Segmentation and Label Map Supplement](https://www.dicomstandard.org/news-dir/current/docs/sups/sup243.pdf)
- [DICOM Surface Segmentation Supplement](https://www.dicomstandard.org/News-dir/ftsup/docs/sups/sup132.pdf)
- [DICOM Encapsulation of STL Models](https://www.dicomstandard.org/news/supplements/view/dicom-encapsulation-of-stl-models-for-3d-manufacturing)
- [DICOM Encapsulation of OBJ Models](https://www.dicomstandard.org/news-dir/progress/docs/sups/sup208.pdf)
- [3D Slicer supported data formats](https://github.com/Slicer/Slicer/blob/main/Docs/user_guide/data_loading_and_saving.md)
- [3D Slicer DICOM guide](https://slicer.readthedocs.io/en/latest/user_guide/modules/dicom.html)
- [Library of Congress optical-disc preservation guidance](https://ask.loc.gov/preservation/faq/338800)
- [NIST care and handling of CDs/DVDs](https://nvlpubs.nist.gov/nistpubs/legacy/sp/NISTspecialpublication500-252.pdf)
- [DICOM Security Group media-file vulnerability FAQ](https://www.dicomstandard.org/docs/librariesprovider2/dicomdocuments/wp-cotent/uploads/2019/05/faq-dicom-128-byte-preamble-posted1-1.pdf)
