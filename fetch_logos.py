"""
fetch_logos.py — Fetch team logo URLs from Yahoo Fantasy API.

Saves to data/team_logos.json as a flat {team_name: logo_url} dict.

Run:
    python3 fetch_logos.py

Requires Yahoo OAuth credentials to be set up (see setup_keys.py).
"""

from __future__ import annotations

import json
from pathlib import Path

from auth import setup_oauth
from yahoo_client import _api_get

DATA_ROOT = Path(__file__).parent / "data"

# Hardcoded league keys — same as backfill.py — used as final fallback
# when neither draft_order.json nor the week JSONs contain a league_key field.
LEAGUE_KEYS = {
    2017: "370.l.36051",
    2021: "404.l.39098",
    2022: "412.l.49651",
    2023: "422.l.35047",
    2024: "431.l.29063",
    2025: "458.l.25686",
    2026: "469.l.10470",
}


def get_league_key_for_season(season: int) -> str | None:
    """Try to find the Yahoo league_key for a given season year."""
    # 1. Check draft_order.json
    draft_file = DATA_ROOT / str(season) / "draft_order.json"
    if draft_file.exists():
        try:
            with open(draft_file) as f:
                d = json.load(f)
            if d.get("league_key"):
                return d["league_key"]
        except Exception:
            pass

    # 2. Fall back to any week JSON file
    season_dir = DATA_ROOT / str(season)
    if season_dir.exists():
        for wf in sorted(season_dir.glob("week_*.json")):
            try:
                with open(wf) as f:
                    d = json.load(f)
                if d.get("league_key"):
                    return d["league_key"]
            except Exception:
                pass

    # 3. Hardcoded fallback
    return LEAGUE_KEYS.get(season)


def fetch_logos_for_league(session, league_key: str) -> dict[str, str]:
    """
    Return {team_name: logo_url} for all teams in a Yahoo league.
    Calls /league/{league_key}/teams endpoint.
    """
    try:
        data = _api_get(session, f"league/{league_key}/teams")
        # The Yahoo API returns: data["league"][1]["teams"]
        league_data = data.get("league", [])
        teams_block = {}
        for item in league_data:
            if isinstance(item, dict) and "teams" in item:
                teams_block = item["teams"]
                break

        count = int(teams_block.get("count", 0))
        logos: dict[str, str] = {}

        for i in range(count):
            team_entry = teams_block.get(str(i), {}).get("team", [])
            if not team_entry:
                continue

            # team[0] is a list of metadata dicts — flatten them
            info_list = team_entry[0] if team_entry else []
            flat: dict = {}
            for item in info_list:
                if isinstance(item, dict):
                    flat.update(item)

            name = flat.get("name", "")
            if not name:
                continue

            # Extract logo URL
            logo_url = ""
            for entry in flat.get("team_logos", []):
                tl = entry.get("team_logo", {}) if isinstance(entry, dict) else {}
                logo_url = tl.get("url", "")
                if logo_url:
                    break

            logos[name] = logo_url

        return logos

    except Exception as e:
        print(f"  ⚠ Error fetching logos for {league_key}: {e}")
        return {}


def main() -> None:
    print("🔑 Authenticating with Yahoo…")
    oauth  = setup_oauth()
    session = oauth.get_session()

    # Load existing logos (so we don't lose any already fetched)
    logos_file = DATA_ROOT / "team_logos.json"
    existing: dict[str, str] = {}
    if logos_file.exists():
        try:
            with open(logos_file) as f:
                existing = json.load(f)
            print(f"  Loaded {len(existing)} existing logo entries.")
        except Exception:
            pass

    # Find all seasons with a league_key
    season_dirs = sorted(
        [d for d in DATA_ROOT.iterdir() if d.is_dir() and d.name.isdigit()],
        key=lambda d: int(d.name),
    )

    all_logos = dict(existing)

    for season_dir in season_dirs:
        season = int(season_dir.name)
        league_key = get_league_key_for_season(season)
        if not league_key:
            print(f"  [{season}] No league key found — skipping.")
            continue

        print(f"  [{season}] Fetching logos for league {league_key}…")
        season_logos = fetch_logos_for_league(session, league_key)

        if season_logos:
            added = 0
            for name, url in season_logos.items():
                if name not in all_logos or (url and not all_logos.get(name)):
                    all_logos[name] = url
                    added += 1
            print(f"    → Found {len(season_logos)} teams, added/updated {added} entries.")
        else:
            print(f"    → No teams returned.")

    # Save merged logos
    logos_file.parent.mkdir(parents=True, exist_ok=True)
    with open(logos_file, "w") as f:
        json.dump(all_logos, f, indent=2, sort_keys=True)

    non_empty = sum(1 for v in all_logos.values() if v)
    print(f"\n✅ Saved {len(all_logos)} teams ({non_empty} with logo URLs) → {logos_file}")


if __name__ == "__main__":
    main()
