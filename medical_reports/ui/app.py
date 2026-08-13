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
                nav(ft.Icons.DOCUMENT_SCANNER, "Scan document", self.start_scan),
                nav(ft.Icons.FOLDER_SHARED, "Add document", lambda e: self.file_picker.pick_files(
                    allow_multiple=True,
                    allowed_extensions=["pdf", "jpg", "jpeg", "png", "doc", "docx", "txt", "webp"])),
                nav(ft.Icons.CLOUD_UPLOAD, "Backup now", self.backup_now),
                nav(ft.Icons.CLOUD_DOWNLOAD, "Restore from Drive", self.restore_now),
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
                    ft.IconButton(ft.Icons.DOWNLOAD, tooltip="Decrypt & save",
                                  on_click=lambda e, rid=r.id: self.save_document(rid)),
                    ft.IconButton(ft.Icons.DELETE_OUTLINE, tooltip="Delete",
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
            self.show_documents()
        except Exception as ex:
            self.snack(f"Scan failed: {ex}", error=True)

    def _on_scan_picked(self, e: ft.FilePickerResultEvent):
        if not e.files:
            return
        self._pending_pages = [Path(f.path) for f in e.files]
        self._show_scan_review()

    def _ocr_enabled(self) -> bool:
        return bool(self.settings.ocr_enabled)

    def _show_scan_review(self):
        """Review chosen pages: choose a filter, toggle PDF, name, save."""
        filter_dd = ft.Dropdown(
            label="Look", value=self.settings.default_filter, width=200, dense=True,
            options=[ft.dropdown.Option(k, label=label) for k, label in [
                ("magic", "Clean scan"),
                ("color", "Color"),
                ("gray", "Grayscale"),
                ("bw", "Black & white"),
                ("original", "Original photo"),
            ]],
        )
        as_pdf = ft.Switch(label="Combine into PDF", value=True, width=220)
        process_toggle = ft.Switch(
            label="Clean up pages", value=PROCESSING_SUPPORTED, width=220,
            disabled=not PROCESSING_SUPPORTED,
        )
        ocr_toggle = ft.Switch(
            label="Extract text (OCR, makes searchable)",
            value=self.settings.ocr_enabled, width=360,
        )
        name_field = ft.TextField(
            label="Document name", value=self._default_scan_name(), width=320,
        )
        page_count = ft.Text(f"{len(self._pending_pages)} page(s)",
                             color=ft.Colors.GREY_700)
        rotation = {"deg": 0}

        def rotate_pages(_):
            rotation["deg"] = (rotation["deg"] + 90) % 360
            rotate_btn.text = f"Rotate {rotation['deg']}\u00b0"
            self.page.update()

        rotate_btn = ft.OutlinedButton(
            "Rotate 0\u00b0", icon=ft.Icons.ROTATE_RIGHT, on_click=rotate_pages,
            width=220,
        )

        def save(_):
            self.settings.ocr_enabled = bool(ocr_toggle.value)
            self.settings.default_filter = filter_dd.value or "magic"
            self.settings.save()
            dlg.open = False
            self.page.update()
            self._save_scan(
                name=name_field.value or "scan.pdf",
                filter_name=filter_dd.value or "magic",
                process=bool(process_toggle.value),
                as_pdf=bool(as_pdf.value),
                rotate=rotation["deg"],
            )

        def add_more(_):
            dlg.open = False
            self.page.update()
            self.scan_picker.pick_files(
                allow_multiple=True, file_type=ft.FilePickerFileType.IMAGE,
                allowed_extensions=["jpg", "jpeg", "png", "webp"],
            )

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("Review scan"),
            content=ft.Container(
                ft.Column([
                    page_count,
                    name_field,
                    ft.Row([filter_dd]),
                    rotate_btn,
                    process_toggle,
                    as_pdf,
                    ocr_toggle,
                    ft.Text(
                        "Pages are cleaned on this device and stored encrypted. "
                        if PROCESSING_SUPPORTED else
                        "Install the [scan] extra for image cleanup; storing originals as-is.",
                        size=11, color=ft.Colors.GREY_600, width=360),
                ], tight=True, spacing=12, width=380),
                width=400,
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
                   rotate: int = 0):
        try:
            pages = [CapturedPage(path=p, content_type=_guess_ct(p), source="camera")
                     for p in self._pending_pages]
            result = CaptureResult(pages=pages)
            doc = self.capture_svc.store_result(
                result,
                name=name,
                process=process,
                options=ProcessOptions(filter=filter_name, rotate=rotate),
                as_pdf=as_pdf,
                ocr=self._ocr_enabled(),
                source="camera",
            )
            self.snack(f"Encrypted: {doc.name}")
        except Exception as ex:
            self.snack(f"Could not save scan: {ex}", error=True)
        finally:
            self._pending_pages = []
            self.show_documents()

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
        def confirm(_):
            self.docs.delete(rid)
            dlg.open = False
            self.page.update()
            self.show_documents()
        dlg = ft.AlertDialog(
            title=ft.Text("Delete document?"),
            content=ft.Text("This removes the local encrypted copy. "
                            "Backed-up copies in Drive must be removed separately."),
            actions=[ft.TextButton("Cancel", on_click=lambda e: self._close_dlg(dlg)),
                     ft.FilledButton("Delete", on_click=confirm)],
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

    def backup_now(self, _=None):
        try:
            be = self._pick_backend()
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
