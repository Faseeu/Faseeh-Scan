"""Google Drive backend (optional).

Stores the encrypted vault inside a dedicated folder in the USER'S OWN Google
Drive, using the `drive.file` scope — the narrowest scope, which only lets the
app see files/folders it created itself. Google never receives plaintext; all
uploads are AES-256-GCM ciphertext.

Two ways to authenticate:

1. **Flet OAuth (desktop, web, AND Android — recommended).** The UI calls
   `page.login(GoogleOAuthProvider(...))`; Flet performs the Authorization Code
   flow with a platform-appropriate redirect (`flet://api/oauth/redirect` on
   Android) and hands back an access token. We build the Drive service directly
   from that token via `GoogleDriveBackend.from_access_token(...)`.

2. **Desktop installed-app flow (fallback / headless).** Uses
   `google-auth-oauthlib`'s local-server flow with a `client_secret.json`. This
   opens a browser and works on a laptop but is NOT suitable for Android.

Both paths produce the same authenticated Drive service.
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Callable, Optional

from .base import StorageBackend

FOLDER_NAME = "Medical Reports Backup"
TOKEN_FILE = Path("credentials/gdrive_token.json")
CLIENT_SECRET_FILE = Path("credentials/client_secret.json")

# drive.file: see and manage only files/folders this app creates/opens in Drive.
DRIVE_FILE_SCOPE = "https://www.googleapis.com/auth/drive.file"
# Flet's GoogleOAuthProvider already requests profile/email; add Drive scope.
SCOPES = [DRIVE_FILE_SCOPE]


class GDriveNotConfigured(RuntimeError):
    pass


class GoogleDriveBackend(StorageBackend):
    id = "gdrive"
    display_name = "My Google Drive"

    def __init__(
        self,
        access_token: Optional[str] = None,
        token_refresher: Optional[Callable[[], str]] = None,
        client_secret: str | Path = CLIENT_SECRET_FILE,
        token_file: str | Path = TOKEN_FILE,
    ):
        """
        :param access_token: OAuth2 bearer token from Flet's page.auth.token
                             (preferred; works on Android/web/desktop).
        :param token_refresher: zero-arg callable returning a fresh access token,
                                used when the API reports 401. In Flet this is
                                typically `lambda: page.auth.token.access_token`.
        """
        self.access_token = access_token
        self.token_refresher = token_refresher
        self.client_secret = Path(client_secret)
        self.token_file = Path(token_file)
        self._service = None
        self._folder_id: str | None = None

    # ---- construction ----------------------------------------------------

    @classmethod
    def from_access_token(
        cls, access_token: str, token_refresher: Optional[Callable[[], str]] = None
    ) -> "GoogleDriveBackend":
        be = cls(access_token=access_token, token_refresher=token_refresher)
        be._build_service()
        return be

    def _build_service(self) -> None:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build

        if not self.access_token:
            raise GDriveNotConfigured("No access token available.")
        # A bare access token is enough for Drive calls. refresh_token is
        # optional because Flet manages token refresh itself.
        creds = Credentials(token=self.access_token, scopes=SCOPES)
        self._service = build("drive", "v3", credentials=creds, cache_discovery=False)

    # ---- auth ------------------------------------------------------------

    def is_configured(self) -> bool:
        return bool(self.access_token) or self.client_secret.exists() or self.token_file.exists()

    def authenticate(self, parent_window=None) -> None:
        """Authenticate. Prefers an injected access token; otherwise falls back
        to the desktop local-server OAuth flow (requires client_secret.json)."""
        if self.access_token:
            if self._service is None:
                self._build_service()
            self._folder_id = self._ensure_folder()
            return
        self._authenticate_desktop()

    def _authenticate_desktop(self) -> None:
        try:
            from google.auth.transport.requests import Request
            from google.oauth2.credentials import Credentials
            from google_auth_oauthlib.flow import InstalledAppFlow
        except ImportError as e:  # pragma: no cover
            raise GDriveNotConfigured(
                "Google dependencies missing. Install with: pip install -e .[gdrive]"
            ) from e

        creds = None
        if self.token_file.exists():
            creds = Credentials.from_authorized_user_file(str(self.token_file), SCOPES)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not self.client_secret.exists():
                    raise GDriveNotConfigured(
                        f"Missing {self.client_secret}. Download an OAuth Desktop "
                        "client from Google Cloud Console and place it there, "
                        "or sign in with Google inside the app."
                    )
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(self.client_secret), SCOPES
                )
                creds = flow.run_local_server(port=0)
            self.token_file.parent.mkdir(parents=True, exist_ok=True)
            self.token_file.write_text(creds.to_json())

        from googleapiclient.discovery import build
        self._service = build("drive", "v3", credentials=creds, cache_discovery=False)
        self._folder_id = self._ensure_folder()

    def _refresh_token_if_needed(self) -> None:
        """Called on 401 to get a fresh token via the Flet-provided refresher."""
        if self.token_refresher:
            self.access_token = self.token_refresher()
            self._build_service()
            self._folder_id = self._ensure_folder()

    # ---- folder helpers --------------------------------------------------

    def _ensure_folder(self) -> str:
        q = (
            f"name='{FOLDER_NAME}' and mimeType='application/vnd.google-apps.folder' "
            "and trashed=false"
        )
        resp = self._service.files().list(q=q, spaces="drive", fields="files(id)").execute()
        files = resp.get("files", [])
        if files:
            return files[0]["id"]
        folder = self._service.files().create(
            body={"name": FOLDER_NAME, "mimeType": "application/vnd.google-apps.folder"},
            fields="id",
        ).execute()
        return folder["id"]

    def _find_child(self, relative_path: str) -> str | None:
        parent = self._folder_id
        for part in Path(relative_path).parts:
            q = f"name='{part}' and '{parent}' in parents and trashed=false"
            resp = self._service.files().list(q=q, fields="files(id,mimeType)").execute()
            files = resp.get("files", [])
            if not files:
                return None
            parent = files[0]["id"]
        return parent

    def _ensure_parent(self, relative_path: str) -> str:
        parent = self._folder_id
        for part in Path(relative_path).parts[:-1]:
            q = (
                f"name='{part}' and '{parent}' in parents and "
                "mimeType='application/vnd.google-apps.folder' and trashed=false"
            )
            resp = self._service.files().list(q=q, fields="files(id)").execute()
            files = resp.get("files", [])
            if files:
                parent = files[0]["id"]
            else:
                f = self._service.files().create(
                    body={
                        "name": part,
                        "mimeType": "application/vnd.google-apps.folder",
                        "parents": [parent],
                    },
                    fields="id",
                ).execute()
                parent = f["id"]
        return parent

    def _run(self, fn):
        """Run a Drive API call, refreshing the token once on 401."""
        try:
            return fn()
        except Exception as e:
            status = getattr(getattr(e, "resp", None), "status", None)
            if status == 401 and self.token_refresher:
                self._refresh_token_if_needed()
                return fn()
            raise

    # ---- operations ------------------------------------------------------

    def upload(self, relative_path: str, local_path: Path) -> str:
        if self._service is None:
            self.authenticate()
        from googleapiclient.http import MediaFileUpload

        def _do():
            parent = self._ensure_parent(relative_path)
            name = Path(relative_path).name
            existing = self._find_child(relative_path)
            media = MediaFileUpload(str(local_path), resumable=False)
            if existing:
                f = self._service.files().update(
                    fileId=existing, media_body=media, fields="id"
                ).execute()
                return f["id"]
            f = self._service.files().create(
                body={"name": name, "parents": [parent]},
                media_body=media,
                fields="id",
            ).execute()
            return f["id"]

        return self._run(_do)

    def download(self, relative_path: str, local_path: Path) -> None:
        if self._service is None:
            self.authenticate()

        def _do():
            file_id = self._find_child(relative_path)
            if not file_id:
                raise FileNotFoundError(f"{relative_path} not found in Drive")
            local_path.parent.mkdir(parents=True, exist_ok=True)
            request = self._service.files().get_media(fileId=file_id)
            from googleapiclient.http import MediaIoBaseDownload
            fh = io.FileIO(str(local_path), "wb")
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()
            fh.close()

        self._run(_do)

    def list_remote(self) -> list[str]:
        if self._service is None:
            self.authenticate()
        results: list[str] = []

        def _do():
            self._walk(self._folder_id, "", results)

        self._run(_do)
        return results

    def _walk(self, folder_id: str, prefix: str, out: list[str]) -> None:
        q = f"'{folder_id}' in parents and trashed=false"
        page_token = None
        while True:
            resp = self._service.files().list(
                q=q,
                fields="nextPageToken, files(id,name,mimeType)",
                pageToken=page_token,
            ).execute()
            for f in resp.get("files", []):
                rel = f"{prefix}{f['name']}"
                if f["mimeType"] == "application/vnd.google-apps.folder":
                    self._walk(f["id"], rel + "/", out)
                else:
                    out.append(rel)
            page_token = resp.get("nextPageToken")
            if not page_token:
                break
