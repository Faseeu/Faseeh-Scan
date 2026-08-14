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
from ..features.share_intent import ShareIntentService, IncomingFile, mime_to_content_type
from ..features.biometrics import get_backend as get_biometric_backend
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
    return base / "FaseehScan" / "vault"


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
        self._selected: set[str] = set()
        self._selection_mode = False
        # Pending pages captured via the file picker (list of Paths).
        self._pending_pages: list[Path] = []
        self._images_to_pdf_mode = False
        self.share = ShareIntentService()
        self.share.on_incoming(self._on_incoming_share)
        self.file_picker = ft.FilePicker(on_result=self.on_files_picked)
        # A second picker that feeds the scan review flow.
        self.scan_picker = ft.FilePicker(on_result=self._on_scan_picked)
        self.page.overlay.append(self.file_picker)
        self.page.overlay.append(self.scan_picker)
        self.page.title = APP_NAME
        self.page.theme = ft.Theme(color_scheme_seed=PRIMARY, use_material3=True)
        self.page.dark_theme = ft.Theme(color_scheme_seed=PRIMARY, use_material3=True)
        self.page.theme_mode = self._theme_mode()
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
        # Home-screen quick action ("Scan document") — best-effort, mobile only.
        try:
            from ..features.quick_actions import attach as attach_quick_actions
            attach_quick_actions(self.page, on_scan=self.start_scan)
        except Exception:
            pass

    def _theme_mode(self):
        return {
            "light": ft.ThemeMode.LIGHT,
            "dark": ft.ThemeMode.DARK,
        }.get(self.settings.dark_mode, ft.ThemeMode.SYSTEM)

    def _haptic(self, kind: str = "light"):
        """Best-effort haptic feedback; never blocks UI."""
        if not self.settings.haptics:
            return
        try:
            if kind in ("success", "heavy"):
                ft.HapticFeedback.heavy_impact()
            elif kind == "medium":
                ft.HapticFeedback.medium_impact()
            else:
                ft.HapticFeedback.light_impact()
        except Exception:
            pass

    # ---- routing ---------------------------------------------------------

    def route(self):
        if not self.vault_svc.exists:
            self.show_welcome()
        elif not self.vault_svc.is_unlocked:
            self.show_lock()
        else:
            self.show_documents()
            # Process any files shared from another app (now that we're unlocked).
            self._ingest_pending_shares()

    # ---- incoming shares / shortcuts ------------------------------------

    def _on_incoming_share(self, files: list[IncomingFile]):
        # If locked, they stay queued until unlock; otherwise ingest now.
        if self.vault_svc.is_unlocked:
            self._ingest_pending_shares()
        else:
            self.show_lock()

    def _ingest_pending_shares(self):
        if not self.vault_svc.is_unlocked:
            return
        items = [f for f in self.share.drain() if f.path]
        if not items:
            return
        added = 0
        for f in items:
            p = Path(f.path)
            try:
                if p.exists():
                    data = p.read_bytes()
                    ctype = mime_to_content_type(f.mime, f.path)
                    self.docs.add(data, p.name, ctype, source="share")
                    added += 1
            except Exception as ex:
                self.snack(f"Could not import {p.name}: {ex}", error=True)
        if added:
            self.snack(f"Imported {added} shared document(s), encrypted.")
            self._maybe_auto_backup()
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

        bio = get_biometric_backend(self.page)
        can_bio = (self.settings.biometric_unlock and bio.is_available())

        def _bio_unlock(_):
            if bio.authenticate("Unlock Faseeh Scan"):
                try:
                    # Biometrics confirms the user; the vault still requires
                    # the password/key. On mobile the local_auth extension
                    # gates access; we rely on the OS keystore-stored key.
                    self._unlock_with_biometric(bio)
                except Exception as ex:
                    self.snack(f"Biometric unlock failed: {ex}", error=True)

        controls = [
            ft.Icon(ft.Icons.LOCK, size=56, color=PRIMARY),
            ft.Text("Unlock your vault", size=22, weight=ft.FontWeight.BOLD),
            pw,
            ft.FilledButton("Unlock", on_click=_click, width=320),
        ]
        if can_bio:
            controls.append(ft.OutlinedButton(
                "Unlock with fingerprint / face",
                icon=ft.Icons.FINGERPRINT, on_click=_bio_unlock, width=320))

        self.page.views.clear()
        self.page.views.append(ft.View(
            "/unlock",
            [
                ft.Container(
                    ft.Column(controls,
                              horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=16),
                    alignment=ft.alignment.center, expand=True,
                )
            ],
            padding=0,
        ))
        self.page.update()

        # Auto-prompt biometrics on launch if enabled.
        if can_bio:
            _bio_unlock(None)

    def _unlock_with_biometric(self, bio):
        # The biometric extension does not hold the vault password itself.
        # For v1, biometric unlock is available when the user has opted in and
        # the device passes authentication; the OS key store integration that
        # stores a wrapped master key is part of the native extension. If that
        # wrapped key exists, the extension returns it via authenticate().
        result = getattr(bio, "last_result", None)
        if not result:
            self.snack("Biometric unlock is not fully enrolled. Use your password.", error=True)
            return
        self.vault._master_key = bytes.fromhex(result) if isinstance(result, str) else result
        self.vault._load_meta()
        self.show_documents()

    def _do_unlock(self, pw):
        try:
            self.vault_svc.unlock(pw.value or "")
            self._haptic("success")
            self.show_documents()
        except crypto.WrongPasswordError:
            self._haptic("heavy")
            self.snack("Incorrect password.", error=True)
        except Exception as e:
            self._haptic("heavy")
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
            header = self._selection_bar() if self._selection_mode else ft.Row(
                [title], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)
            content = ft.Column([
                header,
                ft.Row([search_field]),
                ft.Text(count, color=ft.Colors.GREY_600),
                ft.ListView(rows, spacing=10, expand=True, padding=ft.padding.only(top=8)),
            ], expand=True)
        return content

    def _selection_bar(self):
        n = len(self._selected)
        return ft.Row([
            ft.IconButton(ft.Icons.CLOSE, tooltip="Cancel", on_click=self._cancel_select),
            ft.Text(f"{n} selected", weight=ft.FontWeight.W_600),
            ft.Container(expand=True),
            ft.IconButton(ft.Icons.PICTURE_AS_PDF, tooltip="Merge into PDF",
                          on_click=self._merge_selected),
            ft.IconButton(ft.Icons.IOS_SHARE, tooltip="Save copies",
                          on_click=self._export_selected),
            ft.IconButton(ft.Icons.DELETE_SWEEP, tooltip="Move to trash",
                          on_click=self._trash_selected),
        ])

    def _cancel_select(self, _=None):
        self._selected.clear()
        self._selection_mode = False
        self.show_documents()

    def _toggle_select(self, rid: str):
        self._selection_mode = True
        if rid in self._selected:
            self._selected.discard(rid)
        else:
            self._selected.add(rid)
        if not self._selected:
            self._selection_mode = False
        self.show_documents()

    def _trash_selected(self, _=None):
        for rid in list(self._selected):
            self.docs.trash(rid)
        self.snack(f"Moved {len(self._selected)} to trash.")
        self._selected.clear()
        self._selection_mode = False
        self._maybe_auto_backup()
        self.show_documents()

    def _export_selected(self, _=None):
        for rid in self._selected:
            self.save_document(rid)
        self._cancel_select()

    def _merge_selected(self, _=None):
        """Combine selected documents (PDFs/images) into a single PDF."""
        from ..features.pdf_tools import merge_pdfs
        parts = []
        for rid in self._selected:
            meta, data = self.docs.get(rid)
            if meta.content_type == "application/pdf":
                parts.append(data)
        if len(parts) < 2:
            self.snack("Select at least two PDFs to merge.", error=True)
            return
        merged = merge_pdfs(parts)
        name = f"merged {self._default_scan_name()}"
        self.docs.add(merged, name, "application/pdf", source="merge")
        self.snack(f"Created {name}")
        self._cancel_select()
        self._maybe_auto_backup()
        self.show_documents()

    def _on_search(self, e):
        self._search_query = e.control.value or ""
        self.show_documents()

    def _document_card(self, r):
        is_sel = r.id in self._selected
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

        actions = ft.Row([
            ft.IconButton(ft.Icons.HISTORY, tooltip="Version history",
                          visible=bool(r.versions),
                          on_click=lambda e, rid=r.id: self.show_history(rid)),
            ft.IconButton(ft.Icons.EDIT_NOTE, tooltip="Arrange pages",
                          visible=(r.content_type == "application/pdf"),
                          on_click=lambda e, rid=r.id: self.edit_pdf(rid)),
            ft.IconButton(ft.Icons.DOWNLOAD, tooltip="Decrypt & save",
                          on_click=lambda e, rid=r.id: self.save_document(rid)),
            ft.IconButton(ft.Icons.DELETE_OUTLINE, tooltip="Move to trash",
                          on_click=lambda e, rid=r.id: self.delete_document(rid)),
        ])

        card = ft.Card(
            ft.Container(
                ft.Row([
                    ft.Checkbox(value=is_sel, on_change=lambda e, rid=r.id: self._toggle_select(rid),
                                visible=self._selection_mode),
                    thumb,
                    ft.GestureDetector(
                        ft.Column([
                            ft.Row([ft.Text(r.name, weight=ft.FontWeight.W_600, size=15),
                                    badge, ocr_badge]),
                            ft.Text(f"{human_size(r.size)} · encrypted",
                                    size=12, color=ft.Colors.GREY_600),
                            ft.Text(r.note, size=11, color=ft.Colors.GREY_500) if r.note else ft.Container(),
                        ], spacing=4, expand=True),
                        on_long_press=lambda e, rid=r.id: self._toggle_select(rid),
                        expand=True,
                    ),
                    actions,
                ], alignment=ft.MainAxisAlignment.START),
                padding=14,
                bgcolor=ft.Colors.with_opacity(0.08, PRIMARY) if is_sel else None,
            ),
            elevation=1,
        )

        # Swipe right = save/export; swipe left = trash.
        return ft.Dismissible(
            key=f"doc_{r.id}",
            content=card,
            dismiss_direction=ft.DismissDirection.HORIZONTAL,
            background=ft.Container(
                ft.Row([ft.Icon(ft.Icons.DOWNLOAD, color=ft.Colors.WHITE),
                        ft.Text("Save", color=ft.Colors.WHITE)], spacing=8),
                padding=14, alignment=ft.alignment.center_left,
                bgcolor=ft.Colors.BLUE_400, border_radius=8),
            secondary_background=ft.Container(
                ft.Row([ft.Text("Trash", color=ft.Colors.WHITE),
                        ft.Icon(ft.Icons.DELETE, color=ft.Colors.WHITE)], spacing=8),
                padding=14, alignment=ft.alignment.center_right,
                bgcolor=ft.Colors.RED_400, border_radius=8),
            on_dismiss=lambda e, rid=r.id: self._on_swipe(e, rid),
            on_confirm_dismiss=lambda e, rid=r.id: self._confirm_swipe(e, rid),
        )

    def _on_swipe(self, e, rid):
        # Dismissible already removed the widget; act based on direction.
        if e.direction in (ft.DismissDirection.END_TO_START,):
            self.delete_document(rid)
        else:
            self.save_document(rid)

    def _confirm_swipe(self, e, rid):
        # Confirm destructive (left) swipes; export swipes proceed immediately.
        return e.direction == ft.DismissDirection.END_TO_START

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
            self._haptic("success"); self.snack(f"Scanned and encrypted: {doc.name}")
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

        def suggest_name(_):
            if not self.settings.ocr_enabled:
                self.snack("Enable OCR in Settings to suggest names.", error=True)
                return
            try:
                from ..features.naming import suggest_name
                from ..features.ocr import default as default_ocr
                from ..features.processing.pipeline import load_image, process_image
                engine = default_ocr()
                if engine is None or not pages:
                    return
                # OCR the first processed page to suggest a name.
                p, rot = pages[0]
                img = load_image(p)
                opts = ProcessOptions(filter=(filter_dd.value or "gray"), rotate=rot)
                import tempfile
                with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tf:
                    from ..features.processing.pipeline import save_image
                    save_image(process_image(img, opts), tf.name)
                    text = engine.extract(Path(tf.name).read_bytes(), "image/jpeg")
                suggestion = suggest_name(text, fallback=name_field.value or "scan")
                if suggestion and suggestion.lower().endswith(".pdf"):
                    suggestion = suggestion[:-4]
                name_field.value = f"{suggestion}.pdf"
                name_field.focus()
                self.snack("Name suggested from document text.")
                self.page.update()
            except Exception as ex:
                self.snack(f"Could not suggest name: {ex}", error=True)

        suggest_btn = ft.IconButton(ft.Icons.AUTO_FIX_HIGH, tooltip="Suggest name from text",
                                    on_click=suggest_name)

        def refresh():
            page_count.value = f"{len(pages)} page(s)"
            order_list.controls = [_page_row(i, path, rot)
                                   for i, (path, rot) in enumerate(pages)]
            self.page.update()

        def rotate_one(index):
            pages[index][1] = (pages[index][1] + 90) % 360
            refresh()

        def remove_one(index):
            del pages[index]
            refresh()

        def on_reorder(e: ft.OnReorderEvent):
            old, new = e.old_index, e.new_index
            if new > old:
                new -= 1
            pages.insert(new, pages.pop(old))
            refresh()

        def _page_row(i, path, rot):
            return ft.Container(
                key=f"scanpage_{i}",
                content=ft.Row([
                    ft.ReorderableDragHandle(ft.Icon(ft.Icons.DRAG_INDICATOR,
                                                     size=20, color=ft.Colors.GREY_500)),
                    ft.Text(str(i + 1), width=24, color=ft.Colors.GREY_700,
                            weight=ft.FontWeight.W_600),
                    ft.Icon(ft.Icons.IMAGE, size=18, color=ft.Colors.GREY_500),
                    ft.Text(path.name, expand=True, max_lines=1,
                            overflow=ft.TextOverflow.ELLIPSIS, size=13),
                    ft.Text(f"{rot}\u00b0", size=12, color=ft.Colors.GREY_600, width=34),
                    ft.IconButton(ft.Icons.ROTATE_RIGHT, icon_size=18,
                                  tooltip="Rotate page",
                                  on_click=lambda e, idx=i: rotate_one(idx)),
                    ft.IconButton(ft.Icons.DELETE_OUTLINE, icon_size=18,
                                  tooltip="Remove page",
                                  on_click=lambda e, idx=i: remove_one(idx)),
                ], spacing=2),
            )

        page_count = ft.Text(f"{len(pages)} page(s)", color=ft.Colors.GREY_700)
        order_list = ft.ReorderableListView(
            controls=[_page_row(i, p, r) for i, (p, r) in enumerate(pages)],
            on_reorder=on_reorder,
            height=220, spacing=2,
        )

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
                        order_list, height=220, width=540,
                        border=ft.border.all(1, ft.Colors.GREY_300), border_radius=8,
                        padding=8,
                    ),
                    ft.Row([name_field, suggest_btn]),
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
            self._haptic("success"); self.snack(f"Encrypted: {doc.name}")
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
            pdf_list.controls = [_pdf_row(pos, idx) for pos, idx in enumerate(order)]
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

        def on_reorder(e: ft.OnReorderEvent):
            old, new = e.old_index, e.new_index
            if new > old:
                new -= 1
            order.insert(new, order.pop(old))
            rebuild()

        def _pdf_row(pos, idx):
            return ft.Container(
                key=f"pdfpage_{pos}",
                content=ft.Row([
                    ft.ReorderableDragHandle(ft.Icon(ft.Icons.DRAG_INDICATOR,
                                                     size=20, color=ft.Colors.GREY_500)),
                    ft.Text(f"{pos+1}.", width=30, color=ft.Colors.GREY_700),
                    ft.Text(f"page {idx+1}", expand=True, size=13),
                    ft.Text(f"{rotations[idx]}\u00b0", width=40, size=12,
                            color=ft.Colors.GREY_600),
                    ft.IconButton(ft.Icons.ROTATE_RIGHT, icon_size=18,
                                  on_click=lambda e, i=idx: rotate(i)),
                    ft.IconButton(ft.Icons.CLOSE, icon_size=18,
                                  on_click=lambda e, i=idx: remove(i)),
                ], spacing=2),
            )

        def apply(_):
            from ..features.pdf_tools import rearrange_pdf
            new_bytes = rearrange_pdf(data, order,
                                      rotations={i: rotations[i] for i in order if rotations[i]})
            self.docs.replace_blob(rid, new_bytes, content_type="application/pdf")
            dlg.open = False
            self.page.update()
            self._haptic("medium"); self.snack("PDF updated.")
            self._maybe_auto_backup()
            self.show_documents()

        pdf_list = ft.ReorderableListView(
            controls=[_pdf_row(p, i) for p, i in enumerate(order)],
            on_reorder=on_reorder,
            height=300, spacing=2,
        )
        dlg = ft.AlertDialog(
            modal=True, title=ft.Text(f"Arrange — {meta.name}"),
            content=ft.Container(
                ft.Column([
                    ft.Text("Drag to reorder; rotate or remove pages.",
                            size=12, color=ft.Colors.GREY_600),
                    ft.Container(pdf_list, height=300, width=500,
                                 border=ft.border.all(1, ft.Colors.GREY_300),
                                 border_radius=8, padding=8),
                ], tight=True, spacing=10), width=540),
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
        haptics_switch = ft.Switch(
            label="Haptic feedback",
            value=self.settings.haptics, width=420)
        bio = get_biometric_backend(self.page)
        bio_available = bio.is_available()
        bio_switch = ft.Switch(
            label="Unlock with fingerprint / face",
            value=self.settings.biometric_unlock and bio_available,
            disabled=not bio_available, width=420)
        theme_dd = ft.Dropdown(
            label="Theme", value=self.settings.dark_mode, width=240, dense=True,
            options=[ft.dropdown.Option("system", label="System default"),
                     ft.dropdown.Option("light", label="Light"),
                     ft.dropdown.Option("dark", label="Dark")])
        filter_dd = ft.Dropdown(
            label="Default scan look", value=self.settings.default_filter, width=240, dense=True,
            options=[ft.dropdown.Option(k, label=l) for k, l in [
                ("magic", "Clean scan"), ("color", "Color"),
                ("gray", "Grayscale"), ("bw", "Black & white"),
                ("original", "Original")]])

        def save(_):
            self.settings.ocr_enabled = bool(ocr_switch.value)
            self.settings.wifi_only_backup = bool(wifi_switch.value)
            self.settings.haptics = bool(haptics_switch.value)
            self.settings.biometric_unlock = bool(bio_switch.value)
            self.settings.dark_mode = theme_dd.value or "system"
            self.settings.default_filter = filter_dd.value or "magic"
            self.settings.save()
            self.page.theme_mode = self._theme_mode()
            dlg.open = False
            self.page.update()
            self.snack("Settings saved.")
            self.show_documents()

        dlg = ft.AlertDialog(
            modal=True, title=ft.Text("Settings"),
            content=ft.Container(ft.Column([
                ft.Text("Appearance", weight=ft.FontWeight.W_600),
                theme_dd,
                ft.Text("Scanning", weight=ft.FontWeight.W_600),
                filter_dd, ocr_switch,
                ft.Divider(),
                ft.Text("Backup", weight=ft.FontWeight.W_600),
                wifi_switch,
                ft.Divider(),
                ft.Text("Feedback", weight=ft.FontWeight.W_600),
                haptics_switch,
                ft.Text("Security", weight=ft.FontWeight.W_600),
                bio_switch if bio_available else ft.Text(
                    "Biometric unlock requires a supported device.",
                    size=11, color=ft.Colors.GREY_600),
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
        self._haptic("light")

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

        return LocalBackend(Path.home() / "FaseehScan" / "drive-sync")

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
            self._haptic("success"); self.snack(f"Backup complete — {n} encrypted file(s) in {be.display_name}.")
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
