"""
Posts the weekly recap to a Discord channel via webhook.

Discord message limits:
  - Content field: 2,000 characters
  - Embed description: 4,096 characters
  - Multiple embeds per message: up to 10

Strategy: post header + first chunk as an embed, then spill overflow into
additional messages so nothing gets silently truncated.
"""

from __future__ import annotations

import requests

import credentials


DISCORD_EMBED_LIMIT = 4000   # leave a little buffer under 4096
DISCORD_CONTENT_LIMIT = 1900  # leave a little buffer under 2000


def _split_into_chunks(text: str, chunk_size: int) -> list[str]:
    """Split text on newlines so we don't cut mid-sentence."""
    if len(text) <= chunk_size:
        return [text]

    chunks: list[str] = []
    current = ""
    for line in text.splitlines(keepends=True):
        if len(current) + len(line) > chunk_size:
            if current:
                chunks.append(current.rstrip())
            current = line
        else:
            current += line
    if current:
        chunks.append(current.rstrip())
    return chunks


def post_to_discord(recap_text: str, webhook_url: str | None = None) -> None:
    """
    Send the recap to Discord.  webhook_url defaults to DISCORD_WEBHOOK_URL env var.
    """
    url = webhook_url or credentials.get_secret("DISCORD_WEBHOOK_URL")
    if not url:
        raise EnvironmentError(
            "DISCORD_WEBHOOK_URL is not set.\n"
            "Run  python setup_keys.py  to store it in Keychain.\n"
            "Create a webhook in Discord: Server Settings → Integrations → Webhooks"
        )

    chunks = _split_into_chunks(recap_text, DISCORD_EMBED_LIMIT)

    # First chunk → rich embed for a nicer presentation
    first_payload = {
        "embeds": [
            {
                "title": "⚾  Weekly Fantasy Baseball Recap",
                "description": chunks[0],
                "color": 0x1E5F99,  # baseball blue
            }
        ]
    }
    _send(url, first_payload)

    # Any overflow goes out as plain content messages
    for chunk in chunks[1:]:
        for sub in _split_into_chunks(chunk, DISCORD_CONTENT_LIMIT):
            _send(url, {"content": sub})

    print(f"Posted to Discord ({len(chunks)} message(s)).")


def _send(url: str, payload: dict) -> None:
    resp = requests.post(url, json=payload, timeout=10)
    if resp.status_code not in (200, 204):
        raise RuntimeError(
            f"Discord webhook returned {resp.status_code}: {resp.text[:200]}"
        )
