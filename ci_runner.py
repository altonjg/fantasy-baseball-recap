"""
CI automation runner for BeerLeagueBaseball.

Designed to be called by GitHub Actions on two schedules:
  - Every 4 hours: fetch data, detect new trades → generate trade articles
  - Monday 11am UTC: generate weekly recap article + data snapshot

Usage:
    python ci_runner.py --mode trades    # trade detection only
    python ci_runner.py --mode recap     # weekly recap (typically Monday)
    python ci_runner.py --mode full      # both (default)
    python ci_runner.py --week 12        # override week number

Environment variables required (set as GitHub Actions secrets):
    YAHOO_CLIENT_ID
    YAHOO_CLIENT_SECRET
    YAHOO_REFRESH_TOKEN
    YAHOO_LEAGUE_KEY      e.g. "458.l.123456"
    ANTHROPIC_API_KEY

Optional:
    DISCORD_WEBHOOK_URL   Discord incoming webhook URL — posts recap, trade, and preview articles
    STREAMLIT_APP_URL     Public URL of the dashboard — linked from Discord embeds
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
from datetime import datetime
from pathlib import Path

# Force UTF-8 for stdout/stderr — GitHub Actions runners default to ASCII
# which chokes on any non-ASCII character in team names, player names, or prompts.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ── Bootstrap path so we can import local modules ─────────────────────────────
sys.path.insert(0, str(Path(__file__).parent))

from ci_auth import setup_ci_oauth
from yahoo_client import (
    fetch_next_week_schedule,
    fetch_weekly_data,
    get_draft_results_enriched,
    get_league_meta,
)
try:
    from mlb_stats import enrich_top_players, week_date_range
    _MLB_STATS_AVAILABLE = True
except ImportError:
    _MLB_STATS_AVAILABLE = False

# Writer pools — mirrors app.py so both stay in sync
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

DATA_ROOT = Path(__file__).parent / "data"


# ── Anthropic helpers ─────────────────────────────────────────────────────────

def _anthropic_client():
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise EnvironmentError(
            "ANTHROPIC_API_KEY not set. Add it as a GitHub Actions secret."
        )
    import anthropic
    return anthropic.Anthropic(api_key=api_key)


def _call_claude(prompt: str, max_tokens: int = 1024, model: str = "claude-sonnet-4-6",
                 precommit_facts: str | None = None) -> str:
    """Call Claude. If precommit_facts is provided, use a multi-turn conversation
    where Claude first confirms the facts before writing — prevents hallucination."""
    client = _anthropic_client()
    if precommit_facts:
        messages = [
            {"role": "user", "content": (
                f"Before we begin, confirm the following VERIFIED FACTS by repeating them back "
                f"exactly as stated:\n\n{precommit_facts}"
            )},
            {"role": "assistant", "content": f"Confirmed. {precommit_facts}"},
            {"role": "user", "content": prompt},
        ]
    else:
        messages = [{"role": "user", "content": prompt}]
    msg = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        messages=messages,
    )
    raw = msg.content[0].text.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    return raw


def _fix_json_strings(raw: str) -> str:
    """Escape literal newlines/tabs inside JSON string values (Claude sometimes emits them)."""
    result: list[str] = []
    in_string = False
    i = 0
    while i < len(raw):
        c = raw[i]
        if c == "\\" and in_string:
            result.append(c)
            if i + 1 < len(raw):
                i += 1
                result.append(raw[i])
        elif c == '"':
            in_string = not in_string
            result.append(c)
        elif in_string and c == "\n":
            result.append("\\n")
        elif in_string and c == "\r":
            result.append("\\r")
        elif in_string and c == "\t":
            result.append("\\t")
        else:
            result.append(c)
        i += 1
    return "".join(result)


def _safe_json_parse(raw: str) -> dict:
    """
    Attempt to parse JSON from Claude's response.
    Falls back to repairing literal control chars in strings, then extracting
    the first {...} block — handles Claude's occasional formatting quirks.
    """
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Fix literal newlines/tabs inside JSON strings and retry
        fixed = _fix_json_strings(raw)
        try:
            return json.loads(fixed)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", fixed, re.DOTALL)
            if match:
                return json.loads(match.group())
            raise


# ── Season history helpers ────────────────────────────────────────────────────

_SEASON_HISTORY_TEMPLATE: dict = {
    "power_rankings": {},
    "weekly_points": {},
    "manager_spotlight_rotation": [],
    "last_spotlight_week": None,
}

_RECORDS_LOWER_IS_BETTER = {"lowest_era_winner"}


def _load_season_history(season: int) -> dict:
    path = DATA_ROOT / str(season) / "season_history.json"
    if path.exists():
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    import copy
    return copy.deepcopy(_SEASON_HISTORY_TEMPLATE)


def _save_season_history(season: int, data: dict) -> None:
    path = DATA_ROOT / str(season) / "season_history.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _load_records(season: int) -> dict:
    path = DATA_ROOT / str(season) / "records.json"
    if path.exists():
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_records(season: int, data: dict) -> None:
    path = DATA_ROOT / str(season) / "records.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _parse_cat_stat(key: str, value: str) -> float:
    """Parse a category stat string to float. Returns -1 on failure."""
    try:
        if key == "H/AB":
            parts = str(value).split("/")
            if len(parts) == 2 and int(parts[1]) > 0:
                return int(parts[0]) / int(parts[1])
            return 0.0
        return float(value)
    except (ValueError, ZeroDivisionError):
        return -1.0


def _check_and_update_records(
    week_data: dict, week_num: int, records: dict
) -> tuple[dict, list[dict]]:
    """
    Compare current week stats against stored records.
    Returns (updated_records, broken_records_list).
    broken_records entries: {record, new_value, team, prev_value, prev_team, prev_week}
    """
    broken: list[dict] = []

    def _update(key: str, value: float, team: str, higher: bool) -> None:
        if value < 0:
            return
        current = records.get(key)
        is_better = (value > current["value"]) if higher else (value < current["value"])
        if current is None or is_better:
            if current is not None and is_better:
                broken.append({
                    "record": key,
                    "new_value": value,
                    "team": team,
                    "prev_value": current["value"],
                    "prev_team": current["team"],
                    "prev_week": current["week"],
                })
            records[key] = {"value": value, "team": team, "week": week_num}

    for m in week_data.get("matchups", []):
        winner_key = m.get("winner_key")
        for t in m.get("teams", []):
            name = t.get("name", "")
            stats = t.get("category_stats", {})
            pts = float(t.get("points", 0.0))
            is_winner = (t.get("team_key") == winner_key) and not m.get("is_tied")

            _update("most_category_wins", pts, name, higher=True)
            _update("most_hr_team", _parse_cat_stat("HR", stats.get("HR", "-1")), name, higher=True)
            _update("highest_obp", _parse_cat_stat("OBP", stats.get("OBP", "-1")), name, higher=True)
            _update("most_sb", _parse_cat_stat("SB", stats.get("SB", "-1")), name, higher=True)
            _update("most_rbi", _parse_cat_stat("RBI", stats.get("RBI", "-1")), name, higher=True)
            _update("most_k_team", _parse_cat_stat("K", stats.get("K", "-1")), name, higher=True)
            if is_winner:
                era = _parse_cat_stat("ERA", stats.get("ERA", "-1"))
                if era >= 0:
                    _update("lowest_era_winner", era, name, higher=False)

    return records, broken


# ── Luck index calculator ─────────────────────────────────────────────────────

_LOWER_IS_BETTER_CATS = {"ERA", "WHIP"}


def _calculate_luck_index(season: int, through_week: int) -> dict[str, dict]:
    """
    For each team, compute:
      actual_wins   — real season wins from matchup data
      expected_wins — sum of (simulated wins vs every other team) / 13 per week
      luck_delta    — actual_wins - expected_wins (positive = lucky)

    Returns {team_name: {actual_wins, expected_wins, luck_delta}}
    """
    season_dir = DATA_ROOT / str(season)
    week_files = sorted(
        f for f in season_dir.glob("week_*.json")
        if int(f.stem.split("_")[1]) < through_week
    )

    totals: dict[str, dict] = {}

    for wf in week_files:
        try:
            with open(wf, encoding="utf-8") as f:
                wd = json.load(f)
        except Exception:
            continue

        # Gather all teams' category stats for this week
        teams_stats: dict[str, dict] = {}
        teams_actual_wins: dict[str, float] = {}
        for m in wd.get("matchups", []):
            for t in m.get("teams", []):
                name = t.get("name", "")
                if name:
                    teams_stats[name] = t.get("category_stats", {})
                    teams_actual_wins[name] = float(t.get("points", 0.0))

        all_teams = list(teams_stats.keys())
        n = len(all_teams)
        if n < 2:
            continue

        # For each team, simulate against every other team
        for team_a in all_teams:
            sim_wins = 0.0
            cats_a = teams_stats[team_a]
            for team_b in all_teams:
                if team_a == team_b:
                    continue
                cats_b = teams_stats[team_b]
                # Count categories team_a would win
                a_cat_wins = 0
                for cat in cats_a:
                    val_a = _parse_cat_stat(cat, str(cats_a.get(cat, "-1")))
                    val_b = _parse_cat_stat(cat, str(cats_b.get(cat, "-1")))
                    if val_a < 0 or val_b < 0:
                        continue
                    if cat in _LOWER_IS_BETTER_CATS:
                        if val_a < val_b:
                            a_cat_wins += 1
                    else:
                        if val_a > val_b:
                            a_cat_wins += 1
                # Win = more categories won than opponent (out of 12)
                if a_cat_wins > 6:
                    sim_wins += 1
                elif a_cat_wins == 6:
                    sim_wins += 0.5  # simulated tie

            expected_this_week = sim_wins / (n - 1)

            if team_a not in totals:
                totals[team_a] = {"actual_wins": 0.0, "expected_wins": 0.0}
            totals[team_a]["actual_wins"] += teams_actual_wins.get(team_a, 0.0) / 10  # normalize to match wins
            totals[team_a]["expected_wins"] += expected_this_week

    for team, data in totals.items():
        data["luck_delta"] = round(data["actual_wins"] - data["expected_wins"], 2)
        data["actual_wins"] = round(data["actual_wins"], 2)
        data["expected_wins"] = round(data["expected_wins"], 2)

    return totals


# ── Two-pass recap generation ─────────────────────────────────────────────────

def _build_recap_context(
    week_data: dict,
    season_history: dict,
    records: dict,
    luck_index: dict,
    next_week_schedule: list[dict],
    spotlight_team: str,
) -> str:
    """Assemble all raw data into a context string for Pass 1."""
    week_num = week_data.get("week", "?")
    lines: list[str] = [f"WEEK {week_num} DATA\n"]

    # Matchup results
    lines.append("MATCHUP RESULTS (category stats per team):")
    for m in week_data.get("matchups", []):
        teams = m.get("teams", [])
        if len(teams) < 2:
            continue
        t1, t2 = teams[0], teams[1]
        winner_key = m.get("winner_key")
        if m.get("is_tied"):
            result = f"TIE: {t1['name']} {t1['points']:.0f}–{t2['name']} {t2['points']:.0f}"
        else:
            winner = t1 if t1.get("team_key") == winner_key else t2
            loser  = t2 if winner is t1 else t1
            result = f"{winner['name']} def. {loser['name']} {winner['points']:.0f}–{loser['points']:.0f}"
        lines.append(f"  {result}")
        for t in [t1, t2]:
            cats = t.get("category_stats", {})
            cat_str = " | ".join(f"{k}:{v}" for k, v in cats.items())
            players = t.get("top_players", [])
            player_str = ""
            if players:
                player_str = " — players: " + ", ".join(
                    f"{p['name']}({p.get('position','?')}): {p.get('stats','')}"
                    for p in players[:3] if p.get("stats")
                )
            lines.append(f"    {t['name']}: [{cat_str}]{player_str}")

    # Live standings
    lines.append("\nLIVE STANDINGS:")
    for s in week_data.get("standings", []):
        lines.append(
            f"  {s['rank']}. {s['name']}: {s['wins']}-{s['losses']}-{s.get('ties',0)} "
            f"(PF: {s.get('points_for',0):.0f})"
        )

    # Luck index
    if luck_index:
        lines.append("\nLUCK INDEX (actual wins vs expected wins, luck_delta = difference):")
        for team, data in sorted(luck_index.items(), key=lambda x: x[1]["luck_delta"], reverse=True):
            lines.append(
                f"  {team}: actual={data['actual_wins']:.1f}, "
                f"expected={data['expected_wins']:.2f}, delta={data['luck_delta']:+.2f}"
            )

    # Season history — weekly points and prior power rankings
    weekly_pts = season_history.get("weekly_points", {})
    if weekly_pts:
        lines.append("\nWEEKLY CATEGORY WINS HISTORY:")
        for wk, pts in sorted(weekly_pts.items()):
            top = sorted(pts.items(), key=lambda x: x[1], reverse=True)
            lines.append(f"  {wk}: " + ", ".join(f"{t}:{v:.0f}" for t, v in top))

    prior_rankings = season_history.get("power_rankings", {})
    if prior_rankings:
        last_rk_key = max(prior_rankings.keys())
        lines.append(f"\nPRIOR POWER RANKINGS ({last_rk_key}):")
        for entry in prior_rankings[last_rk_key]:
            lines.append(f"  {entry['rank']}. {entry['team']}")

    # Current season records
    if records:
        lines.append("\nCURRENT SEASON RECORDS (compare current week stats to flag new records):")
        for k, v in records.items():
            lines.append(f"  {k}: {v['value']} ({v['team']}, week {v['week']})")

    # Transactions
    adds: dict[str, list[str]] = {}
    drops: dict[str, list[str]] = {}
    for tx in week_data.get("transactions", []):
        if tx.get("type") not in ("add", "drop", "add/drop"):
            continue
        for p in tx.get("players", []):
            team = p.get("team", "")
            name = p.get("name", "")
            pos = p.get("position", "")
            entry = f"{name}({pos})" if pos else name
            if p.get("action") == "add":
                adds.setdefault(team, []).append(entry)
            elif p.get("action") == "drop":
                drops.setdefault(team, []).append(entry)
    if adds or drops:
        lines.append("\nWAIVER WIRE MOVES THIS WEEK:")
        for team in sorted(set(list(adds.keys()) + list(drops.keys()))):
            parts = []
            if team in adds:
                parts.append(f"added {', '.join(adds[team][:4])}")
            if team in drops:
                parts.append(f"dropped {', '.join(drops[team][:4])}")
            lines.append(f"  {team}: {'; '.join(parts)}")

    # Manager spotlight
    lines.append(f"\nMANAGER SPOTLIGHT THIS WEEK: {spotlight_team}")

    # Next week schedule
    if next_week_schedule:
        lines.append(f"\nNEXT WEEK MATCHUPS (week {int(week_num)+1}):")
        for pair in next_week_schedule:
            lines.append(f"  {pair['team_a']} vs {pair['team_b']}")

    return "\n".join(lines)


def _repair_json_aggressive(raw: str) -> dict:
    """
    More aggressive JSON repair beyond _safe_json_parse:
    - Strips JS-style // comments
    - Removes trailing commas before } or ]
    - Falls back to extracting the outermost {...} block
    """
    import re as _re
    # Strip // comments (not inside strings — best-effort)
    cleaned = _re.sub(r'(?<!:)//[^\n]*', '', raw)
    # Remove trailing commas before closing braces/brackets
    cleaned = _re.sub(r',\s*([}\]])', r'\1', cleaned)
    # Fix literal control chars in strings
    cleaned = _fix_json_strings(cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    # Last resort: grab outermost { ... }
    match = _re.search(r'\{.*\}', cleaned, _re.DOTALL)
    if match:
        return json.loads(match.group())
    raise ValueError("Could not repair JSON")


def _parse_pass1_xml(raw: str) -> dict:
    """Parse Pass 1 XML-tagged output into a dict. Robust to missing tags."""
    def _tag(name: str, default: str = "") -> str:
        m = re.search(rf'<{name}>(.*?)</{name}>', raw, re.DOTALL)
        return m.group(1).strip() if m else default

    def _tag_lines(name: str) -> list[str]:
        m = re.search(rf'<{name}>(.*?)</{name}>', raw, re.DOTALL)
        if not m:
            return []
        return [ln.strip() for ln in m.group(1).strip().splitlines() if ln.strip()]

    return {
        "stat_of_week":       _tag("stat_of_week"),
        "thriller_teams":     _tag("thriller_teams"),
        "thriller_score":     _tag("thriller_score"),
        "thriller_note":      _tag("thriller_note"),
        "key_storyline":      _tag("key_storyline"),
        "lucky_team":         _tag("lucky_team"),
        "lucky_reason":       _tag("lucky_reason"),
        "unlucky_team":       _tag("unlucky_team"),
        "unlucky_reason":     _tag("unlucky_reason"),
        "records_broken":     _tag("records_broken"),
        "spotlight_team":     _tag("spotlight_team"),
        "include_trade_value": _tag("include_trade_value", "false").lower() == "true",
        "power_rankings":     _tag_lines("power_rankings"),
        "waiver_highlights":  _tag_lines("waiver_highlights"),
    }


def _pass1_plan(context: str, week_num: int, prior_rankings: dict) -> dict:
    """
    Pass 1: Feed raw data into Claude. Returns a planning dict.
    Uses XML tags — no JSON parsing, completely avoids escaping issues.
    """
    has_prior = bool(prior_rankings)
    rankings_note = (
        "List all 14 teams in power order, one per line: RANK. TEAM NAME | brief reason | movement (up/down/same)"
        if has_prior else
        "List all 14 teams in power order, one per line: RANK. TEAM NAME | brief reason"
    )

    prompt = f"""You are a fantasy baseball analyst. Read the week data below and make the key editorial decisions for a weekly recap article.

{context}

Respond using ONLY these XML tags — no JSON, no markdown, no preamble, nothing outside the tags:

<stat_of_week>NUMBER - brief explanation of the most striking stat</stat_of_week>
<thriller_teams>Team A vs Team B</thriller_teams>
<thriller_score>X-Y</thriller_score>
<thriller_note>One sentence on what made it close and what it means for both teams going forward</thriller_note>
<key_storyline>2-3 sentences on the single biggest narrative of the week</key_storyline>
<lucky_team>Team Name</lucky_team>
<lucky_reason>One sentence on why they were lucky this week</lucky_reason>
<unlucky_team>Team Name</unlucky_team>
<unlucky_reason>One sentence on why they were unlucky this week</unlucky_reason>
<records_broken>Empty if none. Otherwise: one sentence naming the record, who broke it, and the previous mark.</records_broken>
<spotlight_team>Team Name</spotlight_team>
<include_trade_value>true or false</include_trade_value>
<power_rankings>
{rankings_note}
Include ALL 14 teams.
</power_rankings>
<waiver_highlights>
One line per notable move: Team Name | grade (A/B/C/D) | move description | brief analysis
Leave empty if no significant moves this week.
</waiver_highlights>

Rules:
- thriller_teams must be the matchup with the smallest margin of victory (fewest categories separating teams)
- lucky_team: won despite below-average category stats; unlucky_team: strong stats but lost
- include_trade_value: true only if 2 or more players had significant performance shifts
- Use exact team names from the data"""

    last_err: Exception | None = None
    for attempt in range(3):
        try:
            raw = _call_claude(prompt, max_tokens=1500)
            plan = _parse_pass1_xml(raw)
            if not plan.get("key_storyline"):
                raise ValueError("Pass 1 response missing key fields — retrying")
            return plan
        except Exception as e:
            last_err = e
            print(f"[ci_runner] Pass 1 attempt {attempt+1}/3 failed: {e}", file=sys.stderr)
    raise RuntimeError(f"Pass 1 failed after 3 attempts: {last_err}")


def _pass2_write(
    week_data: dict,
    plan: dict,
    writer_key: str,
    next_week_schedule: list[dict],
) -> dict:
    """
    Pass 2: Feed the planning document into Claude and generate the full article.
    Returns {headline, subheadline, body}.
    """
    writer = WRITER_STYLES[writer_key]
    week_num = week_data.get("week", "?")
    league = week_data.get("league_name", "MillerLite® BeerLeagueBaseball")

    # Build the at-a-glance table rows from matchup data
    table_rows: list[str] = []
    for m in week_data.get("matchups", []):
        teams = m.get("teams", [])
        if len(teams) < 2:
            continue
        t1, t2 = teams[0], teams[1]
        winner_key = m.get("winner_key")
        if m.get("is_tied"):
            winner_col = f"{t1['name']} / {t2['name']}"
            loser_col = ""
            score = f"{t1['points']:.0f}-{t2['points']:.0f}"
        else:
            winner = t1 if t1.get("team_key") == winner_key else t2
            loser  = t2 if winner is t1 else t1
            winner_col = winner["name"]
            loser_col  = loser["name"]
            score = f"{winner['points']:.0f}-{loser['points']:.0f}"
        table_rows.append(f"| {winner_col} | {loser_col} | {score} | — |")

    table_md = (
        "| Winner | Loser | Score | Player of the Matchup |\n"
        "|--------|-------|-------|-----------------------|\n"
        + "\n".join(table_rows)
    )

    # Build matchup summary lines for Pass 2
    matchup_lines: list[str] = []
    for m in week_data.get("matchups", []):
        teams = m.get("teams", [])
        if len(teams) < 2:
            continue
        t1, t2 = teams[0], teams[1]
        winner_key = m.get("winner_key")
        if m.get("is_tied"):
            result = f"TIE: {t1['name']} {t1['points']:.0f} vs {t2['name']} {t2['points']:.0f}"
        else:
            winner = t1 if t1.get("team_key") == winner_key else t2
            loser  = t2 if winner is t1 else t1
            result = f"{winner['name']} def. {loser['name']} {winner['points']:.0f}-{loser['points']:.0f}"
        matchup_lines.append(result)
        for t in [t1, t2]:
            cats = t.get("category_stats", {})
            cat_str = " | ".join(f"{k}:{v}" for k, v in cats.items())
            matchup_lines.append(f"  {t['name']}: {cat_str}")

    # Serialize the planning doc
    plan_text = json.dumps(plan, indent=2)

    # Trade value section note
    include_trade = plan.get("include_trade_value", False)
    trade_value_note = (
        "Section 10 (Trade value): OMIT this section entirely — no significant player shifts this week."
        if not include_trade
        else "Section 10 (Trade value): Include 2-3 players. For each: one sentence on what happened, one verdict (Buy/Sell/Hold) with brief reasoning."
    )

    # Records broken note
    records_str = str(plan.get("records_broken", "")).strip()
    records_note = (
        "Section 8 (League record broken): OMIT this section entirely — no records were broken this week."
        if not records_str
        else f"Section 8 (League record broken): Include — {records_str}"
    )

    # Power rankings from plan — already formatted as "1. Team | reason" strings
    rankings_list = plan.get("power_rankings", [])
    rankings_text = "\n".join(rankings_list) if rankings_list else "(not provided)"
    has_movement = any("up" in r.lower() or "down" in r.lower() for r in rankings_list)

    # Waiver highlights from plan
    waiver_list = plan.get("waiver_highlights", [])
    waiver_text = "\n".join(f"  {w}" for w in waiver_list) if waiver_list else "  (no notable moves)"

    prompt = f"""You are {writer['name']} of {writer['outlet']}, writing the Week {week_num} recap for "{league}."

{writer['voice']}

You have a PLANNING DOCUMENT with the key editorial decisions, and the full raw week data below. Use both to write the article.

PLANNING DOCUMENT:
{plan_text}

POWER RANKINGS (use exactly as listed):
{rankings_text}

WAIVER WIRE MOVES (use exactly as listed):
{waiver_text}

RAW MATCHUP DATA (use for deep-dives and player references):
{chr(10).join(matchup_lines)}

AT-A-GLANCE TABLE (include verbatim — fill in Player of the Matchup column from the raw data):
{table_md}

WRITE THE FULL ARTICLE in this exact section order. Use ## for section headers.

1. **Headline + subheadline** — returned as separate JSON fields, not in body
2. **Stat of the Week** — bold callout immediately after opening. Format: **[the stat_of_week from the plan]**
3. **At-a-Glance** (`## At-a-Glance`) — the table above, but fill in the Player of the Matchup column with the standout performer from each matchup based on the raw data
4. **Thriller of the Week** (`## Thriller of the Week`) — write about the thriller_teams matchup. 2-3 sentences on key performances, 1 sentence on stakes for both teams
5. **The Week's Defining Moment** (`## The Week's Defining Moment`) — expand key_storyline into 2-3 paragraphs using raw matchup data
6. **Matchup Deep-Dives** (`## Matchup Deep-Dives`) — every matchup gets its own subsection (### Result). For each: result line, key category stats, strategic implication, next week preview
7. **Lucky/Unlucky Team of the Week** (`## Lucky/Unlucky Team of the Week`) — use lucky_team/unlucky_team and their reasons from the plan
8. {records_note}
9. **Manager Spotlight** (`## Manager Spotlight`) — feature spotlight_team. Cover their record, power ranking position, how their roster is performing, playoff outlook
10. {trade_value_note}
11. **Power Rankings** (`## Power Rankings`) — use the rankings list exactly as provided above, one entry per line{"" if has_movement else " (week 1 — no movement arrows)"}
12. **Waiver Wire** (`## Waiver Wire`) — use the waiver highlights above. Format: **[GRADE]** Team — move — analysis

RULES:
- Use **bold** for team names throughout
- No favoritism toward any team
- Write in {writer['name']}s authentic voice
- Body should be 900-1200 words (not counting the table)

Wrap your response in XML tags exactly like this — no JSON, no preamble, nothing outside the tags:
<headline>your headline here</headline>
<subheadline>one sharp sentence here</subheadline>
<body>
full article body here, sections 2-12 in order, markdown OK
</body>"""

    raw = _call_claude(prompt, max_tokens=4000)

    headline_match    = re.search(r'<headline>(.*?)</headline>', raw, re.DOTALL)
    subheadline_match = re.search(r'<subheadline>(.*?)</subheadline>', raw, re.DOTALL)
    body_match        = re.search(r'<body>(.*?)(?:</body>|$)', raw, re.DOTALL)

    if not (headline_match and subheadline_match and body_match):
        raise ValueError(f"Pass 2 missing XML tags in response: {raw[:300]}")

    return {
        "headline":    headline_match.group(1).strip(),
        "subheadline": subheadline_match.group(1).strip(),
        "body":        body_match.group(1).strip(),
    }


def generate_recap_article(
    week_data: dict,
    season: int,
    season_history: dict,
    records: dict,
    luck_index: dict,
    next_week_schedule: list[dict],
) -> dict | None:
    """
    Two-pass recap generation.
    Pass 1: planning document (max 1500 tokens)
    Pass 2: full article from planning doc (max 4000 tokens)
    Returns article dict or None on failure.
    """
    is_champ   = any(m.get("is_championship") for m in week_data.get("matchups", []))
    is_playoff = any(m.get("is_playoffs") and not m.get("is_consolation")
                     for m in week_data.get("matchups", []))

    if is_champ:
        writer_key = _PLAYOFF_WRITER
    elif is_playoff:
        writer_key = random.choice([_PLAYOFF_WRITER] + _RECAP_WRITERS)
    else:
        writer_key = random.choice(_RECAP_WRITERS)

    week_num = week_data.get("week", 0)

    # Determine spotlight team from rotation
    rotation = season_history.get("manager_spotlight_rotation", [])
    last_spotlight = season_history.get("last_spotlight_week")
    if rotation:
        # Advance rotation by 1 from last used index
        try:
            last_idx = rotation.index(last_spotlight) if last_spotlight in rotation else -1
        except ValueError:
            last_idx = -1
        spotlight_team = rotation[(last_idx + 1) % len(rotation)]
    else:
        spotlight_team = ""

    # Build context
    prior_rankings = season_history.get("power_rankings", {})
    context = _build_recap_context(
        week_data, season_history, records, luck_index,
        next_week_schedule, spotlight_team,
    )

    # Pass 1 — planning
    print(f"[ci_runner] Pass 1: generating planning document for week {week_num}…")
    try:
        plan = _pass1_plan(context, week_num, prior_rankings)
    except Exception as e:
        print(f"[ci_runner] Pass 1 failed: {e}", file=sys.stderr)
        return None

    # Save Pass 1 artifact for debugging
    artifacts_dir = DATA_ROOT / str(season) / "articles" / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = artifacts_dir / f"week_{int(week_num):02d}_plan.json"
    try:
        with open(artifact_path, "w", encoding="utf-8") as f:
            json.dump(plan, f, indent=2, ensure_ascii=False)
        print(f"[ci_runner]   ✓ Pass 1 plan saved to {artifact_path.name}")
    except Exception as e:
        print(f"[ci_runner] Warning: could not save Pass 1 artifact: {e}", file=sys.stderr)

    # Pass 2 — writing
    print(f"[ci_runner] Pass 2: generating article for week {week_num}…")
    for attempt in range(3):
        try:
            article = _pass2_write(week_data, plan, writer_key, next_week_schedule)
            break
        except Exception as e:
            print(f"[ci_runner] Pass 2 attempt {attempt+1}/3 failed: {e}", file=sys.stderr)
            if attempt == 2:
                return None

    article["generated_at"]    = datetime.now().isoformat()
    article["week"]            = week_num
    article["writer_key"]      = writer_key
    article["writer_name"]     = WRITER_STYLES[writer_key]["name"]
    article["writer_outlet"]   = WRITER_STYLES[writer_key]["outlet"]
    article["is_playoff"]      = is_playoff
    article["is_championship"] = is_champ
    article["spotlight_team"]  = spotlight_team
    article["power_rankings"]  = plan.get("power_rankings", [])

    # Update season_history with this week's data
    wk_key = f"week_{int(week_num):02d}"
    weekly_pts: dict[str, float] = {}
    for m in week_data.get("matchups", []):
        for t in m.get("teams", []):
            if t.get("name"):
                weekly_pts[t["name"]] = float(t.get("points", 0.0))
    season_history["weekly_points"][wk_key] = weekly_pts
    season_history["power_rankings"][wk_key] = plan.get("power_rankings", [])
    if spotlight_team:
        season_history["last_spotlight_week"] = spotlight_team

    return article


# ── Trade article generation ──────────────────────────────────────────────────

def generate_trade_article(trade_tx: dict, standings: list[dict]) -> dict | None:
    writer_key  = random.choice(_TRADE_WRITERS)
    writer      = WRITER_STYLES[writer_key]

    players = trade_tx.get("players", [])
    if not players:
        return None

    team_names = list({p.get("team", "") for p in players
                       if p.get("team") and p.get("team") != "Free Agent"})
    team_a = team_names[0] if team_names else "Team A"
    team_b = team_names[1] if len(team_names) > 1 else "Team B"

    def side(team: str) -> list[str]:
        return [f"{p['name']} ({p.get('position','?')})" for p in players if p.get("team") == team]

    all_names = ", ".join(f"{p['name']} ({p.get('position','?')})" for p in players)
    standings_ctx = "\n".join(
        f"  {s['name']}: {s['wins']}-{s['losses']} ({s.get('points_for',0):.0f} PF)"
        for s in standings[:8]
    ) if standings else "  (pre-season)"

    prompt = f"""You are {writer['name']} of {writer['outlet']}, writing a breaking news trade article for "MillerLite® BeerLeagueBaseball."

{writer['voice']}

TRADE DETAILS:
{team_a} receives: {', '.join(side(team_a)) or 'undisclosed'}
{team_b} receives: {', '.join(side(team_b)) or 'undisclosed'}
All players: {all_names}

CURRENT STANDINGS (top 8):
{standings_ctx}

Write a trade wire article (220–300 words) including:
1. A punchy breaking-news headline referencing BeerLeague
2. Opening in {writer['name']}'s authentic voice
3. Analysis of what each team gains/loses strategically
4. A clear verdict on who wins the trade
5. Trade grades for each side (A+ through F)

Respond ONLY with valid JSON — no markdown fences:
{{
  "headline": "...",
  "body": "...(use **bold** for player names, markdown OK)...",
  "grade_team_a": "B+",
  "grade_team_b": "A-",
  "team_a": "{team_a}",
  "team_b": "{team_b}"
}}"""

    try:
        raw     = _call_claude(prompt, max_tokens=1024)
        article = _safe_json_parse(raw)
        article["generated_at"]          = datetime.now().isoformat()
        article["transaction_timestamp"] = trade_tx.get("timestamp", 0)
        article["writer_key"]            = writer_key
        article["writer_name"]           = writer["name"]
        article["writer_outlet"]         = writer["outlet"]
        return article
    except Exception as e:
        print(f"[ci_runner] Trade article generation failed: {e}", file=sys.stderr)
        return None


# ── Recap article generation ──────────────────────────────────────────────────

# ── Season preview generation ─────────────────────────────────────────────────

def _build_historical_context(season: int, lookback: int = 2) -> dict:
    """
    Aggregate team records (wins, losses, championships) from the most recent
    `lookback` completed seasons before `season`.
    Returns a dict keyed by team name.
    """
    records: dict[str, dict] = {}
    min_season = season - lookback  # only include seasons within the lookback window

    for season_dir in sorted(DATA_ROOT.iterdir()):
        if not season_dir.is_dir():
            continue
        try:
            yr = int(season_dir.name)
        except ValueError:
            continue
        if yr >= season or yr < min_season:   # skip current and seasons outside window
            continue

        # Find the last week file for this season
        week_files = sorted(season_dir.glob("week_*.json"))
        if not week_files:
            continue
        last_week_file = week_files[-1]

        try:
            with open(last_week_file, encoding="utf-8") as f:
                wd = json.load(f)
        except Exception:
            continue

        standings = wd.get("standings", [])
        matchups  = wd.get("matchups", [])

        # Detect champion from the championship matchup — use team name only
        champion_name = None
        for m in matchups:
            if m.get("is_championship") and not m.get("is_tied"):
                teams = m.get("teams", [])
                if len(teams) == 2:
                    winner = next(
                        (t for t in teams if t.get("team_key") == m.get("winner_key")), None
                    )
                    if winner:
                        champion_name = winner.get("name")  # team name, not manager name

        for s in standings:
            # Always key by team name — never expose real manager names
            team = s.get("name", "Unknown")
            if team not in records:
                records[team] = {"wins": 0, "losses": 0, "ties": 0,
                                 "championships": 0, "seasons": 0,
                                 "best_rank": 99, "seasons_data": []}
            records[team]["wins"]   += s.get("wins", 0)
            records[team]["losses"] += s.get("losses", 0)
            records[team]["ties"]   += s.get("ties", 0)
            records[team]["seasons"] += 1
            rank = s.get("rank", 99)
            if rank < records[team]["best_rank"]:
                records[team]["best_rank"] = rank
            records[team]["seasons_data"].append({
                "year": yr,
                "rank": rank,
                "wins": s.get("wins", 0),
                "losses": s.get("losses", 0),
            })
            if champion_name and s.get("name") == champion_name:
                records[team]["championships"] += 1

    return records


def generate_season_preview(season: int) -> dict | None:
    """
    Generate a full-season preview article written by Peter Gammons.
    Draws on draft order, last season's standings, and all-time records.
    Returns article dict or None on failure.
    """
    draft_file = DATA_ROOT / str(season) / "draft_order.json"
    draft_results_file = DATA_ROOT / str(season) / "draft_results.json"

    draft_order: list[dict] = []
    draft_date  = f"{season}-03-22"
    draft_notes = "Snake draft, live online"

    if draft_file.exists():
        with open(draft_file, encoding="utf-8") as f:
            draft_data = json.load(f)
        draft_order = draft_data.get("draft_order", [])
        draft_date  = draft_data.get("draft_date", draft_date)
        draft_notes = draft_data.get("notes", draft_notes)
    elif draft_results_file.exists():
        # Fallback: synthesize draft order from round-1 picks in draft_results.json
        with open(draft_results_file, encoding="utf-8") as f:
            dr = json.load(f)
        picks = dr.get("picks", [])
        # Build team_key→name from week data
        tk_to_name: dict[str, str] = {}
        for wf in sorted((DATA_ROOT / str(season)).glob("week_*.json")):
            try:
                with open(wf, encoding="utf-8") as f:
                    wd = json.load(f)
                for m in wd.get("matchups", []):
                    for t in m.get("teams", []):
                        if t.get("team_key") and t.get("name"):
                            tk_to_name[t["team_key"]] = t["name"]
                if tk_to_name:
                    break
            except Exception:
                pass
        round1 = sorted([p for p in picks if p.get("round") == 1], key=lambda x: x.get("pick", 999))
        draft_order = [
            {"pick": p.get("pick", i + 1), "manager": tk_to_name.get(p["team_key"], p["team_key"]),
             "team": tk_to_name.get(p["team_key"], p["team_key"])}
            for i, p in enumerate(round1)
        ]
    else:
        print(f"[ci_runner] No draft_order.json or draft_results.json found for {season}.", file=sys.stderr)
        return None

    # Last season's final standings
    prev_season  = season - 1
    prev_dir     = DATA_ROOT / str(prev_season)
    prev_standings: list[dict] = []
    prev_champion = "Unknown"

    # Build manager-name → team-name mapping from prev season matchup teams
    # NOTE: standings rows don't have a 'manager' field; matchup team objects do.
    mgr_to_team: dict[str, str] = {}

    if prev_dir.exists():
        prev_files = sorted(prev_dir.glob("week_*.json"))
        if prev_files:
            try:
                with open(prev_files[-1], encoding="utf-8") as f:
                    prev_wd = json.load(f)
                prev_standings = prev_wd.get("standings", [])

                # Build mgr→team from matchup teams (have both 'manager' and 'name')
                for m in prev_wd.get("matchups", []):
                    for t in m.get("teams", []):
                        mgr  = t.get("manager", "")
                        team = t.get("name", "")
                        if mgr and team:
                            mgr_to_team[mgr] = team

                # Detect defending champion — use team name only
                # First try: explicit championship matchup
                for m in prev_wd.get("matchups", []):
                    if m.get("is_championship") and not m.get("is_tied"):
                        teams = m.get("teams", [])
                        winner = next(
                            (t for t in teams if t.get("team_key") == m.get("winner_key")), None
                        )
                        if winner:
                            prev_champion = winner.get("name", "Unknown")
                # Fallback: rank=1 in final standings (handles leagues where
                # is_championship flag isn't set in the stored week JSON)
                if prev_champion == "Unknown" and prev_standings:
                    top = next((s for s in prev_standings if s.get("rank") == 1), None)
                    if top:
                        prev_champion = top.get("name", "Unknown")
            except Exception:
                pass

    # Recent records (last 2 seasons only — keeps context tight and relevant)
    alltime = _build_historical_context(season, lookback=2)

    # --- Build prompt context ---
    writer     = WRITER_STYLES["rosenthal"]

    def _resolve_team(pick: dict) -> str:
        """
        Return team name for a draft-order entry, in priority order:
          1. Explicit 'team' field in draft_order.json (most reliable)
          2. Exact manager-name match in mgr_to_team lookup
          3. Prefix match (handles "Alton" vs "Alton Gilbert")
          4. Raw manager name as last resort
        """
        explicit = pick.get("team", "").strip()
        if explicit:
            return explicit
        mgr = pick.get("manager", "")
        if mgr in mgr_to_team:
            return mgr_to_team[mgr]
        # Prefix match: "Alton" → "Alton Gilbert"
        mgr_lower = mgr.lower()
        for full, team in mgr_to_team.items():
            if full.lower().startswith(mgr_lower) or mgr_lower.startswith(full.lower()):
                return team
        return mgr  # final fallback

    # Draft order context
    draft_lines = "\n".join(
        f"  Pick {p['pick']:2d}: {_resolve_team(p)}"
        for p in draft_order
    )

    # Previous season standings — team names + final rank only
    # (wins/losses are not reliably stored; rank IS authoritative)
    prev_sorted = sorted(prev_standings, key=lambda s: s.get("rank", 99))
    prev_lines = "\n".join(
        f"  #{s['rank']:2d}. {s.get('name')}"
        for s in prev_sorted
    ) if prev_standings else "  (not available)"

    # All-time records context — use per-season finish positions
    # (wins/losses fields may be 0 due to storage format; rank is reliable)
    alltime_lines = []
    for team, rec in sorted(alltime.items(), key=lambda x: x[1]["best_rank"]):
        champ_str = f", {rec['championships']}x champion" if rec["championships"] else ""
        seasons_detail = ", ".join(
            f"{sd['year']}: #{sd['rank']}"
            for sd in sorted(rec["seasons_data"], key=lambda x: x["year"])
        )
        alltime_lines.append(
            f"  {team}: {seasons_detail}{champ_str}"
        )
    alltime_ctx = "\n".join(alltime_lines) if alltime_lines else "  (no history available)"

    prompt = f"""You are {writer['name']} of {writer['outlet']}.

{writer['voice']}

You are writing the definitive {season} season preview for a 14-team fantasy baseball league called "MillerLite® BeerLeagueBaseball." This is a close-knit group of friends who have played together for years. You have real historical data — use it. Reference team names, records, and history. Irreverent trash talk is not just permitted, it's expected — but it must be grounded in the actual data.

IMPORTANT: Refer to all participants exclusively by their TEAM NAME — never use real names.

LEAGUE STRUCTURE:
- 14 teams, head-to-head category scoring (12 categories: H/AB, R, HR, RBI, SB, OBP, IP, K, ERA, WHIP, QS, NSVH)
- ERA and WHIP: lower is better; all other categories higher is better
- Snake draft format: {draft_notes}
- Draft date: {draft_date}

{season} DRAFT ORDER (pick position = competitive advantage):
{draft_lines}

{prev_season} FINAL STANDINGS (defending champion: {prev_champion}):
{prev_lines}

RECENT FINISH POSITIONS (last 2 seasons, {season - 2}–{season - 1}):
{alltime_ctx}

Write a LONG, richly detailed season preview (1800–2200 words). Use Roman numeral section headers (I, II, III, IV, V). Go deep — this is the kind of feature-length piece that readers bookmark and return to throughout the season.

I. **Opening: The Gathering Storm** (3–4 paragraphs)
   - Open with a vivid, atmospheric scene-setter. Paint a picture of spring baseball arriving.
   - Build to the current state of the league: who rules, who is hungry, what is at stake.
   - Reference {prev_champion} defending their title. Describe the target on their back.
   - End with anticipation for draft day, {draft_date}.

II. **The Draft Order: Fortune's Wheel** (2–3 paragraphs)
   - Analyze the draft order in tiers: the top picks (1–4) who get elite talent, the sweet spot (5–8) with snake-back positioning, and the back end (9–14) who must work for every advantage.
   - Call out which specific teams are advantaged or disadvantaged by their pick slot.
   - Discuss how draft position has historically shaped outcomes in this league.

III. **The Field: Fourteen Teams, Fourteen Stories** (the heart of the piece — ALL 14 teams)
   For EACH of the 14 teams, write 4–5 sentences that cover:
     • Their draft pick number and what it means
     • Their historical record and trajectory across recent seasons (use the data)
     • Their strengths, weaknesses, and what to expect in {season}
     • A moment of specific wit or analysis unique to that team
     • A projected finish (e.g., "Projected finish: 3rd")
   List them IN DRAFT ORDER (pick 1 through 14). Be vivid and specific — no generic sentences.
   Teams with championship history should be noted. Teams with consecutive bad finishes should be roasted. Rising teams should be hyped.

IV. **Five Bold Predictions** (exactly 5)
   Each prediction should be specific, colorful, and arguable. Reference actual teams and real trends from the data. Numbered list. Make them memorable.

V. **The Pick: A Champion Crowned** (1–2 paragraphs)
   Name your champion with conviction. Build a case using draft position, recent trajectory, historical patterns. End with a memorable final line.

Use **bold** for team names throughout. Markdown OK. Section headers as Roman numerals in bold.

Respond ONLY with valid JSON — no markdown fences:
{{
  "headline": "...(punchy, evocative season preview headline — not a question, a declaration)...",
  "subheadline": "...(one sharp sentence that makes you want to read every word)...",
  "body": "...(full article, 1800–2200 words)..."
}}"""

    try:
        raw     = _call_claude(prompt, max_tokens=5000)
        article = _safe_json_parse(raw)
        article["generated_at"]  = datetime.now().isoformat()
        article["season"]        = season
        article["writer_key"]    = "rosenthal"
        article["writer_name"]   = writer["name"]
        article["writer_outlet"] = writer["outlet"]
        article["type"]          = "season_preview"
        return article
    except Exception as e:
        print(f"[ci_runner] Season preview generation failed: {e}", file=sys.stderr)
        return None


def run_preview(season: int, force: bool = False) -> bool:
    """Generate season preview article. Returns True on success."""
    articles_dir = DATA_ROOT / str(season) / "articles"
    out_path     = articles_dir / "season_preview.json"

    if out_path.exists() and not force:
        print(f"[ci_runner] Season preview for {season} already exists — skipping. Use --force to regenerate.")
        return True

    print(f"[ci_runner] Generating {season} season preview…")
    article = generate_season_preview(season)
    if not article:
        return False

    articles_dir.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(article, f, indent=2, ensure_ascii=False)
    print(f"[ci_runner]   ✓ Saved season_preview.json (by {article['writer_name']})")
    return True


# ── Trade detection helpers ───────────────────────────────────────────────────

def _load_existing_article_timestamps(trades_dir: Path) -> set[int]:
    """Return set of transaction timestamps already covered by an article."""
    if not trades_dir.exists():
        return set()
    timestamps = set()
    for fp in trades_dir.glob("trade_*.json"):
        try:
            with open(fp) as f:
                data = json.load(f)
            ts = data.get("transaction_timestamp")
            if ts:
                timestamps.add(int(ts))
        except Exception:
            pass
    return timestamps


def _find_unprocessed_trades(week_data: dict, covered_ts: set[int]) -> list[dict]:
    """Return trade transactions that don't have an article yet."""
    unprocessed = []
    for tx in week_data.get("transactions", []):
        if tx.get("type", "").upper() != "TRADE":
            continue
        ts = tx.get("timestamp", 0)
        if ts and int(ts) not in covered_ts:
            unprocessed.append(tx)
    return unprocessed


# ── Main runner ───────────────────────────────────────────────────────────────

def run_trades(week_data: dict, season: int) -> list[dict]:
    """Detect and write articles for new trades. Returns list of newly-written articles."""
    trades_dir  = DATA_ROOT / str(season) / "trades"
    covered_ts  = _load_existing_article_timestamps(trades_dir)
    unprocessed = _find_unprocessed_trades(week_data, covered_ts)

    if not unprocessed:
        print("[ci_runner] No new trades detected.")
        return []

    standings    = week_data.get("standings", [])
    new_articles = []
    for tx in unprocessed:
        print(f"[ci_runner] Generating trade article for timestamp {tx.get('timestamp')}…")
        article = generate_trade_article(tx, standings)
        if article:
            trades_dir.mkdir(parents=True, exist_ok=True)
            ts   = article.get("transaction_timestamp", int(datetime.now().timestamp()))
            path = trades_dir / f"trade_{ts}.json"
            with open(path, "w") as f:
                json.dump(article, f, indent=2)
            print(f"[ci_runner]   ✓ Saved {path.name} (by {article['writer_name']})")
            new_articles.append(article)
        else:
            print("[ci_runner]   ✗ Article generation failed", file=sys.stderr)

    return new_articles


def _validate_week_data(week_data: dict, season: int) -> tuple[bool, list[str]]:
    """
    Validate week data before article generation.
    Returns (is_valid, list_of_issues).
    Critical issues block generation; warnings are logged but allowed through.
    """
    issues: list[str] = []
    matchups = week_data.get("matchups", [])
    week_num = week_data.get("week", 0)

    # --- Critical checks (return False) ---

    if not matchups:
        issues.append("CRITICAL: No matchups found in week data.")
        return False, issues

    scored = [m for m in matchups if any(t.get("points", 0) > 0 for t in m.get("teams", []))]
    if not scored:
        issues.append(
            f"CRITICAL: All matchup scores are 0 — week {week_num} data appears stale or pre-game."
        )
        return False, issues

    # Check week number looks reasonable for the season
    if not (1 <= int(week_num) <= 27):
        issues.append(f"CRITICAL: Week number {week_num} is out of expected range (1–27).")
        return False, issues

    # Check that team names aren't all generic defaults
    all_names = [t.get("name", "") for m in matchups for t in m.get("teams", [])]
    if sum(1 for n in all_names if n.startswith("Team ")) > len(all_names) // 2:
        issues.append("CRITICAL: More than half of team names are generic ('Team N') — data may be malformed.")
        return False, issues

    # --- Warnings (log but allow through) ---

    teams_without_stats = [
        t.get("name", "?") for m in matchups for t in m.get("teams", [])
        if not t.get("category_stats")
    ]
    if teams_without_stats:
        issues.append(f"WARNING: Missing category_stats for: {', '.join(teams_without_stats)}")

    teams_without_players = [
        t.get("name", "?") for m in matchups for t in m.get("teams", [])
        if not t.get("top_players")
    ]
    if teams_without_players:
        issues.append(f"WARNING: Missing top_players for: {', '.join(teams_without_players)}")

    if not week_data.get("standings"):
        issues.append("WARNING: No standings data — standings section will be thin.")

    return True, issues


def run_recap(
    week_data: dict,
    season: int,
    force: bool = False,
    next_week_schedule: list[dict] | None = None,
) -> bool:
    """Generate weekly recap article. Returns True on success."""
    week_num     = week_data.get("week", 0)
    articles_dir = DATA_ROOT / str(season) / "articles"
    out_path     = articles_dir / f"week_{int(week_num):02d}_recap.json"

    if out_path.exists() and not force:
        print(f"[ci_runner] Recap article for week {week_num} already exists — skipping. Use --force to regenerate.")
        return True

    # Validate data quality before spending an API call on article generation
    is_valid, issues = _validate_week_data(week_data, season)
    for issue in issues:
        print(f"[ci_runner] {issue}", file=sys.stderr if issue.startswith("CRITICAL") else sys.stdout)
    if not is_valid:
        print("[ci_runner] Aborting article generation due to critical data issues.", file=sys.stderr)
        return False

    # Enrich top_players with real MLB game log data for the week
    if _MLB_STATS_AVAILABLE and week_data.get("top_players"):
        generated_at = week_data.get("generated_at", "")
        week_start, week_end = week_date_range(generated_at) if generated_at else (None, None)
        season_year = int(season)
        print(f"[ci_runner] Enriching top players with MLB Stats API ({week_start} → {week_end})…")
        try:
            week_data["top_players"] = enrich_top_players(
                week_data["top_players"], year=season_year,
                week_start=week_start, week_end=week_end, max_players=8,
            )
            enriched = sum(1 for p in week_data["top_players"] if p.get("mlb_id"))
            print(f"[ci_runner]   ✓ Enriched {enriched} players with real stats")
        except Exception as e:
            print(f"[ci_runner] MLB Stats enrichment failed (non-fatal): {e}", file=sys.stderr)

    # Load supporting data
    season_history = _load_season_history(season)
    records        = _load_records(season)

    print(f"[ci_runner] Calculating luck index through week {week_num}…")
    luck_index = _calculate_luck_index(season, through_week=int(week_num))

    print(f"[ci_runner] Checking records for week {week_num}…")
    records, broken_records = _check_and_update_records(week_data, int(week_num), records)
    if broken_records:
        print(f"[ci_runner]   {len(broken_records)} record(s) broken this week!")
        for br in broken_records:
            print(f"    {br['record']}: {br['new_value']} by {br['team']} (prev: {br['prev_value']} by {br['prev_team']})")

    print(f"[ci_runner] Generating recap article for week {week_num} (two-pass)…")
    article = generate_recap_article(
        week_data=week_data,
        season=season,
        season_history=season_history,
        records=records,
        luck_index=luck_index,
        next_week_schedule=next_week_schedule or [],
    )
    if not article:
        print("[ci_runner] Article generation failed — season_history and records NOT updated.", file=sys.stderr)
        return False

    # Persist article
    articles_dir.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(article, f, indent=2, ensure_ascii=False)
    print(f"[ci_runner]   ✓ Saved {out_path.name} (by {article['writer_name']})")

    # Only commit updated season_history and records after a successful article write
    _save_season_history(season, season_history)
    print(f"[ci_runner]   ✓ Updated season_history.json")
    _save_records(season, records)
    print(f"[ci_runner]   ✓ Updated records.json")

    return True


def run_save_data(week_data: dict, season: int, week: int) -> None:
    """Save week data JSON to data/{season}/week_NN.json."""
    season_dir = DATA_ROOT / str(season)
    season_dir.mkdir(parents=True, exist_ok=True)
    out_path = season_dir / f"week_{int(week):02d}.json"
    with open(out_path, "w") as f:
        json.dump({**week_data, "saved_at": datetime.now().isoformat()}, f, indent=2, default=str)
    print(f"[ci_runner] Data saved to {out_path.name}")


LEAGUE_KEYS = {
    2017: "370.l.36051",
    2021: "404.l.39098",
    2022: "412.l.49651",
    2023: "422.l.35047",
    2024: "431.l.29063",
    2025: "458.l.25686",
    2026: "469.l.10470",
}


def run_draft(oauth, league_key: str, season: int, force: bool = False) -> bool:
    """Fetch and save the full enriched draft board. Returns True on success."""
    out_path = DATA_ROOT / str(season) / "draft_results.json"
    if out_path.exists() and not force:
        print(f"[ci_runner] draft_results.json for {season} already exists — skipping. Use --force to regenerate.")
        return True

    print(f"[ci_runner] Fetching draft results for {season} ({league_key})…")
    try:
        session = oauth.get_session()
        picks = get_draft_results_enriched(session, league_key)
        if not picks:
            print("[ci_runner] No draft data returned (pre-season or unsupported).", file=sys.stderr)
            return False
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w") as f:
            json.dump(
                {"season": season, "league_key": league_key,
                 "fetched_at": datetime.now().isoformat(), "picks": picks},
                f, indent=2,
            )
        print(f"[ci_runner]   ✓ Saved draft_results.json ({len(picks)} picks)")
        return True
    except Exception as e:
        print(f"[ci_runner] Draft fetch failed: {e}", file=sys.stderr)
        return False


# ── Draft recap article generation ───────────────────────────────────────────

def generate_draft_recap(season: int) -> dict | None:
    """
    Generate a post-draft review article for `season`.

    Uses:
    - draft_results.json   — actual picks (team_key, player, round, pick#)
    - draft_order.json     — pick-slot → team name mapping
    - adp_snapshot.json    — ADP per player (dict keyed by player_key)
    - advanced_stats.json  — prior-season real stats for drafted players
    - historical draft_results.json files — past early-round picks per team
    - _build_historical_context()  — season finish records per team

    Returns article dict or None on failure.
    """
    # 1. Load current season draft results
    draft_results_file = DATA_ROOT / str(season) / "draft_results.json"
    if not draft_results_file.exists():
        print(f"[ci_runner] No draft_results.json for {season}.", file=sys.stderr)
        return None
    with open(draft_results_file, encoding="utf-8") as f:
        draft_results = json.load(f)
    picks = draft_results.get("picks", [])
    if not picks:
        print(f"[ci_runner] No picks in draft_results.json for {season}.", file=sys.stderr)
        return None

    # 2. Build team_key → team_name.
    #    Priority: draft_order.json (round-1 correlation) → week data matchup teams → team_key
    draft_order_file = DATA_ROOT / str(season) / "draft_order.json"
    team_key_to_name: dict[str, str] = {}
    draft_order_list: list[dict] = []
    draft_date = f"{season}-03-22"

    if draft_order_file.exists():
        with open(draft_order_file, encoding="utf-8") as f:
            draft_order_data = json.load(f)
        draft_order_list = draft_order_data.get("draft_order", [])
        draft_date       = draft_order_data.get("draft_date", draft_date)
        round1 = sorted(
            [p for p in picks if p.get("round") == 1],
            key=lambda x: x.get("pick", 999),
        )
        for i, pk in enumerate(round1):
            if i < len(draft_order_list):
                team_key_to_name[pk["team_key"]] = draft_order_list[i].get("team", pk["team_key"])

    # Fallback: scan this season's week data for team_key → team name from matchup teams
    if not team_key_to_name:
        season_dir = DATA_ROOT / str(season)
        for wf in sorted(season_dir.glob("week_*.json")):
            try:
                with open(wf, encoding="utf-8") as f:
                    wd = json.load(f)
                for m in wd.get("matchups", []):
                    for t in m.get("teams", []):
                        tk = t.get("team_key", "")
                        nm = t.get("name", "")
                        if tk and nm:
                            team_key_to_name[tk] = nm
                if team_key_to_name:
                    break  # one week file is enough to build the map
            except Exception:
                pass

    # If still missing names, use team_key as the display name
    for pk in picks:
        if pk["team_key"] not in team_key_to_name:
            team_key_to_name[pk["team_key"]] = pk["team_key"]

    # If no draft_order.json, synthesize draft_order_list from round-1 picks in pick order
    if not draft_order_list:
        round1_sorted = sorted(
            [p for p in picks if p.get("round") == 1],
            key=lambda x: x.get("pick", 999),
        )
        draft_order_list = [
            {"pick": pk.get("pick", i + 1), "team": team_key_to_name.get(pk["team_key"], pk["team_key"])}
            for i, pk in enumerate(round1_sorted)
        ]

    # 3. Load ADP snapshot (dict keyed by player_key)
    adp_players: dict = {}
    adp_file = DATA_ROOT / str(season) / "adp_snapshot.json"
    if adp_file.exists():
        with open(adp_file, encoding="utf-8") as f:
            adp_players = json.load(f).get("players", {})

    # 4. Advanced stats for player context.
    #    For completed past seasons: use same-season stats (retrospective — how they actually did).
    #    For current/future season: use prior-season stats (pre-draft scouting).
    prev_season = season - 1
    same_season_adv_file = DATA_ROOT / str(season) / "advanced_stats.json"
    prior_season_adv_file = DATA_ROOT / str(prev_season) / "advanced_stats.json"
    is_retrospective = same_season_adv_file.exists()
    adv_file  = same_season_adv_file if is_retrospective else prior_season_adv_file
    stats_year = season if is_retrospective else prev_season
    player_stats_by_name: dict[str, dict] = {}
    if adv_file.exists():
        with open(adv_file, encoding="utf-8") as f:
            adv_data = json.load(f)
        for p in adv_data.get("batting", []):
            if p.get("name"):
                player_stats_by_name[p["name"].lower()] = {"_type": "batter", **p}
        for p in adv_data.get("pitching", []):
            if p.get("name"):
                player_stats_by_name[p["name"].lower()] = {"_type": "pitcher", **p}

    # 5. Historical early-round picks (rounds 1-5) from the past 3 seasons
    hist_picks_by_team: dict[str, list[dict]] = {}
    for yr in range(max(season - 3, 2022), season):
        h_draft_file = DATA_ROOT / str(yr) / "draft_results.json"
        h_order_file = DATA_ROOT / str(yr) / "draft_order.json"
        if not h_draft_file.exists():
            continue
        try:
            with open(h_draft_file, encoding="utf-8") as f:
                h_picks = json.load(f).get("picks", [])
            h_key_to_name: dict[str, str] = {}
            if h_order_file.exists():
                with open(h_order_file, encoding="utf-8") as f:
                    h_order = json.load(f).get("draft_order", [])
                h_round1 = sorted(
                    [p for p in h_picks if p.get("round") == 1],
                    key=lambda x: x.get("pick", 999),
                )
                for i, pk in enumerate(h_round1):
                    if i < len(h_order):
                        h_key_to_name[pk["team_key"]] = h_order[i].get("team", pk["team_key"])
            for pk in h_picks:
                if pk.get("round", 99) > 5:
                    continue
                tname = h_key_to_name.get(pk["team_key"], pk["team_key"])
                hist_picks_by_team.setdefault(tname, []).append({
                    "year": yr,
                    "round": pk.get("round"),
                    "pick": pk.get("pick"),
                    "player_name": pk.get("player_name"),
                    "position": pk.get("position"),
                })
        except Exception:
            pass

    # 6. Historical season finish records (last 3 seasons)
    hist_records = _build_historical_context(season, lookback=3)

    # 7. Organize current picks by team
    picks_by_team: dict[str, list[dict]] = {}
    for pk in picks:
        tname = team_key_to_name.get(pk["team_key"], pk["team_key"])
        picks_by_team.setdefault(tname, []).append(pk)

    # 8. Build per-team context blocks
    team_sections: list[str] = []
    for entry in draft_order_list:
        team_name = entry.get("team", "")
        if not team_name:
            continue
        team_picks = sorted(picks_by_team.get(team_name, []), key=lambda x: x.get("pick", 999))

        pick_lines: list[str] = []
        steals:  list[str] = []
        reaches: list[str] = []
        for pk in team_picks[:15]:
            pkey     = pk.get("player_key", "")
            pick_num = pk.get("pick", 0)
            adp_entry = adp_players.get(pkey, {})
            adp_val   = adp_entry.get("adp", 0)
            delta = ""
            if adp_val and pick_num:
                diff = pick_num - adp_val  # positive = fell past ADP (steal), negative = taken before ADP (reach)
                if diff >= 10:
                    delta = f" [STEAL: ADP {adp_val:.0f}, fell {diff:.0f} picks]"
                    steals.append(pk.get("player_name", "?"))
                elif diff <= -10:
                    delta = f" [REACH: ADP {adp_val:.0f}, taken {-diff:.0f} picks early]"
                    reaches.append(pk.get("player_name", "?"))

            stats_note = ""
            pname_key = pk.get("player_name", "").lower()
            if pname_key in player_stats_by_name:
                ps = player_stats_by_name[pname_key]
                parts: list[str] = []
                if ps.get("_type") == "batter":
                    if ps.get("war"):      parts.append(f"{ps['war']:.1f} WAR")
                    if ps.get("wrc_plus"): parts.append(f"wRC+ {ps['wrc_plus']:.0f}")
                    if ps.get("hr"):       parts.append(f"{ps['hr']:.0f} HR")
                else:
                    if ps.get("war"):  parts.append(f"{ps['war']:.1f} WAR")
                    if ps.get("era"):  parts.append(f"{ps['era']:.2f} ERA")
                    if ps.get("fip"):  parts.append(f"FIP {ps['fip']:.2f}")
                if parts:
                    stats_note = f" ({stats_year}: {', '.join(parts)})"

            pick_lines.append(
                f"    Rd {pk.get('round','?')}, Pick {pick_num}: "
                f"{pk.get('player_name','?')} ({pk.get('position','?')}, "
                f"{pk.get('mlb_team','?')}){stats_note}{delta}"
            )

        # Historical record summary
        hist = hist_records.get(team_name, {})
        hist_summary = ""
        if hist:
            seasons_detail = ", ".join(
                f"{sd['year']}: #{sd['rank']}"
                for sd in sorted(hist.get("seasons_data", []), key=lambda x: x["year"])
            )
            champ_note = f", {hist['championships']}x champion" if hist.get("championships") else ""
            hist_summary = f"Recent finishes: {seasons_detail}{champ_note}"

        # Historical early picks summary
        h_early = hist_picks_by_team.get(team_name, [])
        hist_picks_ctx = ""
        if h_early:
            by_year: dict[int, list[str]] = {}
            for hp in h_early:
                by_year.setdefault(hp["year"], []).append(
                    f"Rd{hp['round']} {hp['player_name']} ({hp['position']})"
                )
            hist_picks_ctx = "Historical early picks: " + "; ".join(
                f"{yr}: {', '.join(ps[:4])}"
                for yr, ps in sorted(by_year.items())
            )

        lines = [f"TEAM: {team_name} (Draft Pick #{entry.get('pick','?')})"]
        if hist_summary:       lines.append(hist_summary)
        if hist_picks_ctx:     lines.append(hist_picks_ctx)
        if steals:             lines.append(f"Notable steals: {', '.join(steals)}")
        if reaches:            lines.append(f"Potential reaches: {', '.join(reaches)}")
        lines.append(f"{season} Draft picks:")
        lines.extend(pick_lines if pick_lines else ["    (no picks recorded)"])
        team_sections.append("\n".join(lines))

    all_teams_ctx = "\n\n".join(team_sections)

    # Build explicit round-1 summary to anchor the prompt — prevents hallucination of pick order
    round1_picks = sorted([p for p in picks if p.get("round") == 1], key=lambda x: x.get("pick", 999))
    round1_summary = "\n".join(
        f"  Pick {p['pick']:>2}: {team_key_to_name.get(p['team_key'], p['team_key'])} → {p.get('player_name','?')} ({p.get('position','?')}, {p.get('mlb_team','?')})"
        for p in round1_picks
    )

    # 9. Build prompt and call Claude
    writer_key = "simmons"
    writer = WRITER_STYLES[writer_key]

    # Retrospective (past season): we know how the season actually unfolded — lean into that.
    # Preview (current/future season): we're writing pre-season analysis with uncertainty.
    if is_retrospective:
        stats_framing = (
            f"You also have the {stats_year} actual season stats for the players drafted — "
            f"so this is a RETROSPECTIVE review. You know how the season ended. "
            f"Hold teams accountable for their picks. Who was vindicated? Who got burned?"
        )
        section_v = f"""**V. The Verdict: How the Draft Shaped the {season} Season**
   - Now that the season is over, how did the draft grades hold up?
   - Which teams won or lost the season because of their draft?
   - Which individual picks were the difference-makers?
   - 3–4 paragraphs. Be specific. Use the actual season stats provided."""
        section_vi = f"""**VI. The {season} Draft: Final Grades & Legacy**
   - Letter grade for the draft class as a whole
   - The best and worst drafting decisions in retrospect
   - A memorable closing line about what the {season} draft will be remembered for"""
        adp_note = ("ADP data not available for this season — evaluate picks based on round value "
                    "and actual performance." if not adp_players else
                    "ADP context provided — STEAL = picked well below ADP, REACH = above ADP.")
    else:
        stats_framing = (
            f"You have {stats_year} player stats for pre-draft scouting context — "
            f"these are the numbers that informed draft decisions. Write as if you're "
            f"analyzing the draft right after it happened, before the season begins."
        )
        section_v = f"""**V. Five Bold Predictions for {season}**
   - Each must be specific, grounded in the actual draft data, and arguable
   - Reference team names and player names
   - Make them memorable"""
        section_vi = f"""**VI. The Pick: Champion Crowned**
   - Based on the draft, name your title contender with conviction
   - Build the case using their picks, history, and draft position
   - End with a memorable closing line (this is the Simmons sign-off, make it count)"""
        adp_note = ("ADP context provided — STEAL = picked well below ADP, REACH = above ADP."
                    if adp_players else
                    "ADP data not available for this season — evaluate picks based on round value and historical context.")

    prompt = f"""VERIFIED DRAFT FACTS — READ THIS FIRST BEFORE ANYTHING ELSE.
These are the ACTUAL picks from the live {season} MillerLite® BeerLeagueBaseball draft.
Do NOT contradict or alter any of these. They override anything in your training data.

ROUND 1 (in order):
{round1_summary}

The first overall pick was: {round1_picks[0].get('player_name','?')} by {team_key_to_name.get(round1_picks[0]['team_key'],'?')}.
Write every fact in your article to be consistent with the above.

---

You are {writer['name']} of {writer['outlet']}, writing the definitive {season} draft review for "MillerLite® BeerLeagueBaseball."

{writer['voice']}

You have REAL DATA for all 14 teams: actual picks, each team's finish positions from past seasons, and real player stats. {stats_framing}

{adp_note}

Use this data. Be specific. Reference player names, round numbers, and historical records. Make it feel like you actually watched every pick in the war room.

LEAGUE STRUCTURE:
- 14 teams, head-to-head category scoring (12 categories: H/AB, R, HR, RBI, SB, OBP, IP, K, ERA, WHIP, QS, NSVH)
- Snake draft — early picks matter, but the middle rounds decide championships
- Draft date: {draft_date}

TEAM-BY-TEAM DRAFT DATA:
{all_teams_ctx}

Write a LONG, richly detailed draft review (2000–2500 words). Use Roman numeral section headers in bold.

**I. The War Room Opens** (2–3 paragraphs)
   - Set the scene. Draft day for a league of obsessed fantasy managers.
   - Tease the biggest steals, worst reaches, and surprise moves.
   - Pop culture reference or analogy to kick things off (this IS Bill Simmons after all).

**II. Draft Order & Early-Pick Breakdown** (1–2 paragraphs)
   - The VERIFIED Round 1 order is: {round1_summary}
   - Your section II MUST open by accurately describing who had pick 1 and who they selected — use the exact names from the verified data above. Do not substitute different players.
   - Note any notable first-round value or disasters.

**III. The Draft Grades: All 14 Teams** (the heart — ALL 14 teams, in draft pick order)
   For EACH team write 5–7 sentences:
   • Draft slot and first-round pick (name the player explicitly)
   • 2–3 key picks from rounds 2–10, including any steals or reaches if flagged
   • Qualitative description of each key pick's value — DO NOT invent or cite specific statistics (HR totals, ERA, WAR, etc.) unless the exact number appears in the verified draft data above. Instead use phrases like "coming off a monster year", "perennial 30-HR threat", "elite strikeout rate" without fabricating specific figures.
   • Historical finish trajectory (are they a dynasty, a pretender, a rebuild?)
   • Historical drafting tendencies if the data shows patterns
   • A letter grade (A through F) with a sharp one-line justification
   Be brutally honest and funny in Simmons's voice. Parenthetical asides welcome. If a team reached on a 75-wRC+ bat, say so. If a history of blown picks exists, reference it.

**IV. Draft Day Heroes & Villains**
   - The 3 best value picks of the entire draft (cite round, pick #, player, and why)
   - The 3 worst reaches or puzzling decisions (same format)
   {"- Use real ADP numbers from the data" if adp_players else "- Use round value and actual performance to judge value"}

{section_v}

{section_vi}

Use **bold** for team and player names throughout. Markdown OK.

Wrap your response in XML tags exactly like this — no JSON, no preamble:
<subheadline>your one sharp sentence that makes readers want to read the whole thing</subheadline>
<body>
full article, 2000–2500 words — markdown ok
</body>"""

    # Build a factual round-1 opener that Claude cannot hallucinate
    r1_narrative = ", ".join(
        f"**{team_key_to_name.get(p['team_key'], p['team_key'])}** took **{p.get('player_name','?')}** ({p.get('position','?')})"
        for p in round1_picks
    )

    precommit = (
        f"Round 1 picks in order: {round1_summary}\n"
        f"The first overall pick was {round1_picks[0].get('player_name','?')} "
        f"by {team_key_to_name.get(round1_picks[0]['team_key'],'?')}. "
        f"These are facts from the live draft and must not be contradicted in the article."
    )

    # Build headline programmatically from verified data — model cannot hallucinate this
    p1_player = round1_picks[0].get('player_name', '?').split('(')[0].strip()
    p1_team   = team_key_to_name.get(round1_picks[0]['team_key'], '?')
    # Find biggest steal across all rounds: steal = pick_num > adp_val (player fell past consensus)
    best_steal_note = ""
    best_delta = 0
    for pk in picks:
        if pk.get('round', 99) > 20:  # ignore garbage-time picks where ADP is unreliable
            continue
        adp_val = adp_players.get(pk.get('player_key', ''), {}).get('adp', 0)
        pick_num = pk.get('pick', 0)
        if adp_val and pick_num:
            delta = pick_num - adp_val  # positive = fell past ADP = steal
            if delta > best_delta:
                best_delta = delta
                steal_team = team_key_to_name.get(pk['team_key'], '')
                steal_player = pk.get('player_name', '').split('(')[0].strip()
                steal_pick   = pick_num
                best_steal_note = f"{steal_team} snagging {steal_player} at Pick {steal_pick} (ADP {adp_val:.0f})"
    headline = f"{p1_player} Goes First Overall to {p1_team}"
    if best_steal_note:
        headline += f", and {best_steal_note} Was the Steal of the Draft"

    for attempt in range(3):
        try:
            raw = _call_claude(prompt, max_tokens=8000, precommit_facts=precommit)
            sub_match  = re.search(r'<subheadline>(.*?)</subheadline>', raw, re.DOTALL)
            # Accept body even if closing tag is missing (token cutoff)
            body_match = re.search(r'<body>(.*?)(?:</body>|$)', raw, re.DOTALL)
            if not (sub_match and body_match):
                raise ValueError(f"Missing XML tags in response (attempt {attempt+1}): {raw[:200]}")
            body_text = body_match.group(1).strip()
            article = {
                "headline":      headline,
                "subheadline":   sub_match.group(1).strip(),
                "body":          body_text,
                "generated_at":  datetime.now().isoformat(),
                "season":        season,
                "writer_key":    writer_key,
                "writer_name":   writer["name"],
                "writer_outlet": writer["outlet"],
                "type":          "draft_recap",
            }
            return article
        except Exception as e:
            print(f"[ci_runner] Draft recap generation failed (attempt {attempt+1}/3): {e}", file=sys.stderr)
            if attempt == 2:
                return None


def run_draft_recap(season: int, force: bool = False) -> bool:
    """Generate draft recap article. Returns True on success."""
    articles_dir = DATA_ROOT / str(season) / "articles"
    out_path     = articles_dir / "draft_recap.json"

    if out_path.exists() and not force:
        print(f"[ci_runner] Draft recap for {season} already exists — skipping. Use --force to regenerate.")
        return True

    draft_results_file = DATA_ROOT / str(season) / "draft_results.json"
    if not draft_results_file.exists():
        print(f"[ci_runner] No draft_results.json for {season}. Run --mode draft first.", file=sys.stderr)
        return False

    print(f"[ci_runner] Generating {season} draft recap…")
    article = generate_draft_recap(season)
    if not article:
        return False

    articles_dir.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(article, f, indent=2, ensure_ascii=False)
    print(f"[ci_runner]   ✓ Saved draft_recap.json (by {article['writer_name']})")
    return True


# ═══════════════════════════════════════════════════════════════════════════════
# DISCORD WEBHOOK
# ═══════════════════════════════════════════════════════════════════════════════

def _discord_post(payload: dict) -> bool:
    """POST a Discord webhook payload. Returns True on success."""
    import urllib.request
    url = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
    if not url:
        return False
    try:
        body = json.dumps(payload).encode("utf-8")
        req  = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status in (200, 204)
    except Exception as e:
        print(f"[discord] Post failed: {e}", file=sys.stderr)
        return False


def discord_post_recap(article: dict, week_num: int, season: int) -> bool:
    """Post a weekly recap article to Discord as a rich embed."""
    GOLD = 0xF0C040
    week_meta = {22: "Wild Card", 23: "Semifinals", 24: "World Series"}
    round_label = week_meta.get(week_num, f"Week {week_num}")
    app_url = os.environ.get("STREAMLIT_APP_URL", "").rstrip("/")
    description = article.get("subheadline") or ""
    if len(description) > 300:
        description = description[:297] + "…"

    embed = {
        "title":       article.get("headline", f"{season} {round_label} Recap"),
        "description": description,
        "color":       GOLD,
        "fields": [
            {"name": "Season", "value": str(season),    "inline": True},
            {"name": "Week",   "value": round_label,    "inline": True},
            {"name": "Author", "value": f"{article.get('writer_name','')} · {article.get('writer_outlet','')}", "inline": False},
        ],
        "footer": {"text": "MillerLite® BeerLeagueBaseball"},
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }
    if app_url:
        embed["url"] = app_url

    content = f"**:newspaper: {season} {round_label} Recap is live!**"
    ok = _discord_post({"content": content, "embeds": [embed]})
    if ok:
        print(f"[discord] Posted recap for {season} {round_label}")
    return ok


def discord_post_trade(article: dict, season: int) -> bool:
    """Post a trade article to Discord."""
    AMBER = 0xF59E0B
    app_url = os.environ.get("STREAMLIT_APP_URL", "").rstrip("/")
    description = article.get("subheadline") or ""
    if len(description) > 300:
        description = description[:297] + "…"

    embed = {
        "title":       article.get("headline", "Trade Alert"),
        "description": description,
        "color":       AMBER,
        "fields": [
            {"name": "Author", "value": f"{article.get('writer_name','')} · {article.get('writer_outlet','')}", "inline": False},
        ],
        "footer": {"text": f"MillerLite® BeerLeagueBaseball · {season}"},
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }
    if app_url:
        embed["url"] = app_url

    ok = _discord_post({"content": ":arrows_counterclockwise: **Trade Alert**", "embeds": [embed]})
    if ok:
        print(f"[discord] Posted trade article: {article.get('headline','')[:60]}")
    return ok


def discord_post_preview(article: dict, season: int) -> bool:
    """Post a season preview article to Discord."""
    BLUE = 0x3B82F6
    app_url = os.environ.get("STREAMLIT_APP_URL", "").rstrip("/")
    description = article.get("subheadline") or ""
    if len(description) > 300:
        description = description[:297] + "…"

    embed = {
        "title":       article.get("headline", f"{season} Season Preview"),
        "description": description,
        "color":       BLUE,
        "fields": [
            {"name": "Author", "value": f"{article.get('writer_name','')} · {article.get('writer_outlet','')}", "inline": False},
        ],
        "footer": {"text": f"MillerLite® BeerLeagueBaseball · {season} Season"},
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }
    if app_url:
        embed["url"] = app_url

    ok = _discord_post({"content": f":baseball: **{season} Season Preview is here!**", "embeds": [embed]})
    if ok:
        print(f"[discord] Posted season preview for {season}")
    return ok


def main() -> None:
    parser = argparse.ArgumentParser(description="BeerLeagueBaseball CI runner")
    parser.add_argument("--mode",   choices=["trades", "recap", "full", "preview", "draft", "draft_recap", "backfill"], default="full")
    parser.add_argument("--week",   type=int, default=None, help="Override week number")
    parser.add_argument("--season", type=int, default=None, help="Override season year (used with --mode preview)")
    parser.add_argument("--force",  action="store_true", help="Regenerate even if article already exists")
    parser.add_argument("--dry-run", action="store_true", help="Don't write any files")
    args = parser.parse_args()

    # ── Draft mode ────────────────────────────────────────────────────────────
    if args.mode == "draft":
        season     = args.season or datetime.now().year
        league_key = os.environ.get("YAHOO_LEAGUE_KEY") or LEAGUE_KEYS.get(season, "")
        if not league_key:
            print(f"[ci_runner] No league key for {season}. Set YAHOO_LEAGUE_KEY.", file=sys.stderr)
            sys.exit(1)
        print(f"[ci_runner] Setting up Yahoo OAuth…")
        oauth = setup_ci_oauth()
        ok = run_draft(oauth, league_key, season, force=args.force)
        if not ok:
            sys.exit(1)
        print("[ci_runner] Done ✓")
        return

    # ── Draft recap mode (no Yahoo fetch needed) ─────────────────────────────
    if args.mode == "draft_recap":
        if args.season:
            # Single season
            ok = run_draft_recap(args.season, force=args.force)
            if not ok:
                print("[ci_runner] Draft recap generation failed.", file=sys.stderr)
                sys.exit(1)
        else:
            # Backfill all seasons that have draft_results.json
            seasons_with_draft = sorted(
                int(d.name)
                for d in DATA_ROOT.iterdir()
                if d.is_dir() and d.name.isdigit()
                and (d / "draft_results.json").exists()
            )
            if not seasons_with_draft:
                print("[ci_runner] No draft_results.json found in any season directory.", file=sys.stderr)
                sys.exit(1)
            generated = 0
            for s in seasons_with_draft:
                ok = run_draft_recap(s, force=args.force)
                if ok:
                    generated += 1
            print(f"[ci_runner] Draft recap backfill complete — {generated}/{len(seasons_with_draft)} article(s) generated ✓")
        print("[ci_runner] Done ✓")
        return

    # ── Season preview mode (no Yahoo fetch needed) ──────────────────────────
    if args.mode == "preview":
        season = args.season or datetime.now().year
        print(f"[ci_runner] Generating {season} season preview…")
        ok = run_preview(season, force=args.force)
        if not ok:
            print("[ci_runner] Season preview generation failed.", file=sys.stderr)
            sys.exit(1)
        # Post to Discord if webhook is configured
        articles_dir = DATA_ROOT / str(season) / "articles"
        preview_path = articles_dir / "season_preview.json"
        if preview_path.exists():
            with open(preview_path) as f:
                discord_post_preview(json.load(f), season)
        print("[ci_runner] Done ✓")
        return

    # ── Backfill mode — generate recaps from existing week JSON files ─────────
    if args.mode == "backfill":
        season = args.season or datetime.now().year
        season_dir = DATA_ROOT / str(season)
        if not season_dir.exists():
            print(f"[ci_runner] No data directory for {season}: {season_dir}", file=sys.stderr)
            sys.exit(1)

        week_files = sorted(season_dir.glob("week_*.json"))
        if args.week:
            week_files = [f for f in week_files if int(f.stem.split("_")[1]) == args.week]

        if not week_files:
            print(f"[ci_runner] No week files found for {season}" + (f" week {args.week}" if args.week else ""), file=sys.stderr)
            sys.exit(1)

        generated = 0
        for wf in week_files:
            try:
                wk_num = int(wf.stem.split("_")[1])
                out_path = DATA_ROOT / str(season) / "articles" / f"week_{wk_num:02d}_recap.json"
                if out_path.exists() and not args.force:
                    print(f"[ci_runner] Week {wk_num}: recap exists — skipping (use --force to regenerate)")
                    continue
                with open(wf, encoding="utf-8") as f:
                    week_data = json.load(f)
                week_data.setdefault("week", wk_num)
                week_data.setdefault("season", season)
                print(f"[ci_runner] Backfilling recap for {season} Week {wk_num}…")
                ok = run_recap(week_data, season, next_week_schedule=[])
                if ok:
                    generated += 1
            except Exception as e:
                print(f"[ci_runner] Failed on {wf.name}: {e}", file=sys.stderr)

        print(f"[ci_runner] Backfill complete — {generated} article(s) generated for {season} ✓")
        return

    league_key = os.environ.get("YAHOO_LEAGUE_KEY", "")
    if not league_key:
        print("Error: YAHOO_LEAGUE_KEY not set.", file=sys.stderr)
        sys.exit(1)

    # Set up Yahoo OAuth (CI mode — no browser)
    print("[ci_runner] Setting up Yahoo OAuth…")
    oauth = setup_ci_oauth()

    # Fetch league data — any failure here aborts the run with non-zero exit
    print(f"[ci_runner] Fetching Yahoo data (week={args.week or 'latest'})…")
    try:
        week_data = fetch_weekly_data(oauth, league_key, week=args.week)
    except Exception as e:
        print(f"[ci_runner] FATAL: Yahoo API fetch failed: {e}", file=sys.stderr)
        print("[ci_runner] Aborting — no files written, no article published.", file=sys.stderr)
        sys.exit(1)

    season   = week_data.get("season", datetime.now().year)
    week_num = week_data.get("week", 0)
    print(f"[ci_runner] Got data for {season} Week {week_num}")

    # Fetch next week's schedule for next-week preview in the article
    next_week_schedule: list[dict] = []
    if args.mode in ("recap", "full"):
        try:
            session = oauth.get_session()
            next_week_schedule = fetch_next_week_schedule(session, league_key, int(week_num))
            print(f"[ci_runner] Fetched next week schedule ({len(next_week_schedule)} matchups)")
        except Exception as e:
            print(f"[ci_runner] FATAL: next week schedule fetch failed: {e}", file=sys.stderr)
            print("[ci_runner] Aborting — no files written, no article published.", file=sys.stderr)
            sys.exit(1)

    if args.dry_run:
        print("[ci_runner] --dry-run: showing week data summary (no files written, no Claude call).")
        print(f"\n=== Week {week_num} Matchups ===")
        for m in week_data.get("matchups", []):
            teams = m.get("teams", [])
            if len(teams) < 2:
                continue
            t1, t2 = teams[0], teams[1]
            print(f"  {t1['name']} ({t1['points']}) vs {t2['name']} ({t2['points']})")
            for t in [t1, t2]:
                players = t.get("top_players", [])
                if players:
                    print(f"    {t['name']} contributors:")
                    for p in players:
                        print(f"      {p['name']} ({p.get('position','?')}, {p.get('mlb_team','?')}): {p.get('stats','')}")
        print(f"\n=== Standings ===")
        for s in week_data.get("standings", [])[:10]:
            print(f"  {s.get('rank')}. {s['name']}: {s.get('wins',0)}-{s.get('losses',0)}")
        return

    # Guard: skip saving if there are no regular-season matchups with real points.
    # This prevents stale playoff data from being written every 4 hours during
    # the off-season (e.g. 2026 league key returning 2025 week-23 playoff data).
    matchups = week_data.get("matchups", [])
    regular_with_points = [
        m for m in matchups
        if not m.get("is_playoffs") and not m.get("is_consolation")
        and any(t.get("points", 0) > 0 for t in m.get("teams", []))
    ]
    if not regular_with_points:
        print(
            f"[ci_runner] Skipping data save for {season} Week {week_num}: "
            "no regular-season matchups with points (off-season or pre-season)."
        )
    else:
        run_save_data(week_data, season, week_num)

    # Trade articles
    if args.mode in ("trades", "full"):
        new_trade_articles = run_trades(week_data, season)
        print(f"[ci_runner] Trade articles written: {len(new_trade_articles)}")
        for article in new_trade_articles:
            discord_post_trade(article, season)

    # Weekly recap
    if args.mode in ("recap", "full"):
        ok = run_recap(
            week_data, season,
            force=args.force,
            next_week_schedule=next_week_schedule,
        )
        if not ok:
            print("[ci_runner] Recap article generation failed.", file=sys.stderr)
            sys.exit(1)
        # Post recap to Discord
        articles_dir = DATA_ROOT / str(season) / "articles"
        recap_path   = articles_dir / f"week_{int(week_num):02d}_recap.json"
        if recap_path.exists():
            with open(recap_path) as f:
                discord_post_recap(json.load(f), week_num, season)

    print("[ci_runner] Done ✓")


if __name__ == "__main__":
    main()
