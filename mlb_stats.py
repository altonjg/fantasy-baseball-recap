"""
MLB Stats API client — statsapi.mlb.com (free, no key required).

Provides player ID lookup, season stats, and weekly game log summaries
for enriching AI-generated fantasy baseball articles and the dashboard.

Usage:
    from mlb_stats import enrich_top_players, get_player_headshot_url

    # Enrich week_data['top_players'] with real MLB stats before article gen:
    week_data['top_players'] = enrich_top_players(
        week_data['top_players'], season=2025,
        week_start='2025-09-01', week_end='2025-09-07'
    )
"""

from __future__ import annotations

import json
import time
import urllib.parse
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import requests

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_BASE    = "https://statsapi.mlb.com/api/v1"
_IMG_BASE = "https://img.mlbstatic.com/mlb-photos/image/upload"
_GENERIC_HEADSHOT = (
    f"{_IMG_BASE}/d_people:generic:headshot:67:current.png"
    "/w_213,q_auto:best/v1/people/1/headshot/67/current"
)

_CACHE_DIR  = Path(__file__).parent / ".mlb_cache"
_CACHE_FILE = _CACHE_DIR / "player_ids.json"

# ---------------------------------------------------------------------------
# Disk-backed player ID cache
# ---------------------------------------------------------------------------

def _load_id_cache() -> dict[str, int]:
    try:
        if _CACHE_FILE.exists():
            with open(_CACHE_FILE) as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def _save_id_cache(cache: dict[str, int]) -> None:
    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        with open(_CACHE_FILE, "w") as f:
            json.dump(cache, f, indent=2)
    except Exception:
        pass


_ID_CACHE: dict[str, int] = _load_id_cache()


# ---------------------------------------------------------------------------
# HTTP helper
# ---------------------------------------------------------------------------

_SESSION = requests.Session()
_SESSION.headers.update({"Accept": "application/json"})


def _get(path: str, params: dict | None = None, timeout: int = 8) -> dict:
    url  = f"{_BASE}{path}"
    resp = _SESSION.get(url, params=params, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# Player lookup
# ---------------------------------------------------------------------------

def get_player_id(name: str) -> int | None:
    """
    Look up an MLB player's statsapi ID by name.
    Results are disk-cached so repeated calls are instant.
    Returns None if not found.
    """
    key = name.strip().lower()
    if key in _ID_CACHE:
        return _ID_CACHE[key] or None  # 0 means "not found, stop retrying"

    try:
        data   = _get("/people/search", {"names": name, "sportId": 1})
        people = data.get("people", [])
        pid    = people[0]["id"] if people else None
        # Only cache confirmed results (found or definitively not found via API)
        _ID_CACHE[key] = pid or 0
        _save_id_cache(_ID_CACHE)
    except Exception:
        # Network / API error — don't cache, allow retry next time
        pid = None

    return pid


def get_player_headshot_url(name: str) -> str:
    """Return the headshot URL for a player (falls back to generic silhouette)."""
    pid = get_player_id(name)
    if not pid:
        return _GENERIC_HEADSHOT
    return (
        f"{_IMG_BASE}/d_people:generic:headshot:67:current.png"
        f"/w_213,q_auto:best/v1/people/{pid}/headshot/67/current"
    )


# ---------------------------------------------------------------------------
# Season stats
# ---------------------------------------------------------------------------

def get_season_stats(player_id: int, year: int) -> dict:
    """
    Return a flat dict of season stats for a player.
    Tries hitting stats first; pitching if no hitting data.
    Returns {} on failure.
    """
    for group in ("hitting", "pitching"):
        try:
            data = _get(
                f"/people/{player_id}/stats",
                {"stats": "season", "season": year, "sportId": 1, "group": group},
            )
            splits = data.get("stats", [{}])[0].get("splits", [])
            if splits:
                raw = splits[0].get("stat", {})
                return {"group": group, **raw}
        except Exception:
            continue
    return {}


# ---------------------------------------------------------------------------
# Weekly game log
# ---------------------------------------------------------------------------

def get_game_log(
    player_id: int,
    year: int,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[dict]:
    """
    Return a list of game-by-game log entries for a player.
    start_date / end_date: 'YYYY-MM-DD' strings (inclusive).
    Returns [] on failure.
    """
    params: dict[str, Any] = {
        "stats":   "gameLog",
        "season":  year,
        "sportId": 1,
    }
    if start_date:
        params["startDate"] = start_date
    if end_date:
        params["endDate"] = end_date

    try:
        data   = _get(f"/people/{player_id}/stats", params)
        splits = data.get("stats", [{}])[0].get("splits", [])
        return [s.get("stat", {}) | {"date": s.get("date", "")} for s in splits]
    except Exception:
        return []


def summarize_game_log(games: list[dict]) -> str:
    """
    Build a one-line human-readable summary of a week's game log.
    e.g. "3 G · .412 AVG · 2 HR · 7 RBI" (hitter)
    or   "2 GS · 12.1 IP · 1.46 ERA · 18 K" (pitcher)
    """
    if not games:
        return ""

    # Detect hitter vs pitcher by which keys dominate
    sample = games[0]
    is_pitcher = "inningsPitched" in sample or "earnedRuns" in sample

    g = len(games)
    if is_pitcher:
        ip   = sum(float(x.get("inningsPitched", 0) or 0) for x in games)
        er   = sum(int(x.get("earnedRuns", 0) or 0)       for x in games)
        k    = sum(int(x.get("strikeOuts", 0) or 0)        for x in games)
        bb   = sum(int(x.get("baseOnBalls", 0) or 0)       for x in games)
        era  = (er / ip * 9) if ip else 0
        parts = [f"{g} app", f"{ip:.1f} IP", f"{era:.2f} ERA", f"{k} K"]
        if bb:
            parts.append(f"{bb} BB")
        return " · ".join(parts)
    else:
        ab  = sum(int(x.get("atBats", 0)    or 0) for x in games)
        h   = sum(int(x.get("hits", 0)      or 0) for x in games)
        hr  = sum(int(x.get("homeRuns", 0)  or 0) for x in games)
        rbi = sum(int(x.get("rbi", 0)       or 0) for x in games)
        sb  = sum(int(x.get("stolenBases",0)or 0) for x in games)
        avg = (h / ab) if ab else 0
        parts = [f"{g} G", f".{int(avg*1000):03d} AVG", f"{hr} HR", f"{rbi} RBI"]
        if sb:
            parts.append(f"{sb} SB")
        return " · ".join(parts)


# ---------------------------------------------------------------------------
# Bulk enrichment — top_players list
# ---------------------------------------------------------------------------

def enrich_top_players(
    players: list[dict],
    year: int,
    week_start: str | None = None,
    week_end:   str | None = None,
    max_players: int = 10,
    delay: float = 0.2,
) -> list[dict]:
    """
    Enrich a top_players list (from week_data) with real MLB stats.

    Adds to each player dict:
        mlb_id         — statsapi person ID
        mlb_headshot   — headshot image URL
        mlb_week_log   — one-line game log summary for the fantasy week
        mlb_season     — dict of season stats
        mlb_week_games — list of raw game log dicts (for AI prompts)

    Players without an MLB ID (or lookup failures) are returned unchanged.
    Skips players already enriched (have 'mlb_id' key).

    delay: seconds between API calls to be polite to the free endpoint.
    """
    enriched = []
    for player in players[:max_players]:
        if "mlb_id" in player:
            enriched.append(player)
            continue

        name = player.get("name", "")
        if not name:
            enriched.append(player)
            continue

        pid = get_player_id(name)
        p   = dict(player)

        if pid:
            p["mlb_id"]       = pid
            p["mlb_headshot"] = (
                f"{_IMG_BASE}/d_people:generic:headshot:67:current.png"
                f"/w_213,q_auto:best/v1/people/{pid}/headshot/67/current"
            )
            try:
                season_stats = get_season_stats(pid, year)
                p["mlb_season"] = season_stats
            except Exception:
                p["mlb_season"] = {}

            if week_start and week_end:
                try:
                    games = get_game_log(pid, year, week_start, week_end)
                    p["mlb_week_games"] = games
                    p["mlb_week_log"]   = summarize_game_log(games)
                except Exception:
                    p["mlb_week_games"] = []
                    p["mlb_week_log"]   = ""

            time.sleep(delay)  # polite rate limiting

        enriched.append(p)

    # Append any players beyond max_players unchanged
    enriched.extend(players[max_players:])
    return enriched


# ---------------------------------------------------------------------------
# Date helpers
# ---------------------------------------------------------------------------

def week_date_range(generated_at: str, lookback_days: int = 7) -> tuple[str, str]:
    """
    Given a 'generated_at' ISO timestamp, compute the fantasy week's
    approximate date range (end = generated_at date, start = end - lookback_days).
    Returns (start_date, end_date) as 'YYYY-MM-DD' strings.
    """
    try:
        end_dt   = datetime.fromisoformat(generated_at[:10])
        start_dt = end_dt - timedelta(days=lookback_days)
        return start_dt.strftime("%Y-%m-%d"), end_dt.strftime("%Y-%m-%d")
    except Exception:
        today = datetime.now()
        return (today - timedelta(days=lookback_days)).strftime("%Y-%m-%d"), today.strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# CLI — quick test / cache warm-up
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    names = sys.argv[1:] or ["Shohei Ohtani", "Aaron Judge", "Corbin Carroll"]
    for name in names:
        pid = get_player_id(name)
        print(f"{name:30s} → ID: {pid}")
        if pid:
            stats = get_season_stats(pid, datetime.now().year)
            grp   = stats.pop("group", "?")
            keys  = ["avg", "homeRuns", "rbi", "era", "strikeOuts", "inningsPitched"]
            line  = ", ".join(f"{k}={stats[k]}" for k in keys if k in stats)
            print(f"  {grp}: {line or '(no stats yet)'}")
