"""
Weekly Fantasy Baseball Recap — main entry point.

Usage:
  python main.py                  # recap the most recently completed week
  python main.py --week 12        # recap a specific week
  python main.py --dry-run        # generate recap but don't post to Discord
  python main.py --no-discord     # same as --dry-run
  python main.py --print-data     # show raw fetched data and exit (debug)
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

# Load .env as a fallback for setups that haven't migrated to Keychain yet.
# Keychain is always checked first (in credentials.get_secret), so .env values
# are only used when a key isn't found in the Keychain.
_safe_env  = Path.home() / ".config" / "fantasy_recap" / ".env"
_local_env = Path(__file__).parent / ".env"
_env_path  = _safe_env if _safe_env.exists() else _local_env
load_dotenv(_env_path)

import credentials
from auth import setup_oauth
from yahoo_client import fetch_weekly_data
from recap_generator import generate_recap
from discord_poster import post_to_discord


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate and post a weekly fantasy baseball recap.")
    parser.add_argument("--week", type=int, default=None, help="Override the week number to recap.")
    parser.add_argument("--dry-run", "--no-discord", action="store_true",
                        help="Generate the recap but don't post to Discord.")
    parser.add_argument("--print-data", action="store_true",
                        help="Print the raw fetched data structure and exit (for debugging).")
    args = parser.parse_args()

    league_key = credentials.get_secret("YAHOO_LEAGUE_KEY")
    if not league_key:
        print(
            "Error: YAHOO_LEAGUE_KEY is not set.\n"
            "Run  python setup_keys.py  to store it in Keychain.\n"
            "Format: {game_key}.l.{league_id}  e.g.  458.l.123456",
            file=sys.stderr,
        )
        sys.exit(1)

    # ------------------------------------------------------------------
    # Step 1: Yahoo OAuth
    # ------------------------------------------------------------------
    print("Step 1/4  Setting up Yahoo OAuth...")
    try:
        oauth = setup_oauth()
    except EnvironmentError as e:
        print(f"\n{e}", file=sys.stderr)
        sys.exit(1)

    # ------------------------------------------------------------------
    # Step 2: Fetch league data
    # ------------------------------------------------------------------
    print("Step 2/4  Fetching league data from Yahoo...")
    try:
        data = fetch_weekly_data(oauth, league_key, week=args.week)
    except Exception as e:
        print(f"\nFailed to fetch Yahoo data: {e}", file=sys.stderr)
        raise

    if args.print_data:
        print(json.dumps(data, indent=2, default=str))
        return

    # ------------------------------------------------------------------
    # Step 3: Generate recap with Claude
    # ------------------------------------------------------------------
    print("Step 3/4  Generating recap with Claude...")
    try:
        recap = generate_recap(data)
    except EnvironmentError as e:
        print(f"\n{e}", file=sys.stderr)
        sys.exit(1)

    # Save data + recap to data/{season}/week_NN.json for the Streamlit dashboard
    season    = data.get("season", datetime.now().year)
    data_dir  = Path(__file__).parent / "data" / str(season)
    data_dir.mkdir(parents=True, exist_ok=True)
    save_path = data_dir / f"week_{data['week']:02d}.json"
    with open(save_path, "w") as f:
        json.dump({**data, "recap_text": recap, "generated_at": datetime.now().isoformat()}, f, indent=2, default=str)
    print(f"  Saved to data/{season}/{save_path.name}")

    # ------------------------------------------------------------------
    # Step 4: Post to Discord
    # ------------------------------------------------------------------
    if args.dry_run:
        print("\nStep 4/4  --dry-run: skipping Discord post.")
        print("\n" + "=" * 60)
        print(recap)
        print("=" * 60)
    else:
        print("Step 4/4  Posting to Discord...")
        try:
            post_to_discord(recap)
        except EnvironmentError as e:
            print(f"\n{e}", file=sys.stderr)
            sys.exit(1)

    print("\nDone! 🎉")


if __name__ == "__main__":
    main()
