#!/usr/bin/env python3
"""
One-time credential setup for Fantasy Baseball Recap.

Stores all secrets in macOS Keychain so they are:
  - Encrypted at rest (AES-256, protected by your login password / Touch ID)
  - Never written to disk as plaintext
  - Never synced to iCloud or any cloud storage

Run once to store your keys:
    python setup_keys.py

Re-run any time you need to rotate or update a credential.
To wipe all stored keys and start over:
    python setup_keys.py --clear
"""

from __future__ import annotations

import argparse
import getpass
import sys

try:
    import keyring
except ImportError:
    print(
        "Error: 'keyring' is not installed.\n"
        "Run:  pip install keyring",
        file=sys.stderr,
    )
    sys.exit(1)

from credentials import KEYCHAIN_SERVICE, set_secret, get_secret, delete_secret, delete_oauth_token


# ---------------------------------------------------------------------------
# Field definitions
# ---------------------------------------------------------------------------

FIELDS = [
    {
        "key":       "YAHOO_CLIENT_ID",
        "label":     "Yahoo Client ID (Consumer Key)",
        "help":      "https://developer.yahoo.com/apps/  →  your app  →  Client ID",
        "sensitive": False,
        "required":  True,
    },
    {
        "key":       "YAHOO_CLIENT_SECRET",
        "label":     "Yahoo Client Secret (Consumer Secret)",
        "help":      "https://developer.yahoo.com/apps/  →  your app  →  Client Secret",
        "sensitive": True,
        "required":  True,
    },
    {
        "key":       "YAHOO_LEAGUE_KEY",
        "label":     "Yahoo League Key",
        "help":      "Format: {game_key}.l.{league_id}  e.g.  458.l.123456\n"
                     "  Find your league ID in the URL:\n"
                     "  baseball.fantasysports.yahoo.com/b1/123456  →  league ID is 123456\n"
                     "  MLB 2025 game key is typically 458",
        "sensitive": False,
        "required":  True,
    },
    {
        "key":       "ANTHROPIC_API_KEY",
        "label":     "Anthropic API Key",
        "help":      "https://console.anthropic.com/  →  API Keys  →  Create Key",
        "sensitive": True,
        "required":  True,
    },
    {
        "key":       "DISCORD_WEBHOOK_URL",
        "label":     "Discord Webhook URL  (optional — skip if testing locally)",
        "help":      "Discord  →  Server Settings  →  Integrations  →  Webhooks  →  New Webhook",
        "sensitive": False,
        "required":  False,
    },
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mask(value: str, sensitive: bool) -> str:
    if not sensitive:
        return value
    if len(value) <= 8:
        return "***"
    return value[:4] + "…" + value[-4:]


def prompt_field(field: dict) -> str | None:
    """Prompt for a single field; returns the new value or None to skip."""
    existing = get_secret(field["key"])

    print(f"\n{'─' * 56}")
    print(f"  {field['label']}")
    for line in field["help"].splitlines():
        print(f"  {line}")

    if existing:
        print(f"  Current value: {_mask(existing, field['sensitive'])}")
        keep_prompt = "  New value (press Enter to keep current): "
    else:
        keep_prompt = "  Value: "

    if field["sensitive"]:
        value = getpass.getpass(keep_prompt)
    else:
        value = input(keep_prompt).strip()

    if not value:
        if existing:
            print("  ✓ Keeping existing value.")
            return existing
        if not field["required"]:
            print("  – Skipped (optional).")
            return None
        print("  ⚠  This field is required — skipping for now. Re-run setup to add it.")
        return None

    return value


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def clear_all() -> None:
    print(f"\nRemoving all credentials from Keychain service '{KEYCHAIN_SERVICE}'...")
    for field in FIELDS:
        delete_secret(field["key"])
        print(f"  Deleted: {field['key']}")
    delete_oauth_token()
    print("  Deleted: oauth_token  (Yahoo OAuth token)")
    print("\nAll credentials cleared.  Run  python setup_keys.py  to re-enter them.")


def run_setup() -> None:
    print("=" * 60)
    print("  Fantasy Baseball Recap — Keychain Setup")
    print("=" * 60)
    print(f"\nSecrets are stored in macOS Keychain under service '{KEYCHAIN_SERVICE}'.")
    print("They are encrypted at rest and never written to disk as plaintext.\n")

    saved, skipped = [], []

    for field in FIELDS:
        value = prompt_field(field)
        if value is None:
            skipped.append(field["key"])
            continue
        set_secret(field["key"], value)
        print(f"  ✓ Saved to Keychain: {field['key']}")
        saved.append(field["key"])

    print("\n" + "=" * 60)
    if saved:
        print(f"Saved:   {', '.join(saved)}")
    if skipped:
        print(f"Skipped: {', '.join(skipped)}")

    print()
    if skipped and any(f["key"] in skipped and f["required"] for f in FIELDS):
        print("⚠  Some required fields were skipped.  Re-run setup before running main.py.")
    else:
        print("Setup complete!")
        print()
        print("Next steps:")
        print("  1.  python main.py --print-data   # verify Yahoo API access")
        print("       (your browser will open for Yahoo authorization on first run)")
        print("  2.  python main.py --dry-run      # generate a recap locally")
    print("=" * 60)


def main() -> None:
    parser = argparse.ArgumentParser(description="Store Fantasy Recap credentials in macOS Keychain.")
    parser.add_argument("--clear", action="store_true",
                        help="Remove ALL stored credentials from Keychain and exit.")
    args = parser.parse_args()

    if args.clear:
        confirm = input(f"Remove all credentials from Keychain service '{KEYCHAIN_SERVICE}'? [y/N] ").strip().lower()
        if confirm == "y":
            clear_all()
        else:
            print("Aborted.")
        return

    run_setup()


if __name__ == "__main__":
    main()
