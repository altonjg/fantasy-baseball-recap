"""
CI-friendly Yahoo OAuth — no browser, no macOS Keychain.

Reads credentials from environment variables set as GitHub Actions secrets:
    YAHOO_CLIENT_ID
    YAHOO_CLIENT_SECRET
    YAHOO_REFRESH_TOKEN   ← obtained once via get_refresh_token.py on your local machine

Usage:
    from ci_auth import setup_ci_oauth
    oauth = setup_ci_oauth()
    session = oauth.get_session()
"""

from __future__ import annotations

import os
import time

import requests
from requests.auth import HTTPBasicAuth

YAHOO_TOKEN_URL = "https://api.login.yahoo.com/oauth2/get_token"


class CIOAuth:
    """
    Thin OAuth client for CI environments.
    Uses a stored refresh token to obtain access tokens without any browser interaction.
    """

    def __init__(self, client_id: str, client_secret: str, refresh_token: str):
        self.client_id     = client_id
        self.client_secret = client_secret
        self._refresh_token = refresh_token
        self._access_token: str | None = None
        self._expires_at: float = 0.0

    # ------------------------------------------------------------------
    # Public interface (compatible with YahooOAuth used in main.py)
    # ------------------------------------------------------------------

    def get_session(self) -> requests.Session:
        """Return a requests.Session with a valid Bearer token."""
        self._ensure_valid_token()
        session = requests.Session()
        session.headers.update({"Authorization": f"Bearer {self._access_token}"})
        return session

    # ------------------------------------------------------------------
    # Token lifecycle
    # ------------------------------------------------------------------

    def _ensure_valid_token(self) -> None:
        if self._access_token is None or time.time() >= (self._expires_at - 300):
            self._refresh()

    def _refresh(self) -> None:
        resp = requests.post(
            YAHOO_TOKEN_URL,
            auth=HTTPBasicAuth(self.client_id, self.client_secret),
            data={
                "grant_type":   "refresh_token",
                "redirect_uri": "oob",
                "refresh_token": self._refresh_token,
            },
            timeout=30,
        )
        resp.raise_for_status()
        token = resp.json()
        self._access_token  = token["access_token"]
        self._expires_at    = time.time() + token.get("expires_in", 3600)
        # Yahoo sometimes rotates the refresh token — keep the latest one
        new_rt = token.get("refresh_token")
        if new_rt:
            self._refresh_token = new_rt
            # Print for GitHub Actions to capture and update the secret if needed
            print(f"[ci_auth] Refresh token updated. New value: {new_rt}")


def setup_ci_oauth() -> CIOAuth:
    """Read credentials from env vars and return a CIOAuth instance."""
    client_id     = os.environ.get("YAHOO_CLIENT_ID", "")
    client_secret = os.environ.get("YAHOO_CLIENT_SECRET", "")
    refresh_token = os.environ.get("YAHOO_REFRESH_TOKEN", "")

    missing = [k for k, v in [
        ("YAHOO_CLIENT_ID", client_id),
        ("YAHOO_CLIENT_SECRET", client_secret),
        ("YAHOO_REFRESH_TOKEN", refresh_token),
    ] if not v]

    if missing:
        raise EnvironmentError(
            f"Missing required environment variables: {', '.join(missing)}\n"
            "Set them as GitHub Actions secrets (or local env vars for testing).\n"
            "Run  python get_refresh_token.py  once on your local machine to\n"
            "obtain the initial YAHOO_REFRESH_TOKEN value."
        )

    return CIOAuth(client_id, client_secret, refresh_token)
