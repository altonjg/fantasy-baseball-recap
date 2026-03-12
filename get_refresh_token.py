"""
One-time helper: print the stored Yahoo refresh token from macOS Keychain.

Run this LOCALLY (after you've already authenticated via main.py at least once):
    python get_refresh_token.py

Copy the printed refresh token and add it as a GitHub Actions secret named
YAHOO_REFRESH_TOKEN in your repo settings:
    Settings → Secrets and variables → Actions → New repository secret

You should only need to do this once. The CI runner refreshes the token
automatically, and Yahoo access tokens last 3600 seconds.

If your refresh token ever expires (rare; Yahoo tokens are long-lived),
re-run main.py locally to re-authorize and then run this script again.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import credentials


def main() -> None:
    token = credentials.get_oauth_token()

    if not token:
        # Fall back to file-based storage
        fallback = Path.home() / ".config" / "fantasy_recap" / "oauth_token.json"
        if fallback.exists():
            with open(fallback) as f:
                token = json.load(f)

    if not token:
        print(
            "No stored OAuth token found.\n"
            "Run  python main.py --dry-run  first to authorize and store the token.",
            file=sys.stderr,
        )
        sys.exit(1)

    refresh_token = token.get("refresh_token", "")
    if not refresh_token:
        print("Token found but has no refresh_token field.", file=sys.stderr)
        sys.exit(1)

    print("=" * 60)
    print("YAHOO_REFRESH_TOKEN (copy this into GitHub Actions secrets):")
    print("=" * 60)
    print(refresh_token)
    print("=" * 60)
    print("\nAdd it at: GitHub repo → Settings → Secrets → New repository secret")
    print("Name:  YAHOO_REFRESH_TOKEN")
    print("Value: (the token printed above)")


if __name__ == "__main__":
    main()
