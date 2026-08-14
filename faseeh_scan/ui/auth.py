"""
Google sign-in, wired through Flet's built-in OAuth.

This single code path works on desktop, web, and Android:
  * desktop/web -> Flet opens a browser tab and catches the redirect on a
    local loopback URL;
  * Android     -> Flet opens an in-app web view and catches the
    `flet://api/oauth/redirect` custom-scheme callback.

After `page.login()` succeeds, `page.auth.token.access_token` is a valid
OAuth2 bearer token with the `drive.file` scope, which we hand to
`GoogleDriveBackend.from_access_token(...)`.
"""

from __future__ import annotations

from flet.auth.providers import GoogleOAuthProvider

from ..config import settings
from ..backends import GoogleDriveBackend, GDriveNotConfigured

# drive.file: access only to files/folders this app creates/opens.
DRIVE_SCOPE = "https://www.googleapis.com/auth/drive.file"


def is_google_configured() -> bool:
    return settings.google_oauth_configured


def build_provider() -> GoogleOAuthProvider:
    if not is_google_configured():
        raise GDriveNotConfigured(
            "Google OAuth is not configured. Set GOOGLE_CLIENT_ID and "
            "GOOGLE_CLIENT_SECRET in .env (see .env.example)."
        )
    return GoogleOAuthProvider(
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        redirect_url=settings.oauth_redirect_url,
    )


def login(page):
    """Start the Google OAuth flow. Raises on configuration errors only;
    the result arrives in page.on_login."""
    provider = build_provider()
    page.login(
        provider,
        scope=[DRIVE_SCOPE],
        fetch_user=True,
    )


def build_drive_backend(page) -> GoogleDriveBackend:
    """Build a Drive backend from the current Flet auth session.

    `token_refresher` reads page.auth.token.access_token each time, which is a
    property that auto-refreshes expired tokens — so long-lived uploads don't
    die when the first token expires.
    """
    if page.auth is None or page.auth.token is None:
        raise GDriveNotConfigured("Not signed in to Google.")

    def _access_token() -> str:
        return page.auth.token.access_token

    return GoogleDriveBackend.from_access_token(
        access_token=_access_token(),
        token_refresher=_access_token,
    )


def signed_in_email(page) -> str | None:
    try:
        if page.auth and page.auth.user:
            return page.auth.user.get("email")
    except Exception:
        pass
    return None
