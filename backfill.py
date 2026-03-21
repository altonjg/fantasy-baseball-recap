"""
Backfill historical weekly data for a given season.

Usage:
  python3 backfill.py                              # backfills 2025 (458.l.25686)
  python3 backfill.py --league 431.l.29063         # explicit league key (2024)
  python3 backfill.py --year 2024                  # shorthand — looks up key automatically
  python3 backfill.py --year 2024 --weeks 1-12     # only backfill a week range
  python3 backfill.py --stats --year 2025          # fetch Fangraphs advanced stats (WAR/wRC+/FIP)

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
from yahoo_client import fetch_weekly_data, get_league_meta, get_draft_results_enriched, get_player_adp, get_division_names, get_standings
from mlb_stats import get_player_id, get_player_headshot_url

try:
    import pybaseball as pb
    pb.cache.enable()
    _PYBASEBALL_AVAILABLE = True
except ImportError:
    _PYBASEBALL_AVAILABLE = False

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


def backfill_draft(oauth, league_key: str, season: int) -> None:
    """Fetch and save the full draft board for a single season."""
    data_dir = DATA_ROOT / str(season)
    out_path  = data_dir / "draft_results.json"

    if out_path.exists():
        print(f"  {season} — draft_results.json already exists, skipping")
        return

    print(f"  {season} — fetching draft results for {league_key}...", end=" ", flush=True)
    try:
        session = oauth.get_session()
        picks = get_draft_results_enriched(session, league_key)
        if not picks:
            print("no data returned (pre-season or unsupported)")
            return
        data_dir.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w") as f:
            json.dump(
                {"season": season, "league_key": league_key,
                 "fetched_at": datetime.now().isoformat(), "picks": picks},
                f, indent=2,
            )
        print(f"saved ({len(picks)} picks)")
    except Exception as e:
        print(f"FAILED — {e}")


def backfill_headshots() -> None:
    """
    Build a shared mlb_players.json mapping player names → MLB ID + headshot URL.
    Scans all draft_results.json files for unique player names, then hits the
    MLB Stats API (free, no key) to resolve IDs and headshot URLs.
    Saves to data/mlb_players.json.
    """
    out_path = DATA_ROOT / "mlb_players.json"

    # Load existing cache so we skip already-resolved players
    existing: dict = {}
    if out_path.exists():
        try:
            existing = json.loads(out_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    # Collect all unique player names across all seasons' draft boards
    all_names: set[str] = set()
    for season_dir in sorted(DATA_ROOT.iterdir()):
        if not (season_dir.is_dir() and season_dir.name.isdigit()):
            continue
        draft_file = season_dir / "draft_results.json"
        if not draft_file.exists():
            continue
        try:
            picks = json.loads(draft_file.read_text(encoding="utf-8")).get("picks", [])
            for p in picks:
                name = p.get("player_name", "").strip()
                if name and name not in existing:
                    all_names.add(name)
        except Exception:
            pass

    if not all_names:
        print("  No new players to resolve.")
        return

    print(f"  Resolving {len(all_names)} new player names via MLB Stats API...")
    resolved = 0
    for name in sorted(all_names):
        pid = get_player_id(name)
        existing[name] = {
            "mlb_id":      pid,
            "headshot_url": get_player_headshot_url(name) if pid else None,
        }
        if pid:
            resolved += 1

    DATA_ROOT.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(existing, f, indent=2)
    print(f"  Saved {len(existing)} players ({resolved} with MLB IDs) to data/mlb_players.json")


def backfill_divisions(oauth, league_key: str, season: int) -> None:
    """Fetch and save division names + team→division mapping for a single season."""
    data_dir = DATA_ROOT / str(season)
    out_path  = data_dir / "divisions.json"

    print(f"  {season} — fetching division names for {league_key}...", end=" ", flush=True)
    try:
        session = oauth.get_session()
        divisions = get_division_names(session, league_key)
        if not divisions:
            print("no division data returned")
            return
        # Also fetch standings to get team→division_id mapping
        standings = get_standings(session, league_key)
        team_divisions = {}
        for t in standings:
            div_id   = t.get("division_id", "")
            div_name = divisions.get(str(div_id), "")
            if t.get("team_key") and div_name:
                team_divisions[t["team_key"]] = div_name
        data_dir.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w") as f:
            json.dump(
                {"season": season, "league_key": league_key,
                 "fetched_at": datetime.now().isoformat(),
                 "divisions": divisions, "team_divisions": team_divisions},
                f, indent=2,
            )
        print(f"saved ({len(divisions)} divisions, {len(team_divisions)} teams mapped)")
    except Exception as e:
        print(f"FAILED — {e}")


def backfill_adp(oauth, league_key: str, season: int) -> None:
    """Fetch and save ADP snapshot for a single season."""
    data_dir = DATA_ROOT / str(season)
    out_path  = data_dir / "adp_snapshot.json"

    if out_path.exists():
        print(f"  {season} — adp_snapshot.json already exists, skipping (delete to refresh)")
        return

    print(f"  {season} — fetching ADP snapshot for {league_key}...", end=" ", flush=True)
    try:
        session = oauth.get_session()
        players = get_player_adp(session, league_key, total=400)
        if not players:
            print("no ADP data returned (pre-season or unsupported)")
            return
        data_dir.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w") as f:
            json.dump(
                {"season": season, "league_key": league_key,
                 "fetched_at": datetime.now().isoformat(), "players": players},
                f, indent=2,
            )
        print(f"saved ({len(players)} players)")
    except Exception as e:
        print(f"FAILED — {e}")


def backfill_advanced_stats(season: int) -> None:
    """
    Fetch Fangraphs batting + pitching advanced stats for a season via pybaseball.
    Saves to data/{year}/advanced_stats.json.
    Always overwrites (stats change during the season).
    """
    if not _PYBASEBALL_AVAILABLE:
        print("  pybaseball not installed — run: pip3 install pybaseball")
        return

    data_dir = DATA_ROOT / str(season)
    out_path  = data_dir / "advanced_stats.json"

    print(f"  {season} — fetching Fangraphs batting stats...", end=" ", flush=True)
    try:
        bat_df = pb.batting_stats(season, qual=50)
        bat_cols = ["Name", "Team", "G", "PA", "AB", "HR", "R", "RBI", "SB", "CS",
                    "AVG", "OBP", "SLG", "BB%", "K%", "wRC+", "WAR"]
        bat_cols = [c for c in bat_cols if c in bat_df.columns]
        bat_records = bat_df[bat_cols].round(3).to_dict(orient="records")
        print(f"{len(bat_records)} batters")
    except Exception as e:
        print(f"FAILED — {e}")
        bat_records = []

    print(f"  {season} — fetching Fangraphs pitching stats...", end=" ", flush=True)
    try:
        pit_df = pb.pitching_stats(season, qual=30)
        pit_cols = ["Name", "Team", "G", "GS", "IP", "W", "L", "SV", "HLD",
                    "ERA", "FIP", "xFIP", "WHIP", "K/9", "BB/9", "K%", "BB%", "WAR"]
        pit_cols = [c for c in pit_cols if c in pit_df.columns]
        pit_records = pit_df[pit_cols].round(3).to_dict(orient="records")
        print(f"{len(pit_records)} pitchers")
    except Exception as e:
        print(f"FAILED — {e}")
        pit_records = []

    if not bat_records and not pit_records:
        return

    data_dir.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(
            {"season": season, "fetched_at": datetime.now().isoformat(),
             "batting": bat_records, "pitching": pit_records},
            f, indent=2, default=str,
        )
    print(f"  {season} — saved advanced_stats.json ({len(bat_records)} batters, {len(pit_records)} pitchers)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill historical weekly data.")
    parser.add_argument("--league", default=None, help="Explicit league key, e.g. 431.l.29063")
    parser.add_argument("--year",   default=None, type=int, help="Season year, e.g. 2024")
    parser.add_argument("--weeks",  default=None, help="Week range, e.g. '1-24' or '10-15'")
    parser.add_argument("--draft",  action="store_true",
                        help="Fetch draft results instead of weekly data. "
                             "Use --year to target one season, or omit to backfill all known seasons.")
    parser.add_argument("--adp",       action="store_true",
                        help="Fetch ADP snapshot for the target season. "
                             "Use --year to target one season, or omit for all known seasons.")
    parser.add_argument("--divisions",  action="store_true",
                        help="Fetch division names and team→division mapping. "
                             "Use --year to target one season, or omit for all known seasons.")
    parser.add_argument("--headshots",  action="store_true",
                        help="Resolve MLB player IDs and headshot URLs for all draft picks. "
                             "Saves to data/mlb_players.json.")
    parser.add_argument("--stats",      action="store_true",
                        help="Fetch Fangraphs advanced stats (WAR, wRC+, FIP) via pybaseball. "
                             "Use --year to target one season, or omit for all known seasons.")
    args = parser.parse_args()

    # ── Advanced stats mode (no OAuth needed) ─────────────────────────────────
    if args.stats:
        targets = {args.year: None} if args.year else LEAGUE_KEYS
        print(f"Fetching Fangraphs advanced stats for {len(targets)} season(s)...")
        for yr in sorted(targets.keys()):
            backfill_advanced_stats(yr)
        print("\nDone.")
        return

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

    # ── Draft backfill mode ────────────────────────────────────────────────────
    if args.draft:
        if args.year:
            targets = {args.year: LEAGUE_KEYS.get(args.year) or args.league}
            if not targets[args.year]:
                print(f"No league key found for {args.year}. Use --league to specify one.")
                return
        else:
            targets = LEAGUE_KEYS

        print(f"Backfilling draft results for {len(targets)} season(s)...")
        for yr, lk in sorted(targets.items()):
            backfill_draft(oauth, lk, yr)
        print("\nDone.")
        return

    # ── Headshots mode ───────────────────────────────────────────────────────
    if args.headshots:
        print("Building MLB player headshot cache...")
        backfill_headshots()
        print("\nDone.")
        return

    # ── Divisions mode ────────────────────────────────────────────────────────
    if args.divisions:
        if args.year:
            targets = {args.year: LEAGUE_KEYS.get(args.year) or args.league}
            if not targets[args.year]:
                print(f"No league key found for {args.year}. Use --league to specify one.")
                return
        else:
            targets = LEAGUE_KEYS

        print(f"Backfilling division names for {len(targets)} season(s)...")
        for yr, lk in sorted(targets.items()):
            backfill_divisions(oauth, lk, yr)
        print("\nDone.")
        return

    # ── ADP snapshot mode ──────────────────────────────────────────────────────
    if args.adp:
        if args.year:
            targets = {args.year: LEAGUE_KEYS.get(args.year) or args.league}
            if not targets[args.year]:
                print(f"No league key found for {args.year}. Use --league to specify one.")
                return
        else:
            targets = LEAGUE_KEYS

        print(f"Backfilling ADP snapshots for {len(targets)} season(s)...")
        for yr, lk in sorted(targets.items()):
            backfill_adp(oauth, lk, yr)
        print("\nDone.")
        return

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
