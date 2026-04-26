"""
One-time bootstrap script for BeerLeagueBaseball CI pipeline.

Seeds data/{year}/season_history.json and data/{year}/records.json from
existing week_NN.json files. Run once manually before ci_runner.py takes
over the weekly update cycle.

Usage:
    python3 bootstrap.py [--season 2026]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

DATA_ROOT = Path(__file__).parent / "data"

LOWER_IS_BETTER = {"ERA", "WHIP"}


# ── Category stat parsing ─────────────────────────────────────────────────────

def _parse_stat(key: str, value: str) -> float:
    """Parse a category stat string to float. Returns -1 on failure."""
    try:
        if key == "H/AB":
            parts = value.split("/")
            if len(parts) == 2 and int(parts[1]) > 0:
                return int(parts[0]) / int(parts[1])
            return 0.0
        return float(value)
    except (ValueError, ZeroDivisionError):
        return -1.0


def _team_beats(cat: str, a_val: float, b_val: float) -> int:
    """Return 1 if team A beats team B in this category, 0 if tie, -1 if loss."""
    if a_val < 0 or b_val < 0:
        return 0
    if cat in LOWER_IS_BETTER:
        if a_val < b_val:
            return 1
        if a_val > b_val:
            return -1
        return 0
    else:
        if a_val > b_val:
            return 1
        if a_val < b_val:
            return -1
        return 0


# ── Weekly points extraction ──────────────────────────────────────────────────

def _extract_weekly_points(week_data: dict) -> dict[str, float]:
    """Return {team_name: category_wins} from a week's matchup data."""
    points: dict[str, float] = {}
    for m in week_data.get("matchups", []):
        for t in m.get("teams", []):
            name = t.get("name", "")
            if name:
                points[name] = float(t.get("points", 0.0))
    return points


# ── Records extraction ────────────────────────────────────────────────────────

def _extract_records_from_week(week_data: dict, week_num: int) -> dict:
    """
    Scan a week's matchup data and return a records dict with the best
    single-week team stats found in that week.
    """
    records: dict = {}

    for m in week_data.get("matchups", []):
        teams = m.get("teams", [])
        winner_key = m.get("winner_key")

        for t in teams:
            name = t.get("name", "")
            stats = t.get("category_stats", {})
            pts = float(t.get("points", 0.0))
            team_key = t.get("team_key", "")
            is_winner = (team_key == winner_key) and not m.get("is_tied")

            # Highest single-week category score
            _maybe_update(records, "most_category_wins", pts, name, week_num, higher_is_better=True)

            # Most HR (team)
            hr = _parse_stat("HR", stats.get("HR", "-1"))
            _maybe_update(records, "most_hr_team", hr, name, week_num, higher_is_better=True)

            # Highest OBP
            obp = _parse_stat("OBP", stats.get("OBP", "-1"))
            _maybe_update(records, "highest_obp", obp, name, week_num, higher_is_better=True)

            # Most SB
            sb = _parse_stat("SB", stats.get("SB", "-1"))
            _maybe_update(records, "most_sb", sb, name, week_num, higher_is_better=True)

            # Most RBI
            rbi = _parse_stat("RBI", stats.get("RBI", "-1"))
            _maybe_update(records, "most_rbi", rbi, name, week_num, higher_is_better=True)

            # Most K (team pitching)
            k = _parse_stat("K", stats.get("K", "-1"))
            _maybe_update(records, "most_k_team", k, name, week_num, higher_is_better=True)

            # Lowest ERA in a winning effort
            if is_winner:
                era = _parse_stat("ERA", stats.get("ERA", "-1"))
                if era >= 0:
                    _maybe_update(records, "lowest_era_winner", era, name, week_num, higher_is_better=False)

    return records


def _maybe_update(
    records: dict,
    key: str,
    value: float,
    team: str,
    week: int,
    higher_is_better: bool,
) -> None:
    """Update a record entry if value beats the current best."""
    if value < 0:
        return
    current = records.get(key)
    if current is None:
        records[key] = {"value": value, "team": team, "week": week}
        return
    if higher_is_better and value > current["value"]:
        records[key] = {"value": value, "team": team, "week": week}
    elif not higher_is_better and value < current["value"]:
        records[key] = {"value": value, "team": team, "week": week}


# ── Bootstrap logic ───────────────────────────────────────────────────────────

def bootstrap(season: int) -> None:
    season_dir = DATA_ROOT / str(season)
    if not season_dir.exists():
        print(f"[bootstrap] No data directory found for {season}: {season_dir}", file=sys.stderr)
        sys.exit(1)

    week_files = sorted(season_dir.glob("week_*.json"))
    if not week_files:
        print(f"[bootstrap] No week_NN.json files found in {season_dir}", file=sys.stderr)
        sys.exit(1)

    print(f"[bootstrap] Found {len(week_files)} week file(s) for {season}: "
          f"{[f.name for f in week_files]}")

    # Load all week data
    weeks: list[tuple[int, dict]] = []
    for wf in week_files:
        try:
            with open(wf, encoding="utf-8") as f:
                data = json.load(f)
            wk = int(wf.stem.split("_")[1])
            weeks.append((wk, data))
        except Exception as e:
            print(f"[bootstrap] Warning: could not read {wf.name}: {e}", file=sys.stderr)

    if not weeks:
        print("[bootstrap] No valid week files could be read.", file=sys.stderr)
        sys.exit(1)

    # --- Build season_history.json ---

    # Get team names from standings of the latest week
    latest_week_data = weeks[-1][1]
    team_names = [s["name"] for s in sorted(
        latest_week_data.get("standings", []), key=lambda s: s.get("rank", 99)
    )]

    if not team_names:
        # Fallback: extract from matchups
        team_names = sorted({
            t["name"]
            for _, wd in weeks
            for m in wd.get("matchups", [])
            for t in m.get("teams", [])
            if t.get("name")
        })

    print(f"[bootstrap] Found {len(team_names)} teams.")

    weekly_points: dict[str, dict[str, float]] = {}
    for wk, wd in weeks:
        key = f"week_{wk:02d}"
        weekly_points[key] = _extract_weekly_points(wd)

    season_history = {
        "power_rankings": {},
        "weekly_points": weekly_points,
        "manager_spotlight_rotation": team_names,
        "last_spotlight_week": None,
    }

    sh_path = season_dir / "season_history.json"
    with open(sh_path, "w", encoding="utf-8") as f:
        json.dump(season_history, f, indent=2, ensure_ascii=False)
    print(f"[bootstrap]   ✓ Wrote {sh_path.name}")

    # --- Build records.json ---

    combined_records: dict = {}
    for wk, wd in weeks:
        week_records = _extract_records_from_week(wd, wk)
        for rec_key, rec_val in week_records.items():
            higher = rec_key not in ("lowest_era_winner",)
            _maybe_update(
                combined_records,
                rec_key,
                rec_val["value"],
                rec_val["team"],
                rec_val["week"],
                higher_is_better=higher,
            )

    records_path = season_dir / "records.json"
    with open(records_path, "w", encoding="utf-8") as f:
        json.dump(combined_records, f, indent=2, ensure_ascii=False)
    print(f"[bootstrap]   ✓ Wrote {records_path.name}")

    # --- Summary ---
    print()
    print(f"[bootstrap] season_history.json summary:")
    for wk_key, pts in weekly_points.items():
        top = sorted(pts.items(), key=lambda x: x[1], reverse=True)[:3]
        top_str = ", ".join(f"{t}:{v:.0f}" for t, v in top)
        print(f"  {wk_key}: {top_str}")

    print()
    print(f"[bootstrap] records.json summary:")
    for k, v in combined_records.items():
        print(f"  {k}: {v['value']} ({v['team']}, week {v['week']})")

    print()
    print(f"[bootstrap] Done ✓  Bootstrap complete for {season}.")
    print(f"[bootstrap] Next step: run ci_runner.py --mode recap to generate articles.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Bootstrap season_history.json and records.json")
    parser.add_argument("--season", type=int, default=2026)
    args = parser.parse_args()
    bootstrap(args.season)


if __name__ == "__main__":
    main()
