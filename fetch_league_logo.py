"""
fetch_league_logo.py — Fetch the league logo URL from Yahoo Fantasy API.

Saves to data/league_logo.json as {"url": "<logo_url>"}.

Run:
    python3 fetch_league_logo.py

Uses the most recent known league key by default. Pass --year to target a
specific season's league (the logo is generally consistent across seasons).

Requires Yahoo OAuth credentials to be set up (see setup_keys.py).
"""

from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path

import requests

from auth import setup_oauth
from yahoo_client import _api_get

DATA_ROOT = Path(__file__).parent / "data"

LEAGUE_KEYS = {
    2017: "370.l.36051",
    2021: "404.l.39098",
    2022: "412.l.49651",
    2023: "422.l.35047",
    2024: "431.l.29063",
    2025: "458.l.25686",
    2026: "469.l.10470",
}


def fetch_league_logo(session, league_key: str) -> str | None:
    """
    Return the league logo URL for a given league key, or None if not found.
    Tries both the base league endpoint and the metadata endpoint.
    """
    # Try base league endpoint first — includes league_logos block
    for resource in ("", "metadata"):
        endpoint = f"league/{league_key}" + (f"/{resource}" if resource else "")
        try:
            data = _api_get(session, endpoint)
            league_block = data.get("league", [])
            # Yahoo returns league data as a list of dicts; flatten them
            flat: dict = {}
            for item in (league_block if isinstance(league_block, list) else []):
                if isinstance(item, dict):
                    flat.update(item)

            # league_logos is a list of {"league_logo": {"url": "..."}}
            for entry in flat.get("league_logos", []):
                ll = entry.get("league_logo", {}) if isinstance(entry, dict) else {}
                url = ll.get("url", "")
                if url:
                    return url

            # Some leagues have a logo_url directly on the flat dict
            if flat.get("logo_url"):
                return flat["logo_url"]

        except Exception as e:
            print(f"  ⚠ {endpoint}: {e}")

    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch league logo from Yahoo Fantasy.")
    parser.add_argument("--year", type=int, default=2025,
                        help="Season year to use for the league key (default: 2025)")
    args = parser.parse_args()

    league_key = LEAGUE_KEYS.get(args.year)
    if not league_key:
        print(f"No league key for year {args.year}. Known years: {sorted(LEAGUE_KEYS)}")
        return

    print(f"🔑 Authenticating with Yahoo…")
    oauth = setup_oauth()
    session = oauth.get_session()

    print(f"🔍 Fetching league logo for {league_key} ({args.year})…")
    url = fetch_league_logo(session, league_key)

    if not url:
        print("❌ No league logo URL found in Yahoo response.")
        return

    # Embed the image as a base64 data URI so it works in Streamlit's sandboxed iframe
    data_uri = None
    print(f"📥 Downloading and base64-encoding logo…")
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        content_type = resp.headers.get("content-type", "image/jpeg").split(";")[0].strip()
        data_uri = f"data:{content_type};base64,{base64.b64encode(resp.content).decode()}"
        print(f"   {len(resp.content)} bytes → {len(data_uri)} char data URI")
    except Exception as e:
        print(f"  ⚠ Could not download logo for base64 embedding: {e}")

    out_path = DATA_ROOT / "league_logo.json"
    DATA_ROOT.mkdir(parents=True, exist_ok=True)
    payload: dict = {"url": url, "league_key": league_key, "year": args.year}
    if data_uri:
        payload["data_uri"] = data_uri
    with open(out_path, "w") as f:
        json.dump(payload, f, indent=2)

    print(f"✅ Saved league logo → {out_path}")
    print(f"   {url}")


if __name__ == "__main__":
    main()
