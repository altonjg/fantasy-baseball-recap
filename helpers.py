"""
helpers.py — Shared logic, data loaders, and display helpers.

Imported by both app.py (main dashboard) and pages/1_All_Time.py.
All @st.cache_data decorators work correctly when this module is imported
by a Streamlit app — the cache is shared across imports within the same session.
"""

from __future__ import annotations

import json
import os
import random
import re
import zlib as _zlib
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests
import streamlit as st

# ── Constants ─────────────────────────────────────────────────────────────────
DATA_ROOT = Path(__file__).parent / "data"
LOWER_IS_BETTER_DEFAULT = {"ERA", "WHIP"}

AWARD_DEFS = [
    ("🥇", "Champion",            "champion"),
    ("🥈", "Runner-Up",           "runner_up"),
    ("💀", "Wooden Spoon",        "wooden_spoon"),
    ("🔥", "Most Points For",     "most_pf"),
    ("🛡️", "Best Defense",        "best_defense"),
    ("📈", "Longest Win Streak",  "longest_win_streak"),
    ("📉", "Longest Lose Streak", "longest_lose_streak"),
    ("🍀", "Luckiest Team",       "luckiest"),
    ("😤", "Most Unlucky",        "most_unlucky"),
    ("👑", "Best Regular Season", "best_reg_season"),
    ("🎢", "Biggest Collapse",    "biggest_collapse"),
    ("⚡", "Hottest Finish",      "hottest_finish"),
    ("🧊", "Coldest Finish",      "coldest_finish"),
]

WRITER_STYLES: dict[str, dict] = {
    "passan": {
        "name": "Jeff Passan", "outlet": "ESPN",
        "voice": (
            "Write in Jeff Passan's style: urgent, authoritative breaking-news tone. "
            "Open with a declarative statement of fact. Use em-dashes liberally. "
            "Reference 'sources familiar with the situation.' Sharp, punchy sentences. "
            "Every sentence feels like it belongs in a push notification."
        ),
    },
    "heyman": {
        "name": "Jon Heyman", "outlet": "MLB Network",
        "voice": (
            "Write in Jon Heyman's style: blunt, telegraphic, tweet-like bursts of fact. "
            "Gets straight to the point immediately. Short declarative sentences. No fluff. "
            "Grades are blunt and opinionated. Lead with 'Sources:' or the key fact."
        ),
    },
    "rosenthal": {
        "name": "Ken Rosenthal", "outlet": "The Athletic",
        "voice": (
            "Write in Ken Rosenthal's style: measured, formal, old-school baseball journalism. "
            "Thorough historical context. Balanced, fair analysis of both sides. "
            "Dignified tone. Every sentence carries weight and credibility."
        ),
    },
    "olney": {
        "name": "Buster Olney", "outlet": "ESPN",
        "voice": (
            "Write in Buster Olney's style: analytical, even-handed, rich in historical context. "
            "Focus on team-building implications and long-term impact. "
            "Uses statistics naturally within prose. Thoughtful, measured conclusions."
        ),
    },
    "gammons": {
        "name": "Peter Gammons", "outlet": "MLB Network",
        "voice": (
            "Write in Peter Gammons's style: poetic, flowing prose with legendary gravitas. "
            "Draw historical comparisons. Lyrical and dramatic — make it feel like it matters forever. "
            "Long, beautiful sentences. This is the voice of baseball history itself."
        ),
    },
    "simmons": {
        "name": "Bill Simmons", "outlet": "The Ringer",
        "voice": (
            "Write in Bill Simmons's style: fan-first perspective with pop culture references "
            "and parenthetical asides (lots of them). Self-aware humor. Reference movies, TV, music. "
            "Trash talk is encouraged. Feels like a smart, opinionated friend texting about fantasy."
        ),
    },
}

_TRADE_WRITERS  = ["passan", "heyman"]
_RECAP_WRITERS  = ["rosenthal", "olney", "simmons"]
_PLAYOFF_WRITER = "gammons"


# ══════════════════════════════════════════════════════════════════════════════
# DISPLAY HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _team_color(name: str) -> str:
    """Stable, consistent HSL color for a team name (uses zlib for cross-run stability)."""
    hue = _zlib.crc32(name.encode("utf-8")) % 360
    return f"hsl({hue},52%,40%)"


def _team_initials(name: str) -> str:
    """Return 1–2 uppercase initials from a team name."""
    words = [w for w in name.split() if w and w[0].isalpha()]
    if len(words) >= 2:
        return (words[0][0] + words[1][0]).upper()
    return name[:2].upper() if name else "??"


def _badge_html(name: str, logo_url: str = "", size: int = 22) -> str:
    """Return an <img> (if logo_url) or a colored-circle initials badge."""
    if logo_url:
        return (
            f'<img src="{logo_url}" '
            f'style="width:{size}px;height:{size}px;border-radius:50%;'
            f'object-fit:cover;vertical-align:middle;flex-shrink:0;" '
            f'onerror="this.style.display=\'none\'">'
        )
    color    = _team_color(name)
    initials = _team_initials(name)
    return (
        f'<span class="team-badge" '
        f'style="width:{size}px;height:{size}px;background:{color};">'
        f'{initials}</span>'
    )


# ══════════════════════════════════════════════════════════════════════════════
# DATA LOADING
# ══════════════════════════════════════════════════════════════════════════════

def get_available_seasons() -> list[int]:
    """Return sorted list of season years that have any data."""
    if not DATA_ROOT.exists():
        return []
    seasons = []
    for d in DATA_ROOT.iterdir():
        if d.is_dir() and d.name.isdigit():
            has_weeks   = bool(list(d.glob("week_*.json")))
            has_draft   = (d / "draft_order.json").exists()
            has_preview = (d / "articles" / "season_preview.json").exists()
            if has_weeks or has_draft or has_preview:
                seasons.append(int(d.name))
    return sorted(seasons, reverse=True)


@st.cache_data(ttl=60)
def load_all_weeks(season: int) -> dict[int, dict]:
    """Load all week JSON files for a season. Returns {week_num: week_dict}."""
    weeks: dict[int, dict] = {}
    data_dir = DATA_ROOT / str(season)
    if not data_dir.exists():
        return weeks
    for f in sorted(data_dir.glob("week_*.json")):
        try:
            with open(f) as fp:
                d = json.load(fp)
            weeks[d["week"]] = d
        except Exception:
            pass
    return weeks


@st.cache_data(ttl=300)
def load_all_seasons_data() -> dict[int, dict[int, dict]]:
    """Load all weeks for every available season."""
    return {s: load_all_weeks(s) for s in get_available_seasons()}


@st.cache_data(ttl=3_600, show_spinner=False)
def load_divisions(season: int) -> dict[str, list[str]]:
    """Return {division_name: [team_names]} for the given season from data/divisions.json."""
    div_file = DATA_ROOT / "divisions.json"
    if not div_file.exists():
        return {}
    try:
        with open(div_file) as f:
            all_divs = json.load(f)
        return all_divs.get(str(season), {})
    except Exception:
        return {}


@st.cache_data(ttl=3_600, show_spinner=False)
def load_team_logos() -> dict[str, str]:
    """Return {team_name: logo_url} from data/team_logos.json (created by fetch_logos.py)."""
    logos_file = DATA_ROOT / "team_logos.json"
    if not logos_file.exists():
        return {}
    try:
        with open(logos_file) as f:
            return json.load(f)
    except Exception:
        return {}


# ══════════════════════════════════════════════════════════════════════════════
# STANDINGS RECONSTRUCTION
# ══════════════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=60)
def compute_standings(weeks_data_frozen: tuple, up_to_week: int) -> list[dict]:
    """
    Reconstruct standings from scratch by replaying all weeks up to up_to_week.
    Returns list sorted by wins desc, points_for desc. Each entry has 'rank'.
    """
    records: dict[str, dict] = {}
    for wk in sorted(k for k in dict(weeks_data_frozen) if k <= up_to_week):
        wd = dict(weeks_data_frozen)[wk]
        for m in wd.get("matchups", []):
            if len(m["teams"]) < 2:
                continue
            t1, t2 = m["teams"][0], m["teams"][1]
            for t in (t1, t2):
                if t["team_key"] not in records:
                    records[t["team_key"]] = {
                        "team_key": t["team_key"],
                        "name": t["name"],
                        "wins": 0, "losses": 0, "ties": 0,
                        "points_for": 0.0, "points_against": 0.0,
                    }
            r1, r2 = records[t1["team_key"]], records[t2["team_key"]]
            r1["points_for"]     += t1["points"]
            r1["points_against"] += t2["points"]
            r2["points_for"]     += t2["points"]
            r2["points_against"] += t1["points"]
            if m.get("is_tied"):
                r1["ties"] += 1; r2["ties"] += 1
            elif m.get("winner_key") == t1["team_key"]:
                r1["wins"] += 1; r2["losses"] += 1
            elif m.get("winner_key") == t2["team_key"]:
                r2["wins"] += 1; r1["losses"] += 1
    result = list(records.values())
    result.sort(key=lambda x: (-x["wins"], -x["points_for"]))
    for i, s in enumerate(result):
        s["rank"] = i + 1
    return result


# ══════════════════════════════════════════════════════════════════════════════
# STREAK COMPUTATION
# ══════════════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=60)
def compute_streaks(weeks_data_frozen: tuple) -> dict[str, dict]:
    weeks_data = dict(weeks_data_frozen)
    team_results: dict[str, list[str]] = {}
    team_names:   dict[str, str]       = {}

    for wk in sorted(weeks_data.keys()):
        for m in weeks_data[wk].get("matchups", []):
            if len(m["teams"]) < 2:
                continue
            t1, t2 = m["teams"][0], m["teams"][1]
            for t in (t1, t2):
                team_results.setdefault(t["team_key"], [])
                team_names[t["team_key"]] = t["name"]
            if m.get("is_tied"):
                team_results[t1["team_key"]].append("T")
                team_results[t2["team_key"]].append("T")
            elif m.get("winner_key") == t1["team_key"]:
                team_results[t1["team_key"]].append("W")
                team_results[t2["team_key"]].append("L")
            elif m.get("winner_key") == t2["team_key"]:
                team_results[t2["team_key"]].append("W")
                team_results[t1["team_key"]].append("L")

    result = {}
    for tkey, res in team_results.items():
        if not res:
            continue
        cur_type = res[-1]
        cur_len  = 0
        for r in reversed(res):
            if r == cur_type:
                cur_len += 1
            else:
                break
        max_win = max_lose = cur_w = cur_l = 0
        for r in res:
            if r == "W":
                cur_w += 1; cur_l = 0; max_win  = max(max_win,  cur_w)
            elif r == "L":
                cur_l += 1; cur_w = 0; max_lose = max(max_lose, cur_l)
            else:
                cur_w = cur_l = 0
        result[tkey] = {
            "name": team_names[tkey], "results": res,
            "current_streak": cur_len, "current_type": cur_type,
            "max_win_streak": max_win, "max_lose_streak": max_lose,
        }
    return result


# ══════════════════════════════════════════════════════════════════════════════
# LUCK RATINGS
# ══════════════════════════════════════════════════════════════════════════════

def compute_luck_ratings(weeks_data: dict[int, dict]) -> dict[str, float]:
    """Expected wins = fraction of teams beaten by score each week. Luck = actual - expected."""
    team_expected: dict[str, float] = {}
    for wk in sorted(weeks_data.keys()):
        all_teams = [t for m in weeks_data[wk].get("matchups", []) for t in m["teams"]]
        if len(all_teams) < 2:
            continue
        all_scores = [t["points"] for t in all_teams]
        n = len(all_scores)
        for t in all_teams:
            beaten = sum(1 for s in all_scores if s < t["points"])
            team_expected[t["name"]] = team_expected.get(t["name"], 0.0) + beaten / (n - 1)
    return team_expected


# ══════════════════════════════════════════════════════════════════════════════
# POWER RANKINGS
# ══════════════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=60)
def compute_power_rankings(weeks_data_frozen: tuple, standings_frozen: tuple) -> list[dict]:
    """
    Weighted power ranking score:
      40% recent form (last 3 weeks W%)
      30% season win%
      20% points-for percentile
      10% strength of schedule (avg opponent win%)
    Returns list sorted by pr_rank ascending, each entry includes rank_diff vs standings rank.
    """
    weeks_data = dict(weeks_data_frozen)
    standings  = list(standings_frozen)
    if not weeks_data or not standings:
        return []

    all_weeks = sorted(weeks_data.keys())

    # ── Recent form (last 3 weeks) ────────────────────────────────────────────
    recent_weeks = all_weeks[-3:] if len(all_weeks) >= 3 else all_weeks
    recent_rec: dict[str, dict] = {}
    for wk in recent_weeks:
        for m in weeks_data[wk].get("matchups", []):
            if len(m["teams"]) < 2:
                continue
            t1, t2 = m["teams"][0], m["teams"][1]
            for t in (t1, t2):
                recent_rec.setdefault(t["team_key"], {"name": t["name"], "wins": 0, "games": 0})
                recent_rec[t["team_key"]]["games"] += 1
            if m.get("winner_key") == t1["team_key"]:
                recent_rec[t1["team_key"]]["wins"] += 1
            elif m.get("winner_key") == t2["team_key"]:
                recent_rec[t2["team_key"]]["wins"] += 1

    # ── Win % map ─────────────────────────────────────────────────────────────
    win_pct_map: dict[str, float] = {}
    for s in standings:
        total = s["wins"] + s["losses"]
        win_pct_map[s["team_key"]] = s["wins"] / total if total else 0.0

    # ── Strength of Schedule ──────────────────────────────────────────────────
    team_opp: dict[str, list[str]] = {}
    for wk in all_weeks:
        for m in weeks_data[wk].get("matchups", []):
            if len(m["teams"]) < 2:
                continue
            t1k, t2k = m["teams"][0]["team_key"], m["teams"][1]["team_key"]
            team_opp.setdefault(t1k, []).append(t2k)
            team_opp.setdefault(t2k, []).append(t1k)

    sos_map: dict[str, float] = {
        tkey: (sum(win_pct_map.get(k, 0) for k in opps) / len(opps) if opps else 0.0)
        for tkey, opps in team_opp.items()
    }
    max_sos = max(sos_map.values(), default=1) or 1

    # ── PF percentile ─────────────────────────────────────────────────────────
    pf_vals  = [s["points_for"] for s in standings]
    min_pf   = min(pf_vals, default=0)
    pf_range = (max(pf_vals, default=1) - min_pf) or 1

    # ── Build ranked list ─────────────────────────────────────────────────────
    ranked = []
    for s in standings:
        tkey = s["team_key"]
        rec  = recent_rec.get(tkey, {})

        rf_score  = (rec["wins"] / rec["games"]) if rec.get("games") else win_pct_map.get(tkey, 0)
        wp_score  = win_pct_map.get(tkey, 0)
        pf_score  = (s["points_for"] - min_pf) / pf_range
        sos_score = sos_map.get(tkey, 0) / max_sos

        pr = rf_score * 0.40 + wp_score * 0.30 + pf_score * 0.20 + sos_score * 0.10

        rw = rec.get("wins", 0)
        rg = rec.get("games", 0)
        ranked.append({
            **s,
            "pr_score":    round(pr, 4),
            "recent_form": f"{rw}-{rg - rw}" if rg else "—",
            "sos":         round(sos_map.get(tkey, 0), 3),
        })

    ranked.sort(key=lambda x: x["pr_score"], reverse=True)
    for i, r in enumerate(ranked):
        r["pr_rank"]   = i + 1
        r["rank_diff"] = r["rank"] - r["pr_rank"]   # +N = rising, -N = falling

    return ranked


# ══════════════════════════════════════════════════════════════════════════════
# RIVALRY STATS
# ══════════════════════════════════════════════════════════════════════════════

def compute_rivalry_stats(all_seasons: dict) -> list[dict]:
    """
    Aggregate all-time head-to-head records for every matchup pair.
    Returns list sorted by games played desc.
    """
    rivalries: dict[tuple, dict] = {}
    for weeks_data in all_seasons.values():
        for wd in weeks_data.values():
            for m in wd.get("matchups", []):
                if len(m["teams"]) < 2:
                    continue
                t1, t2 = m["teams"][0], m["teams"][1]
                pair = tuple(sorted([t1["name"], t2["name"]]))
                if pair not in rivalries:
                    rivalries[pair] = {"team_a": pair[0], "team_b": pair[1],
                                       "games": 0, "a_wins": 0, "b_wins": 0, "ties": 0}
                r = rivalries[pair]
                r["games"] += 1
                if m.get("is_tied"):
                    r["ties"] += 1
                elif m.get("winner_key") == t1["team_key"]:
                    if t1["name"] == pair[0]:
                        r["a_wins"] += 1
                    else:
                        r["b_wins"] += 1
                elif m.get("winner_key") == t2["team_key"]:
                    if t2["name"] == pair[0]:
                        r["a_wins"] += 1
                    else:
                        r["b_wins"] += 1
    return sorted(rivalries.values(), key=lambda x: x["games"], reverse=True)


# ══════════════════════════════════════════════════════════════════════════════
# MLB STATS API  (free, no key required)
# ══════════════════════════════════════════════════════════════════════════════

_MLB_API    = "https://statsapi.mlb.com/api/v1"
_MLB_PHOTO  = "https://img.mlbstatic.com/mlb-photos/image/upload"
_GENERIC_HS = (f"{_MLB_PHOTO}/d_people:generic:headshot:67:current.png"
               f"/w_213,q_auto:best/v1/people/0/headshot/67/current")


@st.cache_data(ttl=86_400, show_spinner=False)
def mlb_search_player(name: str) -> int | None:
    """Return the MLB player ID for a name, or None if not found."""
    try:
        r = requests.get(f"{_MLB_API}/people/search",
                         params={"names": name, "sportId": 1}, timeout=5)
        r.raise_for_status()
        people = r.json().get("people", [])
        if people:
            return int(people[0]["id"])
    except Exception:
        pass
    return None


def mlb_headshot_url(player_id: int | None) -> str:
    if not player_id:
        return _GENERIC_HS
    return (f"{_MLB_PHOTO}/d_people:generic:headshot:67:current.png"
            f"/w_213,q_auto:best/v1/people/{player_id}/headshot/67/current")


@st.cache_data(ttl=3_600, show_spinner=False)
def mlb_player_stats(player_id: int, season: int, is_pitcher: bool = False) -> dict:
    """Fetch season-to-date stats from MLB Stats API."""
    group = "pitching" if is_pitcher else "hitting"
    try:
        r = requests.get(f"{_MLB_API}/people/{player_id}/stats",
                         params={"stats": "season", "group": group,
                                 "season": season, "sportId": 1}, timeout=5)
        r.raise_for_status()
        splits = r.json().get("stats", [{}])[0].get("splits", [])
        if splits:
            return splits[0].get("stat", {})
    except Exception:
        pass
    return {}


def _fmt_avg(raw) -> str:
    """Format batting average: '0.285' → '.285'"""
    s = str(raw)
    return s.lstrip("0") if "." in s else s


def mlb_stat_line(stats: dict, is_pitcher: bool) -> str:
    if not stats:
        return ""
    if is_pitcher:
        return (f"{stats.get('wins','—')}W  "
                f"{stats.get('era','—')} ERA  "
                f"{stats.get('strikeOuts','—')}K  "
                f"{stats.get('inningsPitched','—')}IP")
    return (f"{_fmt_avg(stats.get('avg','—'))} AVG  "
            f"{stats.get('homeRuns','—')}HR  "
            f"{stats.get('rbi','—')}RBI  "
            f"{stats.get('stolenBases','—')}SB")


def render_player_card(player: dict, season: int) -> str:
    """Return an HTML card string for a single top-performer."""
    name       = player.get("name", "Unknown")
    mlb_team   = player.get("mlb_team", "")
    pos        = player.get("position", "")
    pts        = float(player.get("points", 0))
    is_pitcher = any(p in pos for p in ("SP", "RP", "P"))

    pid      = mlb_search_player(name)
    hs_url   = mlb_headshot_url(pid)
    stats    = mlb_player_stats(pid, season, is_pitcher) if pid else {}
    stat_ln  = mlb_stat_line(stats, is_pitcher)

    pts_color = "#22c55e" if pts >= 8 else ("#f0c040" if pts >= 5 else "#8a9bb5")

    return f"""
<div style="background:#111e35;border:1px solid #1a2d4a;border-radius:14px;
            padding:14px 10px;text-align:center;height:100%;
            box-shadow:0 2px 10px rgba(0,0,0,0.35);">
  <img src="{hs_url}"
       style="width:76px;height:76px;border-radius:50%;object-fit:cover;
              border:3px solid #f0c040;background:#0d1f38;"
       onerror="this.src='{_GENERIC_HS}'">
  <div style="font-weight:700;font-size:0.92em;margin:8px 0 2px;line-height:1.2;color:#e8edf5">{name}</div>
  <div style="font-size:0.76em;color:#8a9bb5;margin-bottom:6px">{mlb_team}&nbsp;·&nbsp;{pos}</div>
  <div style="font-size:1.1em;font-weight:800;color:{pts_color}">{pts:.0f}&nbsp;cat wins</div>
  <div style="font-size:0.72em;color:#8a9bb5;margin-top:5px;line-height:1.5">{stat_ln}</div>
</div>"""


# ══════════════════════════════════════════════════════════════════════════════
# TRADE WIRE — Claude API article generation
# ══════════════════════════════════════════════════════════════════════════════

def _get_anthropic_key() -> str | None:
    try:
        return st.secrets["ANTHROPIC_API_KEY"]
    except Exception:
        return os.getenv("ANTHROPIC_API_KEY")


def generate_trade_article(trade_tx: dict, standings: list[dict]) -> dict | None:
    """
    Generate a trade article via Claude API using a randomly selected writer persona.
    Returns article dict or None on failure.
    """
    api_key = _get_anthropic_key()
    if not api_key:
        return None

    try:
        import anthropic
    except ImportError:
        st.error("anthropic package not installed.")
        return None

    players = trade_tx.get("players", [])
    if not players:
        return None

    writer_key  = random.choice(_TRADE_WRITERS)
    writer      = WRITER_STYLES[writer_key]
    writer_name = writer["name"]
    writer_out  = writer["outlet"]

    team_names_in_trade = list({p.get("team", "") for p in players
                                if p.get("team") and p.get("team") != "Free Agent"})
    team_a = team_names_in_trade[0] if len(team_names_in_trade) > 0 else "Team A"
    team_b = team_names_in_trade[1] if len(team_names_in_trade) > 1 else "Team B"

    def side_players(team: str) -> list[str]:
        return [f"{p['name']} ({p.get('position','?')})" for p in players if p.get("team") == team]

    team_a_gets      = side_players(team_a)
    team_b_gets      = side_players(team_b)
    all_player_names = ", ".join(f"{p['name']} ({p.get('position','?')})" for p in players)

    standings_ctx = "\n".join(
        f"  {s['name']}: {s['wins']}-{s['losses']} ({s.get('points_for', 0):.0f} PF)"
        for s in standings[:8]
    ) if standings else "  (pre-season — no games played yet)"

    prompt = f"""You are {writer_name} of {writer_out}, writing a breaking news trade article for a 14-team fantasy baseball league called "MillerLite® BeerLeagueBaseball."

{writer["voice"]}

TRADE DETAILS:
{team_a} receives: {', '.join(team_a_gets) if team_a_gets else 'undisclosed'}
{team_b} receives: {', '.join(team_b_gets) if team_b_gets else 'undisclosed'}
All players involved: {all_player_names}

CURRENT STANDINGS (top 8):
{standings_ctx}

Write a trade wire article (220–300 words) that includes:
1. A punchy breaking-news headline — name the players, reference BeerLeague
2. Opening that matches {writer_name}'s authentic voice and style
3. Analysis of what each team is getting and the strategic logic behind the deal
4. A clear verdict on who wins the trade with specific reasoning
5. Trade grades for each side on an A+ through F scale

Respond ONLY with valid JSON in this exact shape — no markdown fences:
{{
  "headline": "...",
  "body": "...(full article, use **bold** for player names, markdown OK)...",
  "grade_team_a": "B+",
  "grade_team_b": "A-",
  "team_a": "{team_a}",
  "team_b": "{team_b}"
}}"""

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        msg = client.messages.create(
            model="claude-opus-4-5",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = msg.content[0].text.strip()
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)

        article = json.loads(raw)
        article["generated_at"]          = datetime.now().isoformat()
        article["transaction_timestamp"] = trade_tx.get("timestamp", 0)
        article["writer_key"]            = writer_key
        article["writer_name"]           = writer_name
        article["writer_outlet"]         = writer_out
        return article
    except Exception as e:
        st.error(f"Article generation failed: {e}")
        return None


def generate_weekly_recap_article(week_data: dict, standings: list[dict],
                                   is_playoff: bool = False,
                                   is_championship: bool = False) -> dict | None:
    """
    Generate a narrative weekly recap article via Claude API.
    Uses a rotating cast of writers — Gammons for championship/playoff weeks,
    random from _RECAP_WRITERS for regular season.
    Returns article dict or None on failure.
    """
    api_key = _get_anthropic_key()
    if not api_key:
        return None

    try:
        import anthropic
    except ImportError:
        st.error("anthropic package not installed.")
        return None

    if is_championship:
        writer_key = _PLAYOFF_WRITER
    elif is_playoff:
        writer_key = random.choice([_PLAYOFF_WRITER] + _RECAP_WRITERS)
    else:
        writer_key = random.choice(_RECAP_WRITERS)

    writer      = WRITER_STYLES[writer_key]
    writer_name = writer["name"]
    writer_out  = writer["outlet"]

    matchups   = week_data.get("matchups", [])
    week_num   = week_data.get("week", "?")
    league     = week_data.get("league_name", "MillerLite® BeerLeagueBaseball")

    matchup_lines = []
    for m in matchups:
        teams = m.get("teams", [])
        if len(teams) < 2:
            continue
        t1, t2   = teams[0], teams[1]
        label    = "[CHAMPIONSHIP] " if m.get("is_championship") else \
                   "[PLAYOFF] "      if m.get("is_playoffs") and not m.get("is_consolation") else \
                   "[CONSOLATION] "  if m.get("is_consolation") else ""
        if m.get("is_tied"):
            matchup_lines.append(f"  {label}TIE: {t1['name']} {t1['points']:.1f} vs {t2['name']} {t2['points']:.1f}")
        else:
            winner = t1 if t1.get("team_key") == m.get("winner_key") else t2
            loser  = t2 if winner is t1 else t1
            matchup_lines.append(
                f"  {label}{winner['name']} def. {loser['name']} "
                f"({winner['points']:.1f}–{loser['points']:.1f})"
            )

    standings_ctx = "\n".join(
        f"  {s['rank']}. {s['name']}: {s['wins']}-{s['losses']} ({s.get('points_for', 0):.0f} PF)"
        for s in standings[:10]
    ) if standings else "  (standings unavailable)"

    top_players    = week_data.get("top_players", [])
    top_player_ctx = "\n".join(
        f"  {p['name']} ({p.get('position','?')}, {p.get('mlb_team','?')}): {p.get('points',0):.1f} pts"
        for p in top_players[:5]
    ) if top_players else ""

    week_type = "CHAMPIONSHIP" if is_championship else "PLAYOFF" if is_playoff else "regular season"

    prompt = f"""You are {writer_name} of {writer_out}, writing a weekly column for the fantasy baseball league "{league}."

{writer["voice"]}

WEEK {week_num} ({week_type.upper()}) RESULTS:
{chr(10).join(matchup_lines)}

CURRENT STANDINGS (top 10):
{standings_ctx}

{"TOP FANTASY PERFORMERS THIS WEEK:" + chr(10) + top_player_ctx if top_player_ctx else ""}

Write a weekly recap column (350–500 words) in {writer_name}'s authentic voice that:
1. Opens with the most compelling storyline of the week
2. Covers 2–3 matchups in depth with genuine analysis
3. Mentions standout individual performances where relevant
4. Includes a brief standings note about the playoff/title race
5. Ends with a tease of what's next

Use **bold** for team names. Markdown is OK. Write as if this is published on {writer_out}.

Respond ONLY with valid JSON — no markdown fences:
{{
  "headline": "...",
  "subheadline": "...(one-sentence deck/teaser)...",
  "body": "...(full column)..."
}}"""

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        msg = client.messages.create(
            model="claude-opus-4-5",
            max_tokens=1500,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = msg.content[0].text.strip()
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)

        article = json.loads(raw)
        article["generated_at"]    = datetime.now().isoformat()
        article["week"]            = week_num
        article["writer_key"]      = writer_key
        article["writer_name"]     = writer_name
        article["writer_outlet"]   = writer_out
        article["is_playoff"]      = is_playoff
        article["is_championship"] = is_championship
        return article
    except Exception as e:
        st.error(f"Recap article generation failed: {e}")
        return None


def save_recap_article(article: dict, articles_dir: Path) -> Path | None:
    """Write recap article JSON to disk. Returns the path or None on failure."""
    try:
        articles_dir.mkdir(parents=True, exist_ok=True)
        week = article.get("week", "00")
        path = articles_dir / f"week_{int(week):02d}_recap.json"
        with open(path, "w") as f:
            json.dump(article, f, indent=2)
        return path
    except Exception:
        return None


def save_trade_article(article: dict, trades_dir: Path) -> Path | None:
    """Write trade article JSON to disk. Returns the path or None on failure."""
    try:
        trades_dir.mkdir(parents=True, exist_ok=True)
        ts   = article.get("transaction_timestamp", 0) or int(datetime.now().timestamp())
        path = trades_dir / f"trade_{ts}.json"
        with open(path, "w") as f:
            json.dump(article, f, indent=2)
        return path
    except Exception:
        return None


# ══════════════════════════════════════════════════════════════════════════════
# SEASON AWARDS
# ══════════════════════════════════════════════════════════════════════════════

def is_season_complete(weeks_data: dict[int, dict]) -> bool:
    if not weeks_data:
        return False
    last_wk = max(weeks_data.keys())
    return any(m.get("is_championship") for m in weeks_data[last_wk].get("matchups", []))


def compute_season_awards(weeks_data: dict[int, dict]) -> dict:
    if not weeks_data:
        return {}
    all_weeks    = sorted(weeks_data.keys())
    last_week    = max(all_weeks)
    weeks_frozen = tuple(sorted(weeks_data.items()))
    final_st     = compute_standings(weeks_frozen, last_week)
    if not final_st:
        return {}

    awards: dict[str, dict] = {}

    awards["champion"]     = {"name": final_st[0]["name"]}
    if len(final_st) > 1:
        awards["runner_up"] = {"name": final_st[1]["name"]}
    awards["wooden_spoon"] = {
        "name":  final_st[-1]["name"],
        "value": f"{final_st[-1]['wins']}-{final_st[-1]['losses']}",
    }

    most_pf  = max(final_st, key=lambda x: x["points_for"])
    best_def = min(final_st, key=lambda x: x["points_against"])
    awards["most_pf"]      = {"name": most_pf["name"],  "value": f"{most_pf['points_for']:.1f} PF"}
    awards["best_defense"] = {"name": best_def["name"], "value": f"{best_def['points_against']:.1f} PA"}

    streaks = compute_streaks(weeks_frozen)
    if streaks:
        mw = max(streaks.values(), key=lambda x: x["max_win_streak"])
        ml = max(streaks.values(), key=lambda x: x["max_lose_streak"])
        awards["longest_win_streak"]  = {"name": mw["name"], "value": f"{mw['max_win_streak']} in a row"}
        awards["longest_lose_streak"] = {"name": ml["name"], "value": f"{ml['max_lose_streak']} in a row"}

    expected    = compute_luck_ratings(weeks_data)
    actual_wins = {s["name"]: s["wins"] for s in final_st}
    luck_delta  = {name: round(actual_wins.get(name, 0) - exp, 2) for name, exp in expected.items()}
    if luck_delta:
        luckiest   = max(luck_delta, key=luck_delta.get)
        unluckiest = min(luck_delta, key=luck_delta.get)
        awards["luckiest"]     = {"name": luckiest,   "value": f"+{luck_delta[luckiest]:.1f} luck"}
        awards["most_unlucky"] = {"name": unluckiest, "value": f"{luck_delta[unluckiest]:.1f} luck"}

    rs_end = last_week
    for wk in all_weeks:
        if any(m.get("is_playoffs") for m in weeks_data[wk].get("matchups", [])):
            rs_end = wk - 1
            break
    rs_st = compute_standings(weeks_frozen, rs_end)
    if rs_st:
        awards["best_reg_season"] = {
            "name":  rs_st[0]["name"],
            "value": f"{rs_st[0]['wins']}-{rs_st[0]['losses']} reg season",
        }

    hot_records: dict[str, dict] = {}
    for wk in range(max(1, last_week - 3), last_week + 1):
        if wk not in weeks_data:
            continue
        for m in weeks_data[wk].get("matchups", []):
            if len(m["teams"]) < 2:
                continue
            t1, t2 = m["teams"][0], m["teams"][1]
            for t in (t1, t2):
                hot_records.setdefault(t["name"], {"wins": 0, "losses": 0})
            if m.get("winner_key") == t1["team_key"]:
                hot_records[t1["name"]]["wins"]   += 1
                hot_records[t2["name"]]["losses"] += 1
            elif m.get("winner_key") == t2["team_key"]:
                hot_records[t2["name"]]["wins"]   += 1
                hot_records[t1["name"]]["losses"] += 1
    if hot_records:
        hottest = max(hot_records, key=lambda n: hot_records[n]["wins"])
        coldest = min(hot_records, key=lambda n: hot_records[n]["wins"])
        awards["hottest_finish"] = {
            "name":  hottest,
            "value": f"{hot_records[hottest]['wins']}-{hot_records[hottest]['losses']} last 4 wks",
        }
        awards["coldest_finish"] = {
            "name":  coldest,
            "value": f"{hot_records[coldest]['wins']}-{hot_records[coldest]['losses']} last 4 wks",
        }

    mid_wk  = all_weeks[len(all_weeks) // 2]
    mid_st  = compute_standings(weeks_frozen, mid_wk)
    if mid_st:
        mid_rank   = {s["name"]: s["rank"] for s in mid_st}
        final_rank = {s["name"]: s["rank"] for s in final_st}
        top_half   = len(mid_st) // 2
        collapses  = [
            (name, final_rank.get(name, 99) - mid_rank[name], mid_rank[name])
            for name in mid_rank if name in final_rank and mid_rank[name] <= top_half
        ]
        if collapses:
            worst = max(collapses, key=lambda x: x[1])
            if worst[1] > 0:
                awards["biggest_collapse"] = {
                    "name":  worst[0],
                    "value": f"Rank {worst[2]} → {final_rank.get(worst[0], '?')}",
                }

    return awards


# ══════════════════════════════════════════════════════════════════════════════
# WEEKLY AWARDS
# ══════════════════════════════════════════════════════════════════════════════

def compute_weekly_awards(week_data: dict, weeks_data: dict[int, dict]) -> list[dict]:
    awards   = []
    matchups = week_data.get("matchups", [])
    cur_week = week_data.get("week", 0)
    if not matchups:
        return awards

    all_teams  = [t for m in matchups for t in m["teams"]]
    all_scores = [t["points"] for t in all_teams]
    week_avg   = sum(all_scores) / len(all_scores) if all_scores else 0

    if all_teams:
        hot = max(all_teams, key=lambda t: t["points"])
        awards.append({"badge": "🔥 Hot Hand", "color": "badge-gold",
                       "winner": hot["name"], "detail": f"{hot['points']:.0f} cats won"})

    for m in matchups:
        if len(m["teams"]) < 2 or not m.get("winner_key") or m.get("is_tied"):
            continue
        winner = next((t for t in m["teams"] if t["team_key"] == m["winner_key"]), None)
        if winner and winner["points"] < week_avg:
            awards.append({"badge": "🍀 Lucky Win", "color": "badge-green",
                           "winner": winner["name"],
                           "detail": f"{winner['points']:.0f} cats (avg {week_avg:.0f})"})
            break

    prior_avgs: dict[str, float]  = {}
    prior_counts: dict[str, int]  = {}
    for wk, wd in weeks_data.items():
        if wk >= cur_week:
            continue
        for m2 in wd.get("matchups", []):
            for t in m2.get("teams", []):
                prior_avgs[t["name"]]   = prior_avgs.get(t["name"], 0) + t["points"]
                prior_counts[t["name"]] = prior_counts.get(t["name"], 0) + 1
    season_avgs = {n: prior_avgs[n] / prior_counts[n] for n in prior_avgs if prior_counts[n] > 0}

    trap_candidate, trap_gap = None, 0
    for m in matchups:
        if len(m["teams"]) < 2 or not m.get("winner_key") or m.get("is_tied"):
            continue
        loser  = next((t for t in m["teams"] if t["team_key"] != m["winner_key"]), None)
        winner = next((t for t in m["teams"] if t["team_key"] == m["winner_key"]), None)
        if loser and winner:
            la = season_avgs.get(loser["name"],  0)
            wa = season_avgs.get(winner["name"], 0)
            if la > wa and (la - wa) > trap_gap:
                trap_gap, trap_candidate = la - wa, loser["name"]
    if trap_candidate:
        awards.append({"badge": "💀 Trap Game", "color": "badge-red",
                       "winner": trap_candidate, "detail": "Lost despite being favored"})

    weeks_frozen = tuple(sorted(weeks_data.items()))
    standings    = compute_standings(weeks_frozen, cur_week - 1) if cur_week > 1 else []
    if standings:
        rank_map = {s["name"]: s["rank"] for s in standings}
        mid_rank = len(standings) // 2
        for m in matchups:
            if len(m["teams"]) < 2 or not m.get("winner_key") or m.get("is_tied"):
                continue
            loser  = next((t for t in m["teams"] if t["team_key"] != m["winner_key"]), None)
            winner = next((t for t in m["teams"] if t["team_key"] == m["winner_key"]), None)
            if loser and winner:
                lr = rank_map.get(loser["name"],  99)
                wr = rank_map.get(winner["name"], 99)
                if lr <= mid_rank and wr > mid_rank:
                    awards.append({"badge": "📉 Choker", "color": "badge-blue",
                                   "winner": loser["name"],
                                   "detail": "Top-half team upset by bottom-half"})
                    break
    return awards


# ══════════════════════════════════════════════════════════════════════════════
# ALL-TIME STATS
# ══════════════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=300)
def compute_alltime_stats(all_seasons_frozen: tuple) -> dict:
    all_seasons = dict(all_seasons_frozen)
    team_stats:        dict[str, dict] = {}
    season_awards_map: dict[int, dict] = {}

    for season, weeks_data_frozen in sorted(all_seasons.items()):
        if not weeks_data_frozen:
            continue
        weeks_data = dict(weeks_data_frozen)
        wf         = weeks_data_frozen
        last_wk    = max(weeks_data.keys())
        final_st   = compute_standings(wf, last_wk)

        sa = compute_season_awards(weeks_data)
        season_awards_map[season] = sa

        for s in final_st:
            name = s["name"]
            if name not in team_stats:
                team_stats[name] = {
                    "name": name, "seasons": 0,
                    "wins": 0, "losses": 0, "ties": 0,
                    "points_for": 0.0, "points_against": 0.0,
                    "championships": 0, "finals": 0, "wooden_spoons": 0,
                    "best_finish": 99, "season_finishes": {},
                }
            ts = team_stats[name]
            ts["seasons"]        += 1
            ts["wins"]           += s["wins"]
            ts["losses"]         += s["losses"]
            ts["ties"]           += s.get("ties", 0)
            ts["points_for"]     += s["points_for"]
            ts["points_against"] += s["points_against"]
            ts["best_finish"]     = min(ts["best_finish"], s["rank"])
            ts["season_finishes"][season] = s["rank"]
            if s["rank"] == 1:             ts["championships"] += 1
            if s["rank"] <= 2:             ts["finals"]        += 1
            if s["rank"] == len(final_st): ts["wooden_spoons"] += 1

    for ts in team_stats.values():
        total = ts["wins"] + ts["losses"]
        ts["win_pct"] = round(ts["wins"] / total, 3) if total else 0.0

    return {"teams": team_stats, "season_awards": season_awards_map}


# ══════════════════════════════════════════════════════════════════════════════
# MISC HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def get_winner(matchup: dict) -> dict | None:
    if matchup.get("is_tied") or not matchup.get("winner_key"):
        return None
    return next((t for t in matchup["teams"] if t["team_key"] == matchup["winner_key"]), None)


def category_winner(v1, v2, cat: str, lower_is_better: set[str]) -> str:
    try:
        f1, f2 = float(v1), float(v2)
        if f1 == f2: return "tie"
        if cat in lower_is_better: return "←" if f1 < f2 else "→"
        return "←" if f1 > f2 else "→"
    except (TypeError, ValueError):
        return ""


def build_category_df(t1: dict, t2: dict, lower_is_better: set[str]) -> "pd.DataFrame":
    cats1, cats2 = t1.get("category_stats", {}), t2.get("category_stats", {})
    rows = []
    for cat in sorted(set(cats1) | set(cats2)):
        v1, v2 = cats1.get(cat, "–"), cats2.get(cat, "–")
        rows.append({"Category": cat, t1["name"]: v1,
                     "Winner": category_winner(v1, v2, cat, lower_is_better), t2["name"]: v2})
    return pd.DataFrame(rows)


def week_label(w: int, data: dict) -> str:
    is_champ   = any(m.get("is_championship") for m in data.get("matchups", []))
    is_playoff = any(m.get("is_playoffs") and not m.get("is_consolation")
                     for m in data.get("matchups", []))
    suffix = " 🏆" if is_champ else (" 🥊" if is_playoff else "")
    return f"Week {w}{suffix}"


def render_award_card(awards: dict, season: int) -> None:
    """Render a season awards card as a single HTML block (avoids white-bar bug)."""
    html = (
        f'<div class="trophy-section">'
        f'<div style="font-size:1.2em;font-weight:800;color:#f0c040;margin-bottom:10px;">'
        f'🏆 {season} Season Awards</div>'
    )
    for icon, label, key in AWARD_DEFS:
        a = awards.get(key)
        if not a:
            continue
        value_str = a.get("value", "")
        html += (
            f'<div class="award-row">'
            f'<span class="award-icon">{icon}</span>'
            f'<span class="award-label">{label}</span>'
            f'<span class="award-winner">{a["name"]}</span>'
            f'<span class="award-value">{value_str}</span>'
            f'</div>'
        )
    html += '</div>'
    st.markdown(html, unsafe_allow_html=True)


def render_weekly_award_badges(awards: list[dict]) -> None:
    if not awards:
        st.caption("No awards data for this week.")
        return
    html = ""
    for a in awards:
        html += f'<span class="badge {a["color"]}">{a["badge"]} {a["winner"]}</span> '
        html += f'<span style="font-size:0.8em;color:#8a9bb5;">{a["detail"]}</span><br>'
    st.markdown(html, unsafe_allow_html=True)
