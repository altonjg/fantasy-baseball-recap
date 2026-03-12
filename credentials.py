"""
Credential access layer: macOS Keychain → .env fallback.

All secrets are stored under the Keychain service "fantasy_recap".
The get_secret() function checks Keychain first, then falls back to
os.environ (populated by load_dotenv in main.py), so existing .env
setups keep working without any changes.

The OAuth token is stored as a JSON blob in the same Keychain service
so the live Yahoo token is never written to disk as plaintext.
"""

from __future__ import annotations

import json
import logging
import os

logger = logging.getLogger(__name__)

KEYCHAIN_SERVICE = "fantasy_recap"
_OAUTH_TOKEN_KEY  = "oauth_token"


# ---------------------------------------------------------------------------
# Internal: lazy keyring import
# ---------------------------------------------------------------------------

def _keyring():
    """Return the keyring module, or None if it isn't installed."""
    try:
        import keyring
        return keyring
    except ImportError:
        return None


# ---------------------------------------------------------------------------
# Generic secret helpers
# ---------------------------------------------------------------------------

def get_secret(key: str) -> str | None:
    """
    Return the value for *key*, checking in order:
      1. macOS Keychain (via keyring library)
      2. os.environ  (set by load_dotenv or the shell — .env fallback)
    Returns None if not found in either location.
    """
    kr = _keyring()
    if kr is not None:
        try:
            val = kr.get_password(KEYCHAIN_SERVICE, key)
            if val:
                return val
        except Exception as exc:
            logger.debug("Keychain read failed for %s: %s", key, exc)
    return os.environ.get(key)


def set_secret(key: str, value: str) -> None:
    """Store *value* under *key* in the Keychain."""
    import keyring
    keyring.set_password(KEYCHAIN_SERVICE, key, value)


def delete_secret(key: str) -> None:
    """Remove *key* from the Keychain (silently ignores missing keys)."""
    import keyring
    try:
        keyring.delete_password(KEYCHAIN_SERVICE, key)
    except keyring.errors.PasswordDeleteError:
        pass


# ---------------------------------------------------------------------------
# OAuth token helpers  (stored as a JSON string under "oauth_token")
# ---------------------------------------------------------------------------

def get_oauth_token() -> dict | None:
    """Return the stored Yahoo OAuth token dict, or None."""
    raw = get_secret(_OAUTH_TOKEN_KEY)
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("Stored OAuth token is not valid JSON — ignoring.")
        return None


def set_oauth_token(token: dict) -> None:
    """Persist the Yahoo OAuth token dict to Keychain."""
    set_secret(_OAUTH_TOKEN_KEY, json.dumps(token))


def delete_oauth_token() -> None:
    """Remove the stored OAuth token (forces re-authorization next run)."""
    delete_secret(_OAUTH_TOKEN_KEY)
