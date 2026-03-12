"""
Yahoo OAuth 2.0 authentication for Fantasy Sports API.

FIRST-TIME SETUP:
1. Go to https://developer.yahoo.com/apps/
2. Click "Create an App"
3. Set Redirect URI to "https://localhost"
4. Select "Fantasy Sports" under API Permissions -> Read
5. Run  python setup_keys.py  to store your credentials in macOS Keychain
"""

import json
import time
import webbrowser
from pathlib import Path
from urllib.parse import urlencode

import requests
from requests.auth import HTTPBasicAuth

import credentials

# File-based fallback for systems where keyring is unavailable.
_CONFIG_DIR = Path.home() / ".config" / "fantasy_recap"
_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
_TOKEN_FILE_FALLBACK = _CONFIG_DIR / "oauth_token.json"

YAHOO_AUTH_URL  = "https://api.login.yahoo.com/oauth2/request_auth"
YAHOO_TOKEN_URL = "https://api.login.yahoo.com/oauth2/get_token"
REDIRECT_URI    = "https://localhost"


class YahooOAuth:
    """Manages Yahoo OAuth 2.0 tokens with automatic refresh."""

    def __init__(self, client_id: str, client_secret: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self._token: dict | None = None
        self._load_token()

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def get_session(self) -> requests.Session:
        """Return a requests.Session with a valid Authorization header."""
        self._ensure_valid_token()
        session = requests.Session()
        session.headers.update(
            {"Authorization": f"Bearer {self._token['access_token']}"}
        )
        return session

    # ------------------------------------------------------------------
    # Token lifecycle
    # ------------------------------------------------------------------

    def _ensure_valid_token(self):
        if self._token is None:
            self._do_authorization_code_flow()
        elif self._token_expires_soon():
            self._refresh_token()

    def _token_expires_soon(self) -> bool:
        # Refresh if less than 5 minutes remain
        expires_at = self._token.get("expires_at", 0)
        return time.time() >= (expires_at - 300)

    def _do_authorization_code_flow(self):
        """Interactive first-time authorization via the browser."""
        params = {
            "client_id": self.client_id,
            "redirect_uri": REDIRECT_URI,
            "response_type": "code",
        }
        auth_url = f"{YAHOO_AUTH_URL}?{urlencode(params)}"

        print("\n" + "=" * 60)
        print("YAHOO AUTHORIZATION REQUIRED")
        print("=" * 60)
        print("Opening your browser to authorize this app...")
        print("If it doesn't open automatically, visit:\n")
        print(f"  {auth_url}\n")
        webbrowser.open(auth_url)

        print("After you click Agree, your browser will show a")
        print("'connection refused' page — that's expected.")
        print("Look at the URL bar and copy the value after 'code='")
        print("Example: https://localhost?code=XXXXXXX  →  copy XXXXXXX\n")
        code = input("Paste the code here: ").strip()
        # Handle case where user accidentally pastes the full URL
        if "code=" in code:
            code = code.split("code=")[-1].split("&")[0]
        self._exchange_code_for_token(code)

    def _exchange_code_for_token(self, code: str):
        resp = requests.post(
            YAHOO_TOKEN_URL,
            auth=HTTPBasicAuth(self.client_id, self.client_secret),
            data={
                "grant_type": "authorization_code",
                "redirect_uri": REDIRECT_URI,
                "code": code,
            },
        )
        resp.raise_for_status()
        token = resp.json()
        token["expires_at"] = time.time() + token["expires_in"]
        self._token = token
        self._save_token()
        print("Authorization successful! Tokens saved.\n")

    def _refresh_token(self):
        print("Refreshing Yahoo access token...")
        resp = requests.post(
            YAHOO_TOKEN_URL,
            auth=HTTPBasicAuth(self.client_id, self.client_secret),
            data={
                "grant_type": "refresh_token",
                "redirect_uri": "oob",
                "refresh_token": self._token["refresh_token"],
            },
        )
        resp.raise_for_status()
        token = resp.json()
        token["expires_at"] = time.time() + token["expires_in"]
        # Yahoo doesn't always return a new refresh token — keep the old one
        token.setdefault("refresh_token", self._token["refresh_token"])
        self._token = token
        self._save_token()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load_token(self):
        # Prefer Keychain; fall back to the legacy file for one-time migration.
        token = credentials.get_oauth_token()
        if token:
            self._token = token
            return
        if _TOKEN_FILE_FALLBACK.exists():
            with open(_TOKEN_FILE_FALLBACK) as f:
                self._token = json.load(f)

    def _save_token(self):
        # Always write to Keychain (encrypted).
        credentials.set_oauth_token(self._token)
        # If keyring is unavailable, fall back to the protected file.
        if credentials._keyring() is None:
            with open(_TOKEN_FILE_FALLBACK, "w") as f:
                json.dump(self._token, f, indent=2)
            _TOKEN_FILE_FALLBACK.chmod(0o600)


def setup_oauth() -> YahooOAuth:
    """Load credentials from Keychain (or .env fallback) and return a YahooOAuth instance."""
    client_id     = credentials.get_secret("YAHOO_CLIENT_ID")
    client_secret = credentials.get_secret("YAHOO_CLIENT_SECRET")

    if not client_id or not client_secret:
        raise EnvironmentError(
            "YAHOO_CLIENT_ID and YAHOO_CLIENT_SECRET are not set.\n"
            "Run  python setup_keys.py  to store them in macOS Keychain.\n"
            "Get them at: https://developer.yahoo.com/apps/"
        )

    return YahooOAuth(client_id, client_secret)
