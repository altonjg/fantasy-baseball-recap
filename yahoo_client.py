"""
Yahoo Fantasy Sports API client.

All data is fetched via the v2 REST API using JSON format.
The league_key format is:  {game_key}.l.{league_id}
  e.g.  458.l.12345   (game key 458 = MLB 2025 — see get_current_game_key())
"""

from __future__ import annotations

from typing import Optional

import requests

from auth import YahooOAuth

BASE_URL = "https://fantasysports.yahooapis.com/fantasy/v2"

# Stats where a lower value is better (ERA, WHIP)
_LOWER_IS_BETTER = {"26", "27"}

# Module-level cache so we only fetch stat categories once per run
_stat_categories_cache: dict[str, dict[str, str]] = {}


# ---------------------------------------------------------------------------
# Low-level request helper
# ---------------------------------------------------------------------------


def _api_get(session: requests.Session, path: str, **params) -> dict:
    """Make a JSON GET request against the Yahoo Fantasy v2 API."""
    url = f"{BASE_URL}/{path}"
    params["format"] = "json"
    resp = session.get(url, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()["fantasy_content"]


# ---------------------------------------------------------------------------
# League / metadata helpers
# ---------------------------------------------------------------------------


def get_current_game_key(session: requests.Session, sport: str = "mlb") -> str:
    """Return the game key for the current season of a sport (e.g. 'mlb')."""
    data = _api_get(session, f"game/{sport}")
    return str(data["game"][0]["game_key"])


def get_league_meta(session: requests.Session, league_key: str) -> dict:
    data = _api_get(session, f"league/{league_key}/metadata")
    return data["league"][0]


def get_current_week(session: requests.Session, league_key: str) -> int:
    meta = get_league_meta(session, league_key)
    return int(meta["current_week"])


_settings_cache: dict[str, dict] = {}


def _get_league_settings(session: requests.Session, league_key: str) -> list:
    """Fetch and cache raw league settings (list of blocks from Yahoo API)."""
    if league_key not in _settings_cache:
        data = _api_get(session, f"league/{league_key}/settings")
        _settings_cache[league_key] = data["league"][1]["settings"]
    return _settings_cache[league_key]


def get_league_stat_categories(session: requests.Session, league_key: str) -> dict[str, str]:
    """
    Return a mapping of stat_id → display name for this league's scoring categories.
    e.g. {"7": "R", "12": "HR", "26": "ERA", ...}
    Only returns enabled (scored) categories.
    """
    if league_key in _stat_categories_cache:
        return _stat_categories_cache[league_key]

    settings = _get_league_settings(session, league_key)
    stat_list = settings[0].get("stat_categories", {}).get("stats", [])

    cats = {}
    for s in stat_list:
        sc = s.get("stat", {})
        if sc.get("enabled") == 1 or sc.get("enabled") == "1":
            cats[str(sc["stat_id"])] = sc.get("display_name") or sc.get("abbr", str(sc["stat_id"]))

    _stat_categories_cache[league_key] = cats
    return cats


def get_division_names(session: requests.Session, league_key: str) -> dict[str, str]:
    """
    Return a mapping of division_id → division_name for this league.
    Returns {} if the league has no divisions configured.
    """
    settings = _get_league_settings(session, league_key)
    divs: dict[str, str] = {}
    for block in settings:
        if "divisions" in block:
            for d in block["divisions"]:
                div = d.get("division", {})
                did = str(div.get("division_id", ""))
                dname = div.get("name", "")
                if did and dname:
                    divs[did] = dname
    return divs


# ---------------------------------------------------------------------------
# Scoreboard / matchup results
# ---------------------------------------------------------------------------


def get_scoreboard(
    session: requests.Session, league_key: str, week: int
) -> list[dict]:
    """
    Return a list of matchup summaries for the given week.

    Each item:
      {
        "week": int,
        "teams": [
          {"name": str, "team_key": str, "points": float, "manager": str},
          ...
        ],
        "winner_key": str | None,   # None means tied
        "is_tied": bool,
        "is_playoffs": bool,
        "is_consolation": bool,
        "is_championship": bool,    # set by fetch_weekly_data after full scan
        "stat_winners": [{"stat_id": str, "is_tied": bool}, ...]
      }
    """
    data = _api_get(session, f"league/{league_key}/scoreboard;week={week}")
    raw_matchups = data["league"][1]["scoreboard"]["0"]["matchups"]

    matchups = []
    for i in range(int(raw_matchups["count"])):
        raw = raw_matchups[str(i)]["matchup"]
        # Teams are nested under raw["0"]["teams"] in the v2 API
        raw_teams_block = raw.get("0", raw)
        teams = []
        for j in range(int(raw_teams_block["teams"]["count"])):
            t = raw_teams_block["teams"][str(j)]["team"]
            info = t[0]  # list of dicts merged by Yahoo
            pts_block = t[1]

            # info is a list of single-key dicts; flatten it
            flat = {}
            for item in info:
                flat.update(item)

            manager_name = "Unknown"
            managers = flat.get("managers", [])
            if managers:
                m = managers[0].get("manager", {}) if isinstance(managers[0], dict) else {}
                manager_name = m.get("nickname") or m.get("manager_id", "Unknown")

            # Extract logo URL (Yahoo returns team_logos as a list of dicts)
            logo_url = ""
            for _logo_entry in flat.get("team_logos", []):
                _tl = _logo_entry.get("team_logo", {}) if isinstance(_logo_entry, dict) else {}
                logo_url = _tl.get("url", "")
                if logo_url:
                    break

            teams.append(
                {
                    "name": flat.get("name", f"Team {j}"),
                    "team_key": flat.get("team_key", ""),
                    "manager": manager_name,
                    "logo_url": logo_url,
                    "points": float(
                        pts_block.get("team_points", {}).get("total", 0)
                        or pts_block.get("team_projected_points", {}).get("total", 0)
                        or 0
                    ),
                    "category_stats": {},  # filled in by fetch_weekly_data
                }
            )

        is_tied = bool(int(raw.get("is_tied", 0)))
        winner_key = raw.get("winner_team_key") if not is_tied else None
        is_playoffs = bool(int(raw.get("is_playoffs", 0)))
        is_consolation = bool(int(raw.get("is_consolation", 0)))

        # Capture per-category winners from the scoreboard
        stat_winners = []
        for sw in raw.get("stat_winners", []):
            swdata = sw.get("stat_winner", {})
            stat_winners.append({
                "stat_id": str(swdata.get("stat_id", "")),
                "is_tied": bool(int(swdata.get("is_tied", 0))),
            })

        matchups.append(
            {
                "week": week,
                "teams": teams,
                "winner_key": winner_key,
                "is_tied": is_tied,
                "is_playoffs": is_playoffs,
                "is_consolation": is_consolation,
                "is_championship": False,  # set below in fetch_weekly_data
                "stat_winners": stat_winners,
            }
        )

    # Detect championship: exactly 1 non-consolation playoff matchup
    playoff_games = [m for m in matchups if m["is_playoffs"] and not m["is_consolation"]]
    if len(playoff_games) == 1:
        playoff_games[0]["is_championship"] = True

    return matchups


# ---------------------------------------------------------------------------
# Team category stats
# ---------------------------------------------------------------------------


def get_all_team_stats_week(
    session: requests.Session,
    team_keys: list[str],
    week: int,
    stat_categories: dict[str, str],
) -> dict[str, dict[str, str]]:
    """
    Batch-fetch weekly category stats for all given team keys.
    Returns: { team_key: { "HR": "8", "ERA": "2.14", ... } }
    """
    result: dict[str, dict[str, str]] = {}
    # Yahoo allows batching ~8 teams at a time
    batch_size = 8
    for start in range(0, len(team_keys), batch_size):
        batch = team_keys[start: start + batch_size]
        keys_param = ",".join(batch)
        try:
            data = _api_get(
                session,
                f"teams;team_keys={keys_param}/stats;type=week;week={week}",
            )
            teams_block = data["teams"]
            count = int(teams_block.get("count", 0))
            for i in range(count):
                t = teams_block[str(i)]["team"]
                # Extract team_key
                info_flat = {}
                for item in t[0]:
                    if isinstance(item, dict):
                        info_flat.update(item)
                tkey = info_flat.get("team_key", "")

                # Extract stats
                stats_list = t[1].get("team_stats", {}).get("stats", [])
                cat_stats: dict[str, str] = {}
                for s in stats_list:
                    sid = str(s["stat"]["stat_id"])
                    val = s["stat"].get("value", "-")
                    if sid in stat_categories:
                        cat_stats[stat_categories[sid]] = val if val not in (None, "") else "-"

                result[tkey] = cat_stats
        except Exception as e:
            print(f"  Warning: Could not fetch team stats for batch {batch}: {e}")

    return result


# ---------------------------------------------------------------------------
# Standings
# ---------------------------------------------------------------------------


def get_standings(session: requests.Session, league_key: str) -> list[dict]:
    """
    Return standings as a list ordered by rank:
      [{"rank": int, "name": str, "wins": int, "losses": int, "ties": int,
        "points_for": float, "points_against": float}, ...]
    """
    data = _api_get(session, f"league/{league_key}/standings")
    raw_teams = data["league"][1]["standings"][0]["teams"]

    standings = []
    for i in range(int(raw_teams["count"])):
        t = raw_teams[str(i)]["team"]
        info_list = t[0]
        stats_block = t[2] if len(t) > 2 else {}

        flat = {}
        for item in info_list:
            flat.update(item)

        team_standings = flat.get("team_standings", {})
        outcome = team_standings.get("outcome_totals", {})

        standings.append(
            {
                "rank": int(team_standings.get("rank", i + 1)),
                "name": flat.get("name", f"Team {i}"),
                "team_key": flat.get("team_key", ""),
                "division_id": str(flat.get("division_id", "")),
                "wins": int(outcome.get("wins", 0)),
                "losses": int(outcome.get("losses", 0)),
                "ties": int(outcome.get("ties", 0)),
                "points_for": float(team_standings.get("points_for", 0)),
                "points_against": float(team_standings.get("points_against", 0)),
            }
        )

    standings.sort(key=lambda x: x["rank"])
    return standings


# ---------------------------------------------------------------------------
# Transactions
# ---------------------------------------------------------------------------


def get_transactions(
    session: requests.Session, league_key: str, count: int = 25
) -> list[dict]:
    """
    Return recent add/drop/trade transactions.

    Each item:
      {
        "type": "add" | "drop" | "add/drop" | "trade",
        "timestamp": int,
        "players": [
          {"name": str, "action": "add" | "drop", "team": str}
        ]
      }
    """
    data = _api_get(
        session,
        f"league/{league_key}/transactions;types=add,drop,trade;count={count}",
    )
    raw = data["league"][1]["transactions"]

    # Pre-season / no transactions yet — API returns an empty list
    if isinstance(raw, list) or not raw:
        return []

    transactions = []
    for i in range(int(raw["count"])):
        tx = raw[str(i)]["transaction"]
        tx_meta = tx[0]
        tx_players = tx[1].get("players", {})

        players = []
        for j in range(int(tx_players.get("count", 0))):
            p = tx_players[str(j)]["player"]
            p_info = p[0]
            p_flat = {}
            for item in p_info:
                p_flat.update(item)

            tx_data = p[1].get("transaction_data", {})
            if isinstance(tx_data, list):
                tx_data = tx_data[0] if tx_data else {}

            # Destination team (where the player ended up)
            dest_team = (
                tx_data.get("destination_team_name")
                or tx_data.get("source_team_name")
                or "Free Agent"
            )

            players.append(
                {
                    "name": p_flat.get("full") or p_flat.get("name", {}).get("full", "Unknown"),
                    "action": tx_data.get("type", "unknown"),
                    "team": dest_team,
                    "position": p_flat.get("display_position", ""),
                }
            )

        transactions.append(
            {
                "type": tx_meta.get("type", "unknown"),
                "timestamp": int(tx_meta.get("timestamp", 0)),
                "players": players,
            }
        )

    return transactions


# ---------------------------------------------------------------------------
# Top player performances
# ---------------------------------------------------------------------------


def get_top_players_this_week(
    session: requests.Session,
    league_key: str,
    week: int,
    top_n: int = 10,
) -> list[dict]:
    """
    Fetch the top-scoring players (by fantasy points) for a given week.
    Uses the league's players;sort=PTS endpoint.

    Each item:
      {"name": str, "team": str, "position": str, "points": float}
    """
    data = _api_get(
        session,
        f"league/{league_key}/players;sort=PTS;sort_type=lastweek;start=0;count={top_n}/stats;type=week;week={week}",
    )

    players_block = data["league"][1].get("players", {})
    players = []
    for i in range(int(players_block.get("count", 0))):
        p = players_block[str(i)]["player"]
        p_info = p[0]
        p_flat = {}
        for item in p_info:
            p_flat.update(item)

        # Stats are in p[1]
        stats_block = p[1].get("player_points", {}) if len(p) > 1 else {}
        points = float(stats_block.get("total", 0))

        # Editorial team = real MLB team
        editorial_team = p_flat.get("editorial_team_full_name", "")

        players.append(
            {
                "name": p_flat.get("full") or p_flat.get("name", {}).get("full", "Unknown"),
                "mlb_team": editorial_team,
                "position": p_flat.get("display_position", ""),
                "points": points,
            }
        )

    players.sort(key=lambda x: x["points"], reverse=True)
    return players


# ---------------------------------------------------------------------------
# Draft results
# ---------------------------------------------------------------------------


def get_draft_results(session: requests.Session, league_key: str) -> list[dict]:
    """
    Return the full draft order for the league.

    Each item:
      {
        "pick":       int,   # overall pick number (1-based)
        "round":      int,
        "team_key":   str,
        "player_key": str,
        "player_name": str,
        "position":   str,   # display position (e.g. "SP", "OF", "1B")
        "mlb_team":   str,
      }
    """
    data = _api_get(session, f"league/{league_key}/draftresults")
    raw_picks = data["league"][1].get("draft_results", {}).get("0", {}).get("draft_results", {})

    # Yahoo returns draft_results as a dict with numeric string keys + "count"
    if isinstance(raw_picks, list) or not raw_picks:
        return []

    count = int(raw_picks.get("count", 0))
    picks = []
    for i in range(count):
        pick_data = raw_picks[str(i)].get("draft_result", {})
        picks.append({
            "pick":       int(pick_data.get("pick", i + 1)),
            "round":      int(pick_data.get("round", 0)),
            "team_key":   str(pick_data.get("team_key", "")),
            "player_key": str(pick_data.get("player_key", "")),
            # Name/position enriched separately via get_players_info
            "player_name": "",
            "position":    "",
            "mlb_team":    "",
        })

    return picks


def get_players_info(
    session: requests.Session,
    player_keys: list[str],
) -> dict[str, dict]:
    """
    Batch-fetch name, position, and MLB team for a list of player keys.
    Returns: { player_key: {"name": str, "position": str, "mlb_team": str} }
    Yahoo allows up to 25 player keys per request.
    """
    result: dict[str, dict] = {}
    batch_size = 25
    for start in range(0, len(player_keys), batch_size):
        batch = player_keys[start: start + batch_size]
        keys_param = ",".join(batch)
        try:
            data = _api_get(session, f"players;player_keys={keys_param}")
            players_block = data.get("players", {})
            count = int(players_block.get("count", 0))
            for i in range(count):
                p = players_block[str(i)]["player"]
                p_flat: dict = {}
                for item in p[0]:
                    if isinstance(item, dict):
                        p_flat.update(item)
                pkey = str(p_flat.get("player_key", ""))
                result[pkey] = {
                    "name":     p_flat.get("full") or p_flat.get("name", {}).get("full", "Unknown"),
                    "position": p_flat.get("display_position", ""),
                    "mlb_team": p_flat.get("editorial_team_full_name", ""),
                }
        except Exception as e:
            print(f"  Warning: Could not fetch player info for batch {batch}: {e}")

    return result


def get_draft_results_enriched(session: requests.Session, league_key: str) -> list[dict]:
    """
    Full draft board with player names, positions, and MLB teams resolved.
    Convenience wrapper around get_draft_results + get_players_info.
    """
    picks = get_draft_results(session, league_key)
    if not picks:
        return []

    player_keys = [p["player_key"] for p in picks if p["player_key"]]
    players_info = get_players_info(session, player_keys)

    for pick in picks:
        info = players_info.get(pick["player_key"], {})
        pick["player_name"] = info.get("name", "Unknown")
        pick["position"]    = info.get("position", "")
        pick["mlb_team"]    = info.get("mlb_team", "")

    return picks


# ---------------------------------------------------------------------------
# Main fetch function
# ---------------------------------------------------------------------------


def fetch_weekly_data(oauth: YahooOAuth, league_key: str, week: Optional[int] = None) -> dict:
    """
    Fetch all data needed for a weekly recap.
    If week is None, uses the previous completed week.
    """
    session = oauth.get_session()

    current = get_current_week(session, league_key)
    recap_week = week if week is not None else max(1, current - 1)

    print(f"  League: {league_key}")
    print(f"  Recapping week {recap_week} (current week: {current})")

    league_meta = get_league_meta(session, league_key)
    league_name = league_meta.get("name", "Fantasy League")
    end_week = int(league_meta.get("end_week", 0))

    print("  Fetching stat categories...")
    stat_categories = get_league_stat_categories(session, league_key)

    print("  Fetching scoreboard...")
    matchups = get_scoreboard(session, league_key, recap_week)

    print("  Fetching team category stats...")
    all_team_keys = [t["team_key"] for m in matchups for t in m["teams"] if t["team_key"]]
    team_stats = get_all_team_stats_week(session, all_team_keys, recap_week, stat_categories)

    # Enrich each team in each matchup with their category stats
    for m in matchups:
        for t in m["teams"]:
            t["category_stats"] = team_stats.get(t["team_key"], {})

    # If this is the last week of the season, identify the true championship
    # game by checking who won the non-consolation playoff games the prior week.
    # Those two winners face each other in the championship; the losers play
    # for 3rd place (also marked is_playoffs=1, is_consolation=0 by Yahoo).
    if recap_week == end_week and recap_week > 1:
        try:
            prev_matchups = get_scoreboard(session, league_key, recap_week - 1)
            semifinal_winners = {
                m["winner_key"]
                for m in prev_matchups
                if m.get("is_playoffs") and not m.get("is_consolation") and m.get("winner_key")
            }
            for m in matchups:
                if m.get("is_playoffs") and not m.get("is_consolation"):
                    team_keys = {t["team_key"] for t in m["teams"]}
                    if team_keys <= semifinal_winners:
                        m["is_championship"] = True
                    else:
                        m["is_third_place"] = True
        except Exception:
            # Fallback: mark all non-consolation playoff games as championship
            for m in matchups:
                if m.get("is_playoffs") and not m.get("is_consolation"):
                    m["is_championship"] = True

    print("  Fetching division info...")
    divisions = get_division_names(session, league_key)

    print("  Fetching standings...")
    standings = get_standings(session, league_key)
    for t in standings:
        t["division_name"] = divisions.get(t.get("division_id", ""), "")

    print("  Fetching transactions...")
    transactions = get_transactions(session, league_key, count=30)

    print("  Fetching top player performances...")
    try:
        top_players = get_top_players_this_week(session, league_key, recap_week, top_n=10)
    except Exception as e:
        print(f"  Warning: Could not fetch top players ({e}). Skipping.")
        top_players = []

    # Determine stat categories for lower-is-better context
    lower_is_better_names = {
        stat_categories.get(sid) for sid in _LOWER_IS_BETTER if sid in stat_categories
    }

    return {
        "league_name": league_name,
        "week": recap_week,
        "matchups": matchups,
        "standings": standings,
        "divisions": divisions,
        "transactions": transactions,
        "top_players": top_players,
        "stat_categories": stat_categories,
        "lower_is_better_stats": list(lower_is_better_names - {None}),
    }
