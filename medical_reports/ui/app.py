"""
Faseeh Scan — Flet application.

An encrypted document vault with a privacy-first scanner, backed up to the
user's own Google Drive. The UI is a thin shell: it collects a password and
some bytes, and the core/services do the security and feature work.

Run (desktop):
    flet run main.py
Package for Android:
    flet build apk
"""

from __future__ import annotations

import os
import platform
from pathlib import Path

import flet as ft

from .. import APP_NAME, __version__
from .. import crypto
from ..config import settings
from ..vault import Vault
from ..services import VaultService, DocumentsService, BackupService
from ..settings import Settings
from ..backends import LocalBackend, GoogleDriveBackend, GDriveNotConfigured
from ..features.capture import CaptureService, CaptureResult, CapturedPage
from ..features.processing import ProcessOptions, SUPPORTED as PROCESSING_SUPPORTED
from . import auth as google_auth


# Default vault location (per-user app data).
def default_vault_dir() -> Path:
    home = Path.home()
    if platform.system() == "Windows":
        base = Path(os.environ.get("APPDATA", home))
    elif platform.system() == "Darwin":
        base = home / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", home / ".local" / "share"))
    return base / "MedicalReportsBackup" / "vault"


PRIMARY = "#0f766e"  # teal-700
BG = "#f8fafc"


def human_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def _guess_ct(p: Path) -> str:
    return {
        ".pdf": "application/pdf", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".png": "image/png", ".webp": "image/webp", ".txt": "text/plain",
    }.get(p.suffix.lower(), "application/octet-stream")


class App:
    def __init__(self, page: ft.Page):
        self.page = page
        self.vault = Vault(default_vault_dir())
        self.vault_svc = VaultService(self.vault)
        self.settings = Settings.load()
        self.docs = DocumentsService(self.vault, self.settings)
        self.backup_svc = BackupService(self.vault)
        self.capture_svc = CaptureService(self.docs)
        self.backend = None
        self._search_query = ""
        # Pending pages captured via the file picker (list of Paths).
        self._pending_pages: list[Path] = []
        self.file_picker = ft.FilePicker(on_result=self.on_files_picked)
        # A second picker that feeds the scan review flow.
        self.scan_picker = ft.FilePicker(on_result=self._on_scan_picked)
        self.page.overlay.append(self.file_picker)
        self.page.overlay.append(self.scan_picker)
        self.page.title = APP_NAME
        self.page.theme = ft.Theme(color_scheme_seed=PRIMARY)
        self.page.bgcolor = BG
        self.page.padding = 0
        # Flet fires this after the Google OAuth redirect returns.
        self.page.on_login = self._on_google_login
        self.page.on_route_change = lambda e: self.route()
        # Pre-select a backend so the health indicator and auto-backup work
        # without an explicit "Backup now" first. Falls back to local folder.
        try:
            self.backup_svc.use(self._pick_backend())
        except Exception:
            pass
        self.route()

    # ---- routing ---------------------------------------------------------

    def route(self):
        if not self.vault_svc.exists:
            self.show_welcome()
        elif not self.vault_svc.is_unlocked:
            self.show_lock()
        else:
            self.show_documents()

    def snack(self, msg: str, error: bool = False):
        self.page.snack_bar = ft.SnackBar(
            ft.Text(msg), bgcolor=ft.Colors.RED if error else PRIMARY
        )
        self.page.snack_bar.open = True
        self.page.update()

    # ---- welcome / create ------------------------------------------------

    def show_welcome(self):
        pw = ft.TextField(label="Create a vault password", password=True, can_reveal_password=True, width=360)
        pw2 = ft.TextField(label="Confirm password", password=True, can_reveal_password=True, width=360)

        def create(_):
            if len(pw.value or "") < 8:
                return self.snack("Password must be at least 8 characters.", error=True)
            if pw.value != pw2.value:
                return self.snack("Passwords don't match.", error=True)
            try:
                self.vault_svc.create(pw.value)
                self.snack("Vault created.")
                self.show_documents()
            except Exception as e:
                self.snack(str(e), error=True)

        self.page.views.clear()
        self.page.views.append(ft.View(
            "/welcome",
            [
                ft.Container(
                    ft.Column([
                        ft.Icon(ft.Icons.HEALTH_AND_SAFETY, size=64, color=PRIMARY),
                        ft.Text(APP_NAME, size=28, weight=ft.FontWeight.BOLD),
                        ft.Text(
                            "Your documents, encrypted on this device and backed up to "
                            "your own Google Drive. No one — not even the app or Google — can "
                            "read them without your password.",
                            text_align=ft.TextAlign.CENTER, width=380, color=ft.Colors.GREY_700,
                        ),
                        pw, pw2,
                        ft.FilledButton("Create encrypted vault", on_click=create, width=360),
                        ft.Text("⚠ Remember this password. There is no reset — no one can recover it.",
                                size=12, color=ft.Colors.RED_400, width=360, text_align=ft.TextAlign.CENTER),
                    ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=16),
                    alignment=ft.alignment.center, expand=True, padding=32,
                )
            ],
            padding=0,
        ))
        self.page.update()

    # ---- unlock ----------------------------------------------------------

    def show_lock(self):
        pw = ft.TextField(label="Vault password", password=True, can_reveal_password=True,
                          width=320, on_submit=self._do_unlock)

        def _click(_):
            self._do_unlock(pw)

        self.page.views.clear()
        self.page.views.append(ft.View(
            "/unlock",
            [
                ft.Container(
                    ft.Column([
                        ft.Icon(ft.Icons.LOCK, size=56, color=PRIMARY),
                        ft.Text("Unlock your vault", size=22, weight=ft.FontWeight.BOLD),
                        pw,
                        ft.FilledButton("Unlock", on_click=_click, width=320),
                    ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=16),
                    alignment=ft.alignment.center, expand=True,
                )
            ],
            padding=0,
        ))
        self.page.update()

    def _do_unlock(self, pw):
        try:
            self.vault_svc.unlock(pw.value or "")
            self.show_documents()
        except crypto.WrongPasswordError:
            self.snack("Incorrect password.", error=True)
        except Exception as e:
            self.snack(str(e), error=True)

    # ---- Google sign-in (desktop/web/Android via Flet OAuth) -------------

    def _on_google_login(self, e):
        """Called by Flet when the Google OAuth flow completes."""
        if getattr(e, "error", ""):
            self.snack(f"Google sign-in failed: {e.error_description or e.error}",
                       error=True)
            return
        try:
            email = google_auth.signed_in_email(self.page) or "your Google account"
            self.snack(f"Signed in to Google as {email}.")
        except Exception as ex:
            self.snack(f"Signed in, but could not read profile: {ex}", error=True)
        # Re-render so the sidebar reflects the signed-in state.
        if self.vault_svc.is_unlocked:
            self.show_documents()

    def sign_in_google(self, _=None):
        if not google_auth.is_google_configured():
            self.snack(
                "Google sign-in isn't configured. Copy .env.example to .env and "
                "set GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET.", error=True)
            return
        if self.page.auth and self.page.auth.token:
            self.snack("Already signed in to Google.")
            return
        try:
            google_auth.login(self.page)
        except Exception as ex:
            self.snack(f"Could not start Google sign-in: {ex}", error=True)

    def sign_out_google(self, _=None):
        # Flet clears the in-memory token; revoke at Google if desired later.
        self.page.auth = None
        self.snack("Signed out of Google.")
        self.show_documents()

    def _google_email(self) -> str | None:
        return google_auth.signed_in_email(self.page)

    def _is_signed_in(self) -> bool:
        try:
            return bool(self.page.auth and self.page.auth.token)
        except Exception:
            return False

    # ---- documents list ----------------------------------------------------

    def show_documents(self):
        self.page.views.clear()
        rail = self._build_sidebar()
        body = ft.Container(self._build_documents_view(), expand=True, padding=24)
        self.page.views.append(ft.View(
            "/documents",
            [ft.Row([rail, ft.VerticalDivider(width=1), body], expand=True, spacing=0)],
            padding=0,
        ))
        self.page.update()

    def _build_sidebar(self):
        # Backup health indicator.
        health = self.backup_svc.health() if self.backup_svc.backend else None
        if health is None:
            health_dot = ft.Row([
                ft.Icon(ft.Icons.CLOUD_OFF, size=16, color=ft.Colors.GREY_500),
                ft.Text("No backup selected", size=11, color=ft.Colors.GREY_600),
            ])
        elif health["ok"]:
            health_dot = ft.Row([
                ft.Icon(ft.Icons.CHECK_CIRCLE, size=16, color=ft.Colors.GREEN),
                ft.Text("All backed up", size=11, color=ft.Colors.GREY_700),
            ])
        else:
            health_dot = ft.Row([
                ft.Icon(ft.Icons.ERROR, size=16, color=ft.Colors.ORANGE),
                ft.Text(f"{health['pending']} not backed up", size=11,
                        color=ft.Colors.ORANGE),
            ])

        def nav(icon, label, on_click):
            return ft.Container(
                ft.Row([ft.Icon(icon, color=ft.Colors.GREY_700),
                        ft.Text(label, color=ft.Colors.GREY_800)]),
                padding=ft.padding.symmetric(horizontal=16, vertical=10),
                border_radius=8, on_click=on_click, ink=True, width=220,
            )

        # Google account status + sign in/out.
        email = self._google_email()
        if self._is_signed_in():
            account_row = ft.Container(
                ft.Column([
                    ft.Row([ft.Icon(ft.Icons.ACCOUNT_CIRCLE, color=ft.Colors.GREEN, size=20),
                            ft.Text("Google Drive connected", size=12, weight=ft.FontWeight.W_600)]),
                    ft.Text(email or "signed in", size=11, color=ft.Colors.GREY_600,
                            max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                    ft.TextButton("Sign out", on_click=self.sign_out_google, icon=ft.Icons.LOGOUT),
                ], spacing=2),
                padding=ft.padding.symmetric(horizontal=16, vertical=8),
            )
        else:
            account_row = ft.Container(
                ft.Column([
                    ft.Row([ft.Icon(ft.Icons.ACCOUNT_CIRCLE, color=ft.Colors.GREY_500, size=20),
                            ft.Text("Not connected", size=12, color=ft.Colors.GREY_600)]),
                    ft.OutlinedButton(
                        "Sign in with Google", on_click=self.sign_in_google,
                        icon=ft.Icons.LOGIN, width=220,
                    ),
                    ft.Text("Needed to back up to your Google Drive.", size=10,
                            color=ft.Colors.GREY_500),
                ], spacing=6),
                padding=ft.padding.symmetric(horizontal=16, vertical=8),
            )

        return ft.Container(
            ft.Column([
                ft.Container(
                    ft.Row([ft.Icon(ft.Icons.HEALTH_AND_SAFETY, color=PRIMARY, size=28),
                            ft.Text(APP_NAME, weight=ft.FontWeight.BOLD)], spacing=8),
                    padding=20,
                ),
                ft.Divider(height=1),
                account_row,
                ft.Divider(height=1),
                ft.Container(
                    ft.Row([health_dot], spacing=6),
                    padding=ft.padding.symmetric(horizontal=16, vertical=8),
                ),
                nav(ft.Icons.DOCUMENT_SCANNER, "Scan document", self.start_scan),
                nav(ft.Icons.FOLDER_SHARED, "Add document", lambda e: self.file_picker.pick_files(
                    allow_multiple=True,
                    allowed_extensions=["pdf", "jpg", "jpeg", "png", "doc", "docx", "txt", "webp"])),
                nav(ft.Icons.PICTURE_AS_PDF, "Images to PDF", self.images_to_pdf),
                nav(ft.Icons.DELETE_OUTLINE, "Trash", self.show_trash),
                nav(ft.Icons.CLOUD_UPLOAD, "Backup now", self.backup_now),
                nav(ft.Icons.CLOUD_DOWNLOAD, "Restore from Drive", self.restore_now),
                nav(ft.Icons.SETTINGS, "Settings", self.settings_dialog),
                nav(ft.Icons.KEY, "Change password", self.change_password_dialog),
                nav(ft.Icons.LOCK_OUTLINE, "Lock vault", lambda e: self.lock_vault()),
                ft.Container(expand=True),
                ft.Text(f"v{__version__}", size=11, color=ft.Colors.GREY_400, padding=16),
            ], spacing=4),
            width=250, bgcolor=ft.Colors.WHITE,
        )

    def _build_documents_view(self):
        documents = (self.docs.search(self._search_query)
                     if self._search_query.strip() else self.docs.list())
        title = ft.Text("Your documents", size=26, weight=ft.FontWeight.BOLD)

        search_field = ft.TextField(
            hint_text="Search by name, tag, or text inside…",
            prefix_icon=ft.Icons.SEARCH,
            value=self._search_query or "",
            width=420,
            dense=True,
            on_change=self._on_search,
        )

        if not documents:
            empty_msg = ("No matches" if self._search_query.strip()
                         else "No documents yet")
            empty_hint = ("Try a different search." if self._search_query.strip()
                          else "Add a PDF, photo, or document — it's encrypted on this device.")
            content = ft.Column([
                title, search_field,
                ft.Container(
                    ft.Column([
                        ft.Icon(ft.Icons.SEARCH if self._search_query.strip()
                                else ft.Icons.DESCRIPTION_OUTLINED,
                                size=64, color=ft.Colors.GREY_300),
                        ft.Text(empty_msg, size=18, color=ft.Colors.GREY_600),
                        ft.Text(empty_hint, color=ft.Colors.GREY_500),
                    ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=12),
                    alignment=ft.alignment.center, expand=True,
                ),
            ], expand=True)
        else:
            rows = [self._document_card(r) for r in documents]
            count = f"{len(documents)} document(s)"
            if self._search_query.strip():
                count += f" matching “{self._search_query}”"
            content = ft.Column([
                ft.Row([title], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                ft.Row([search_field]),
                ft.Text(count, color=ft.Colors.GREY_600),
                ft.ListView(rows, spacing=10, expand=True, padding=ft.padding.only(top=8)),
            ], expand=True)
        return content

    def _on_search(self, e):
        self._search_query = e.control.value or ""
        self.show_documents()

    def _document_card(self, r):
        icons = {
            "application/pdf": ft.Icons.PICTURE_AS_PDF,
            "image/jpeg": ft.Icons.IMAGE,
            "image/png": ft.Icons.IMAGE,
        }
        badge = ft.Container(
            ft.Row([ft.Icon(ft.Icons.CLOUD_DONE, size=14, color=ft.Colors.WHITE),
                    ft.Text("Backed up", size=11, color=ft.Colors.WHITE)], spacing=4),
            bgcolor=ft.Colors.GREEN, padding=ft.padding.symmetric(horizontal=8, vertical=3),
            border_radius=12, visible=bool(r.backed_up_to),
        )
        ocr_badge = ft.Container(
            ft.Text("OCR", size=10, color=ft.Colors.WHITE),
            bgcolor=ft.Colors.BLUE_GREY, padding=ft.padding.symmetric(horizontal=6, vertical=2),
            border_radius=8, visible=("ocr" in r.artifacts),
        )
        thumb = self._thumbnail_widget(r)
        return ft.Card(
            ft.Container(
                ft.Row([
                    thumb,
                    ft.Column([
                        ft.Row([ft.Text(r.name, weight=ft.FontWeight.W_600, size=15),
                                badge, ocr_badge]),
                        ft.Text(f"{human_size(r.size)} · encrypted",
                                size=12, color=ft.Colors.GREY_600),
                        ft.Text(r.note, size=11, color=ft.Colors.GREY_500) if r.note else ft.Container(),
                    ], spacing=4, expand=True),
                    ft.IconButton(ft.Icons.HISTORY, tooltip="Version history",
                                  visible=bool(r.versions),
                                  on_click=lambda e, rid=r.id: self.show_history(rid)),
                    ft.IconButton(ft.Icons.EDIT_NOTE,
                                  tooltip="Arrange pages",
                                  visible=(r.content_type == "application/pdf"),
                                  on_click=lambda e, rid=r.id: self.edit_pdf(rid)),
                    ft.IconButton(ft.Icons.DOWNLOAD, tooltip="Decrypt & save",
                                  on_click=lambda e, rid=r.id: self.save_document(rid)),
                    ft.IconButton(ft.Icons.DELETE_OUTLINE, tooltip="Move to trash",
                                  on_click=lambda e, rid=r.id: self.delete_document(rid)),
                ], alignment=ft.MainAxisAlignment.START),
                padding=14,
            ),
            elevation=1,
        )

    def _thumbnail_widget(self, r):
        icon = {
            "application/pdf": ft.Icons.PICTURE_AS_PDF,
            "image/jpeg": ft.Icons.IMAGE,
            "image/png": ft.Icons.IMAGE,
        }.get(r.content_type, ft.Icons.DESCRIPTION)
        if "thumb" not in r.artifacts:
            return ft.Icon(icon, size=40, color=PRIMARY)
        try:
            data = self.docs.get_artifact(r.id, "thumb")
            import base64
            b64 = base64.b64encode(data).decode("ascii")
            return ft.Container(
                ft.Image(src_base64=b64, width=50, height=66, fit=ft.ImageFit.COVER,
                         border_radius=ft.border_radius.all(4)),
                width=50, height=66,
            )
        except Exception:
            return ft.Icon(icon, size=40, color=PRIMARY)

    # ---- scan / capture flow --------------------------------------------

    def start_scan(self, _=None):
        """Begin a scan. Use the native ML Kit scanner when available,
        otherwise let the user pick images from the device and review them."""
        providers = self.capture_svc.available_providers()
        mlkit = next((p for p in providers if p.id == "mlkit"), None)
        if mlkit is not None:
            # Native scanner returns directly; no review screen needed.
            self._run_native_scan(mlkit)
            return
        # Desktop/web/no Play Services: choose images and review.
        self._pending_pages = []
        self._images_to_pdf_mode = False
        self.scan_picker.pick_files(
            allow_multiple=True,
            allowed_extensions=["jpg", "jpeg", "png", "webp", "pdf"],
            file_type=ft.FilePickerFileType.IMAGE,
        )

    def _run_native_scan(self, provider):
        try:
            doc = self.capture_svc.capture_to_vault(
                provider,
                name="scan.pdf",
                multi_page=True,
                process=False,          # ML Kit already produces clean pages
                as_pdf=True,
                ocr=self._ocr_enabled(),
            )
            self.snack(f"Scanned and encrypted: {doc.name}")
            self._maybe_auto_backup()
            self.show_documents()
        except Exception as ex:
            self.snack(f"Scan failed: {ex}", error=True)

    def _on_scan_picked(self, e: ft.FilePickerResultEvent):
        if not e.files:
            return
        # Append newly chosen pages to any pages already chosen in this session.
        self._pending_pages = self._pending_pages + [Path(f.path) for f in e.files]
        # If "Images to PDF" was chosen, open the same review but force PDF mode.
        if getattr(self, "_images_to_pdf_mode", False):
            self._show_scan_review(force_pdf=True, force_name="images.pdf")
        else:
            self._show_scan_review()

    def _ocr_enabled(self) -> bool:
        return bool(self.settings.ocr_enabled)

    def _show_scan_review(self, force_pdf: bool = False, force_name: str | None = None):
        """Review chosen pages: reorder/rotate/remove, choose a look, name, save."""
        # Working copy: list of (path, per-page rotation in degrees).
        pages = [[p, 0] for p in self._pending_pages]

        filter_dd = ft.Dropdown(
            label="Look", value=self.settings.default_filter, width=220, dense=True,
            options=[ft.dropdown.Option(k, label=label) for k, label in [
                ("magic", "Clean scan"),
                ("color", "Color"),
                ("gray", "Grayscale"),
                ("bw", "Black & white"),
                ("original", "Original photo"),
            ]],
        )
        as_pdf = ft.Switch(label="Combine into a PDF",
                           value=True if force_pdf else True, width=220)
        process_toggle = ft.Switch(
            label="Clean up pages", value=PROCESSING_SUPPORTED, width=220,
            disabled=not PROCESSING_SUPPORTED,
        )
        ocr_toggle = ft.Switch(
            label="Extract text (OCR, makes searchable)",
            value=self.settings.ocr_enabled, width=360,
        )
        name_field = ft.TextField(
            label="Document name",
            value=force_name or self._default_scan_name(), width=380,
        )

        def refresh():
            page_count.value = f"{len(pages)} page(s)"
            # rebuild reorderable list
            order_col.controls.clear()
            for i, (path, rot) in enumerate(pages):
                order_col.controls.append(_page_row(i, path, rot))
            self.page.update()

        def move(index, delta):
            j = index + delta
            if 0 <= j < len(pages):
                pages[index], pages[j] = pages[j], pages[index]
                refresh()

        def rotate_one(index):
            pages[index][1] = (pages[index][1] + 90) % 360
            refresh()

        def remove_one(index):
            del pages[index]
            refresh()

        def _page_row(i, path, rot):
            return ft.Row([
                ft.Text(str(i + 1), width=24, color=ft.Colors.GREY_700,
                        weight=ft.FontWeight.W_600),
                ft.Icon(ft.Icons.IMAGE, size=18, color=ft.Colors.GREY_500),
                ft.Text(path.name, expand=True, max_lines=1,
                        overflow=ft.TextOverflow.ELLIPSIS, size=13),
                ft.Text(f"{rot}\u00b0", size=12, color=ft.Colors.GREY_600, width=34),
                ft.IconButton(ft.Icons.ARROW_UPWARD, icon_size=18,
                              tooltip="Move up", on_click=lambda e, idx=i: move(idx, -1)),
                ft.IconButton(ft.Icons.ARROW_DOWNWARD, icon_size=18,
                              tooltip="Move down", on_click=lambda e, idx=i: move(idx, 1)),
                ft.IconButton(ft.Icons.ROTATE_RIGHT, icon_size=18,
                              tooltip="Rotate page", on_click=lambda e, idx=i: rotate_one(idx)),
                ft.IconButton(ft.Icons.DELETE_OUTLINE, icon_size=18,
                              tooltip="Remove page", on_click=lambda e, idx=i: remove_one(idx)),
            ], spacing=2)

        page_count = ft.Text(f"{len(pages)} page(s)", color=ft.Colors.GREY_700)
        order_col = ft.Column([], spacing=2)

        def save(_):
            if not pages:
                self.snack("Add at least one page.", error=True)
                return
            self.settings.ocr_enabled = bool(ocr_toggle.value)
            self.settings.default_filter = filter_dd.value or "magic"
            self.settings.save()
            dlg.open = False
            self.page.update()
            self._save_scan(
                name=name_field.value or "scan.pdf",
                filter_name=filter_dd.value or "magic",
                process=bool(process_toggle.value) and not force_pdf,
                as_pdf=bool(as_pdf.value),
                pages=[(p, r) for p, r in pages],
                source="import" if force_pdf else "camera",
            )
            self._images_to_pdf_mode = False

        def add_more(_):
            dlg.open = False
            self.page.update()
            self._pending_pages = [p for p, _ in pages]
            self.scan_picker.pick_files(
                allow_multiple=True, file_type=ft.FilePickerFileType.IMAGE,
                allowed_extensions=["jpg", "jpeg", "png", "webp"],
            )

        refresh()

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("Arrange pages"),
            content=ft.Container(
                ft.Column([
                    page_count,
                    ft.Container(
                        order_col, height=220, width=520,
                        border=ft.border.all(1, ft.Colors.GREY_300), border_radius=8,
                        padding=8,
                    ),
                    name_field,
                    ft.Row([filter_dd]),
                    process_toggle,
                    as_pdf,
                    ocr_toggle,
                    ft.Text(
                        "Drag-free reorder with the arrows; rotate or remove any page. "
                        "Everything is processed on this device and stored encrypted.",
                        size=11, color=ft.Colors.GREY_600, width=480),
                ], tight=True, spacing=12, scroll=ft.ScrollMode.AUTO),
                width=560,
            ),
            actions=[
                ft.TextButton("Add pages", on_click=add_more),
                ft.TextButton("Cancel", on_click=lambda e: self._close_dlg(dlg)),
                ft.FilledButton("Save encrypted", on_click=save),
            ],
        )
        self.page.open(dlg)

    def _default_scan_name(self) -> str:
        from time import strftime
        return f"Scan {strftime('%Y-%m-%d %H%M')}.pdf"

    def _save_scan(self, *, name: str, filter_name: str, process: bool, as_pdf: bool,
                   pages=None, source: str = "camera"):
        try:
            pages = pages or [(p, 0) for p in self._pending_pages]
            captured = [CapturedPage(path=p, content_type=_guess_ct(p), source=source)
                        for p, _ in pages]
            rotations = [r for _, r in pages]
            result = CaptureResult(pages=captured)
            options = ProcessOptions(filter=filter_name)
            doc = self.capture_svc.store_result(
                result,
                name=name,
                process=process,
                options=options,
                as_pdf=as_pdf,
                ocr=self._ocr_enabled(),
                source=source,
                per_page_rotations=rotations,
            )
            self.snack(f"Encrypted: {doc.name}")
            self._maybe_auto_backup()
        except Exception as ex:
            self.snack(f"Could not save scan: {ex}", error=True)
        finally:
            self._pending_pages = []
            self.show_documents()

    # ---- images -> PDF (existing images combined, not necessarily scans) --

    def images_to_pdf(self, _=None):
        self._pending_pages = []
        self._images_to_pdf_mode = True
        self.scan_picker.pick_files(
            allow_multiple=True, file_type=ft.FilePickerFileType.IMAGE,
            allowed_extensions=["jpg", "jpeg", "png", "webp"],
        )

    # ---- trash ------------------------------------------------------------

    def show_trash(self, _=None):
        self.page.views.clear()
        rail = self._build_sidebar()
        body = ft.Container(self._build_trash_view(), expand=True, padding=24)
        self.page.views.append(ft.View(
            "/trash",
            [ft.Row([rail, ft.VerticalDivider(width=1), body], expand=True, spacing=0)],
            padding=0,
        ))
        self.page.update()

    def _build_trash_view(self):
        trashed = self.docs.list_trash()
        title = ft.Text("Trash", size=26, weight=ft.FontWeight.BOLD)
        if not trashed:
            return ft.Column([
                title,
                ft.Container(
                    ft.Column([
                        ft.Icon(ft.Icons.DELETE_OUTLINE, size=64, color=ft.Colors.GREY_300),
                        ft.Text("Trash is empty", color=ft.Colors.GREY_600),
                    ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=12),
                    alignment=ft.alignment.center, expand=True),
            ], expand=True)
        rows = []
        for d in trashed:
            rows.append(ft.Card(ft.Container(ft.Row([
                ft.Icon(ft.Icons.DELETE, color=ft.Colors.GREY_500, size=28),
                ft.Column([ft.Text(d.name, weight=ft.FontWeight.W_600)], expand=True),
                ft.TextButton("Restore", on_click=lambda e, rid=d.id: self._restore_doc(rid)),
                ft.IconButton(ft.Icons.DELETE_FOREVER, tooltip="Delete forever",
                              on_click=lambda e, rid=d.id: self._purge_doc(rid)),
            ]), padding=12), elevation=1))
        return ft.Column([
            ft.Row([title, ft.Container(expand=True),
                    ft.OutlinedButton("Empty trash", icon=ft.Icons.DELETE_SWEEP,
                                      on_click=self.empty_trash)]),
            ft.ListView(rows, spacing=8, expand=True, padding=ft.padding.only(top=8)),
        ], expand=True)

    def _restore_doc(self, rid: str):
        self.docs.restore(rid)
        self.snack("Document restored.")
        self.show_trash()

    def _purge_doc(self, rid: str):
        def confirm(_):
            self.docs.delete(rid)
            dlg.open = False
            self.page.update()
            self.show_trash()
        dlg = ft.AlertDialog(
            title=ft.Text("Delete forever?"),
            content=ft.Text("This permanently erases the encrypted document and cannot be undone."),
            actions=[ft.TextButton("Cancel", on_click=lambda e: self._close_dlg(dlg)),
                     ft.FilledButton("Delete", on_click=confirm)],
        )
        self.page.open(dlg)

    # ---- post-save PDF editing (reorder / rotate / delete pages) ---------

    def edit_pdf(self, rid: str):
        from ..features.pdf_tools import page_count
        meta, data = self.docs.get(rid)
        try:
            n = page_count(data)
        except Exception as ex:
            self.snack(f"Not a multi-page PDF: {ex}", error=True)
            return
        order = list(range(n))
        rotations = {i: 0 for i in range(n)}

        def rebuild():
            col.controls.clear()
            for pos, idx in enumerate(order):
                col.controls.append(ft.Row([
                    ft.Text(f"{pos+1}.", width=30, color=ft.Colors.GREY_700),
                    ft.Text(f"page {idx+1}", expand=True, size=13),
                    ft.Text(f"{rotations[idx]}\u00b0", width=40, size=12, color=ft.Colors.GREY_600),
                    ft.IconButton(ft.Icons.ARROW_UPWARD, icon_size=18,
                                  on_click=lambda e, i=pos: move(i, -1)),
                    ft.IconButton(ft.Icons.ARROW_DOWNWARD, icon_size=18,
                                  on_click=lambda e, i=pos: move(i, 1)),
                    ft.IconButton(ft.Icons.ROTATE_RIGHT, icon_size=18,
                                  on_click=lambda e, i=idx: rotate(i)),
                    ft.IconButton(ft.Icons.CLOSE, icon_size=18,
                                  on_click=lambda e, i=idx: remove(i)),
                ], spacing=2))
            self.page.update()

        def move(pos, delta):
            j = pos + delta
            if 0 <= j < len(order):
                order[pos], order[j] = order[j], order[pos]
                rebuild()

        def rotate(idx):
            rotations[idx] = (rotations[idx] + 90) % 360
            rebuild()

        def remove(idx):
            if idx in order:
                order.remove(idx)
            rebuild()

        def apply(_):
            from ..features.pdf_tools import rearrange_pdf
            new_bytes = rearrange_pdf(data, order,
                                      rotations={i: rotations[i] for i in order if rotations[i]})
            self.docs.replace_blob(rid, new_bytes, content_type="application/pdf")
            dlg.open = False
            self.page.update()
            self.snack("PDF updated.")
            self._maybe_auto_backup()
            self.show_documents()

        col = ft.Column([], spacing=2)
        rebuild()
        dlg = ft.AlertDialog(
            modal=True, title=ft.Text(f"Arrange — {meta.name}"),
            content=ft.Container(
                ft.Column([
                    ft.Text("Reorder, rotate, or remove pages.", size=12, color=ft.Colors.GREY_600),
                    ft.Container(col, height=300, width=480,
                                 border=ft.border.all(1, ft.Colors.GREY_300),
                                 border_radius=8, padding=8),
                ], tight=True, spacing=10), width=520),
            actions=[
                ft.TextButton("Cancel", on_click=lambda e: self._close_dlg(dlg)),
                ft.FilledButton("Apply changes", on_click=apply),
            ],
        )
        self.page.open(dlg)

    # ---- settings --------------------------------------------------------

    def settings_dialog(self, _=None):
        ocr_switch = ft.Switch(
            label="Extract text from scans (OCR, makes searchable)",
            value=self.settings.ocr_enabled, width=420)
        wifi_switch = ft.Switch(
            label="Auto-backup over Wi-Fi only",
            value=self.settings.wifi_only_backup, width=420)
        filter_dd = ft.Dropdown(
            label="Default scan look", value=self.settings.default_filter, width=240, dense=True,
            options=[ft.dropdown.Option(k, label=l) for k, l in [
                ("magic", "Clean scan"), ("color", "Color"),
                ("gray", "Grayscale"), ("bw", "Black & white"),
                ("original", "Original")]])

        def save(_):
            self.settings.ocr_enabled = bool(ocr_switch.value)
            self.settings.wifi_only_backup = bool(wifi_switch.value)
            self.settings.default_filter = filter_dd.value or "magic"
            self.settings.save()
            dlg.open = False
            self.page.update()
            self.snack("Settings saved.")
            self.show_documents()

        dlg = ft.AlertDialog(
            modal=True, title=ft.Text("Settings"),
            content=ft.Container(ft.Column([
                ft.Text("Scanning", weight=ft.FontWeight.W_600),
                filter_dd, ocr_switch,
                ft.Divider(),
                ft.Text("Backup", weight=ft.FontWeight.W_600),
                wifi_switch,
                ft.Text("A backup runs automatically after you add or edit a "
                        "document when a destination is available.",
                        size=11, color=ft.Colors.GREY_600, width=440),
            ], tight=True, spacing=12, width=460), width=480),
            actions=[ft.TextButton("Cancel", on_click=lambda e: self._close_dlg(dlg)),
                     ft.FilledButton("Save", on_click=save)],
        )
        self.page.open(dlg)

    # ---- version history -------------------------------------------------

    def show_history(self, rid: str):
        meta, _ = self.docs.get(rid)
        versions = self.docs.list_versions(rid)
        rows = []

        # Current version row
        rows.append(ft.Container(
            ft.Row([
                ft.Icon(ft.Icons.FIBER_MANUAL_RECORD, size=12, color=ft.Colors.GREEN),
                ft.Column([
                    ft.Text("Current version", weight=ft.FontWeight.W_600, size=13),
                    ft.Text(f"{human_size(meta.size)} · {meta.content_type}",
                            size=11, color=ft.Colors.GREY_600),
                ], expand=True),
            ]),
            padding=10, bgcolor=ft.Colors.GREY_100, border_radius=6,
        ))

        def restore(key):
            self.docs.restore_version(rid, key)
            dlg.open = False
            self.page.update()
            self.snack("Restored previous version.")
            self._maybe_auto_backup()
            self.show_documents()

        import time as _t
        for v in reversed(versions):
            key = v["artifact"]
            when = _t.strftime("%Y-%m-%d %H:%M", _t.localtime(v.get("created_at", 0)))
            rows.append(ft.Container(
                ft.Row([
                    ft.Icon(ft.Icons.HISTORY_TOGGLE_OFF, size=16, color=ft.Colors.GREY_600),
                    ft.Column([
                        ft.Text(f"{v.get('label', 'edit')} · {when}", size=13),
                        ft.Text(f"{human_size(v.get('size', 0))} · {v.get('content_type', '')}",
                                size=11, color=ft.Colors.GREY_600),
                    ], expand=True),
                    ft.TextButton("Restore", on_click=lambda e, k=key: restore(k)),
                ]),
                padding=10,
            ))

        dlg = ft.AlertDialog(
            modal=True, title=ft.Text(f"History — {meta.name}"),
            content=ft.Container(
                ft.Column(rows if rows else [
                    ft.Text("No previous versions yet.", color=ft.Colors.GREY_600)],
                          tight=True, spacing=8, scroll=ft.ScrollMode.AUTO),
                width=520, height=360),
            actions=[ft.TextButton("Close", on_click=lambda e: self._close_dlg(dlg))],
        )
        self.page.open(dlg)

    # ---- actions ---------------------------------------------------------

    def on_files_picked(self, e: ft.FilePickerResultEvent):
        if not e.files:
            return
        added = 0
        for f in e.files:
            p = Path(f.path)
            try:
                data = p.read_bytes()
                ctype = {
                    ".pdf": "application/pdf", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                    ".png": "image/png", ".doc": "application/msword",
                    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    ".txt": "text/plain", ".webp": "image/webp",
                }.get(p.suffix.lower(), "application/octet-stream")
                self.docs.add(data, f.name, content_type=ctype)
                added += 1
            except Exception as ex:
                self.snack(f"Failed to add {f.name}: {ex}", error=True)
        self.snack(f"Encrypted and added {added} document(s).")
        self._maybe_auto_backup()
        self.show_documents()

    def save_document(self, rid: str):
        def pick(e: ft.FilePickerResultEvent):
            if not e.path:
                return
            try:
                meta, data = self.docs.get(rid)
                Path(e.path).write_bytes(data)
                self.snack(f"Decrypted and saved {meta.name}.")
            except Exception as ex:
                self.snack(str(ex), error=True)

        saver = ft.FilePicker(on_result=pick)
        self.page.overlay.append(saver)
        self.page.update()
        meta = self.docs.list()  # refresh
        name = next((r.name for r in meta if r.id == rid), "document")
        saver.save_file(file_name=name)

    def delete_document(self, rid: str):
        """Move to trash (soft delete), with an Undo snackbar."""
        meta = self.docs.get(rid)[0]
        self.docs.trash(rid)

        def undo(_):
            self.docs.restore(rid)
            self.page.snack_bar.open = False
            self.show_documents()

        self.page.snack_bar = ft.SnackBar(
            ft.Row([
                ft.Text(f"Moved “{meta.name}” to trash.", color=ft.Colors.WHITE, expand=True),
                ft.TextButton("Undo", on_click=undo),
            ]),
            bgcolor=ft.Colors.GREY_900, duration=5000,
        )
        self.page.snack_bar.open = True
        self.show_documents()

    def empty_trash(self, _=None):
        def confirm(_):
            n = self.docs.empty_trash()
            dlg.open = False
            self.page.update()
            self.snack(f"Permanently deleted {n} document(s).")
            self.show_documents()
        dlg = ft.AlertDialog(
            title=ft.Text("Empty trash?"),
            content=ft.Text("This permanently erases trashed documents and cannot be undone."),
            actions=[ft.TextButton("Cancel", on_click=lambda e: self._close_dlg(dlg)),
                     ft.FilledButton("Delete forever", on_click=confirm)],
        )
        self.page.open(dlg)

    def _close_dlg(self, dlg):
        dlg.open = False
        self.page.update()

    def lock_vault(self):
        self.vault_svc.lock()
        self.show_lock()

    def change_password_dialog(self, _=None):
        old = ft.TextField(label="Current password", password=True, can_reveal_password=True)
        new = ft.TextField(label="New password", password=True, can_reveal_password=True)
        new2 = ft.TextField(label="Confirm new password", password=True, can_reveal_password=True)

        def do_change(_):
            if len(new.value or "") < 8:
                return self.snack("New password must be at least 8 characters.", error=True)
            if new.value != new2.value:
                return self.snack("New passwords don't match.", error=True)
            try:
                self.vault_svc.change_password(old.value or "", new.value or "")
                dlg.open = False
                self.page.update()
                self.snack("Password changed. Run a backup to sync the new key file.")
            except crypto.WrongPasswordError:
                self.snack("Current password is incorrect.", error=True)

        dlg = ft.AlertDialog(
            title=ft.Text("Change vault password"),
            content=ft.Column([old, new, new2], tight=True, width=360),
            actions=[ft.TextButton("Cancel", on_click=lambda e: self._close_dlg(dlg)),
                     ft.FilledButton("Change", on_click=do_change)],
        )
        self.page.open(dlg)

    # ---- backup / restore ------------------------------------------------

    def _pick_backend(self):
        """Return a configured StorageBackend.

        Priority:
          1. Signed-in Google session via Flet OAuth (works on Android/web/desktop).
          2. Desktop installed-app OAuth via credentials/client_secret.json.
          3. Local folder fallback (USB/SD card), no account required.
        """
        if self._is_signed_in():
            return google_auth.build_drive_backend(self.page)

        if Path("credentials/client_secret.json").exists():
            be = GoogleDriveBackend()
            if be.is_configured():
                return be

        return LocalBackend(Path.home() / "MedicalReportsBackup" / "drive-sync")

    def _select_backend(self):
        """Pick a storage backend and register it with BackupService."""
        be = self._pick_backend()
        self.backup_svc.use(be)
        return be

    def _maybe_auto_backup(self):
        """If a backend is configured and Wi-Fi-only allows it, sync pending
        files. Errors are swallowed (backup is a background safety net)."""
        if not self.backup_svc.backend:
            try:
                self._select_backend()
            except Exception:
                return
        if self.backup_svc.backend and self.backup_svc.pending_count() > 0:
            try:
                self.backup_svc.auto_backup_if_needed(
                    wifi_only=self.settings.wifi_only_backup)
            except Exception:
                pass

    def backup_now(self, _=None):
        try:
            be = self._select_backend()
        except GDriveNotConfigured as e:
            self.snack(f"{e} Tap 'Sign in with Google' first.", error=True)
            return
        self.snack(f"Backing up to {be.display_name}…")
        try:
            n = be.backup_vault(self.vault)
            self.snack(f"Backup complete — {n} encrypted file(s) in {be.display_name}.")
        except GDriveNotConfigured as e:
            self.snack(str(e), error=True)
        except Exception as e:
            self.snack(f"Backup failed: {e}", error=True)
        finally:
            self.show_documents()

    def restore_now(self, _=None):
        try:
            be = self._pick_backend()
        except GDriveNotConfigured as e:
            self.snack(f"{e} Tap 'Sign in with Google' first.", error=True)
            return
        try:
            n = be.restore_vault(self.vault)
            if self.vault_svc.is_unlocked:
                self.vault_svc.lock()
            self.snack(f"Restored {n} file(s). Unlock to view your documents.")
            self.show_lock()
        except Exception as e:
            self.snack(f"Restore failed: {e}", error=True)


def main(page: ft.Page):
    App(page)
