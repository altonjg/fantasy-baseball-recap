"""
Backfill historical weekly data for a given season.

Usage:
  python3 backfill.py                              # backfills 2025 (458.l.25686)
  python3 backfill.py --league 431.l.29063         # explicit league key (2024)
  python3 backfill.py --year 2024                  # shorthand — looks up key automatically
  python3 backfill.py --year 2024 --weeks 1-12     # only backfill a week range

Saves raw data to data/{year}/week_NN.json.
Skips weeks that already have a file.
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

_safe_env  = Path.home() / ".config" / "fantasy_recap" / ".env"
_local_env = Path(__file__).parent / ".env"
load_dotenv(_safe_env if _safe_env.exists() else _local_env)

from auth import setup_oauth
from yahoo_client import fetch_weekly_data, get_league_meta

DATA_ROOT = Path(__file__).parent / "data"

# Known BeerLeagueBaseball league keys by season year
LEAGUE_KEYS = {
    2017: "370.l.36051",
    2021: "404.l.39098",
    2022: "412.l.49651",
    2023: "422.l.35047",
    2024: "431.l.29063",
    2025: "458.l.25686",
    2026: "469.l.10470",
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill historical weekly data.")
    parser.add_argument("--league", default=None, help="Explicit league key, e.g. 431.l.29063")
    parser.add_argument("--year",   default=None, type=int, help="Season year, e.g. 2024")
    parser.add_argument("--weeks",  default=None, help="Week range, e.g. '1-24' or '10-15'")
    args = parser.parse_args()

    # Resolve league key
    if args.league:
        league_key = args.league
    elif args.year:
        league_key = LEAGUE_KEYS.get(args.year)
        if not league_key:
            print(f"No league key found for year {args.year}. Use --league to specify one.")
            return
    else:
        league_key = LEAGUE_KEYS[2025]

    print(f"Setting up Yahoo OAuth...")
    oauth = setup_oauth()
    session = oauth.get_session()

    print(f"Fetching league metadata for {league_key}...")
    meta = get_league_meta(session, league_key)
    start_week = int(meta.get("start_week", 1))
    end_week   = int(meta.get("end_week", 24))
    season     = int(meta.get("season", args.year or 2025))
    print(f"  League: {meta.get('name')}  |  Season: {season}  |  Weeks {start_week}–{end_week}")

    if args.weeks:
        parts = args.weeks.split("-")
        start_week = int(parts[0])
        end_week   = int(parts[1]) if len(parts) > 1 else int(parts[0])

    # Season-specific data directory
    data_dir = DATA_ROOT / str(season)
    data_dir.mkdir(parents=True, exist_ok=True)

    weeks_to_fetch = list(range(start_week, end_week + 1))
    skipped, saved, failed = 0, 0, 0

    for week in weeks_to_fetch:
        out_path = data_dir / f"week_{week:02d}.json"
        if out_path.exists():
            print(f"  Week {week:2d} — already exists, skipping")
            skipped += 1
            continue

        print(f"  Week {week:2d} — fetching...", end=" ", flush=True)
        try:
            data = fetch_weekly_data(oauth, league_key, week=week)
            with open(out_path, "w") as f:
                json.dump(
                    {**data, "recap_text": "", "generated_at": datetime.now().isoformat()},
                    f, indent=2, default=str,
                )
            print(f"saved ({len(data.get('matchups', []))} matchups)")
            saved += 1
            time.sleep(1)   # be polite to Yahoo's API
        except Exception as e:
            print(f"FAILED — {e}")
            failed += 1

    print(f"\nDone.  Saved: {saved}  |  Skipped: {skipped}  |  Failed: {failed}")
    if saved:
        print(f"Data saved to data/{season}/  —  refresh the dashboard to see it.")


if __name__ == "__main__":
    main()
