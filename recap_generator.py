"""
Generates a weekly fantasy baseball recap using the Anthropic API.

Uses Claude Opus 4.6 with adaptive thinking and streaming to produce
a fun, stats-grounded column in the style of a sports writer.
"""

from __future__ import annotations

from datetime import datetime

import anthropic

import credentials


SYSTEM_PROMPT = """You are a sharp, witty fantasy baseball columnist — think Bill Simmons meets
Peter Gammons. Your job is to write the weekly recap for a fantasy baseball league.

Style guidelines:
- Lead with the most compelling storyline of the week (biggest upset, dominant performance, etc.)
- Ground every observation in specific numbers: category scores, stat lines, standings records
- Reference the category-by-category breakdown when it's interesting (e.g. "dominated ERA 1.84 to 4.92")
- Use vivid baseball analogies and pop-culture references sparingly but effectively
- Give each matchup a one-sentence "headline" treatment, then dive into 1-2 that deserve more ink
- For CHAMPIONSHIP weeks: treat this with full drama — this is the title game, someone's season ends here
- For PLAYOFF weeks: acknowledge the stakes — every category point matters, this isn't the regular season
- For CONSOLATION matchups: give each consolation game a proper paragraph with category breakdown highlights — these managers still care, treat their matchups with respect (a touch of dark humor about missing the playoffs is fine, but don't shortchange them)
- Acknowledge heartbreaking losses with empathy and winning performances with appropriate hype
- Keep the tone conversational and fun — this is a friends' league, not ESPN
- End with a "Week Ahead" tease of interesting upcoming matchups or waiver wire topics
- Length: 500–700 words. Punchy, not padded.

Stat notes (lower is better for ERA and WHIP — a team "winning" ERA means their ERA was lower):
DO NOT make up player stats. Work only with the data provided."""


def _category_breakdown(t1: dict, t2: dict, lower_is_better: set[str]) -> list[str]:
    """
    Build a list of category comparison lines between two teams.
    Returns lines like: "  HR:  8  vs  3  → Team A wins"
    """
    cats1 = t1.get("category_stats", {})
    cats2 = t2.get("category_stats", {})
    all_cats = sorted(set(cats1) | set(cats2))
    if not all_cats:
        return []

    lines = []
    for cat in all_cats:
        v1 = cats1.get(cat, "-")
        v2 = cats2.get(cat, "-")
        try:
            f1 = float(v1.split("/")[0]) if "/" not in v1 or cat == "H/AB" else None
            f2 = float(v2.split("/")[0]) if "/" not in v2 or cat == "H/AB" else None
            if f1 is not None and f2 is not None and f1 != f2:
                if cat in lower_is_better:
                    winner_name = t1["name"] if f1 < f2 else t2["name"]
                else:
                    winner_name = t1["name"] if f1 > f2 else t2["name"]
                lines.append(f"    {cat:6s}: {v1:8s} vs {v2:8s}  → {winner_name}")
            else:
                lines.append(f"    {cat:6s}: {v1:8s} vs {v2:8s}  (tied)")
        except (ValueError, AttributeError):
            lines.append(f"    {cat:6s}: {v1:8s} vs {v2:8s}")
    return lines


def _build_data_prompt(data: dict) -> str:
    """Format the fetched league data into a structured prompt for Claude."""
    lines: list[str] = []
    lower_is_better: set[str] = set(data.get("lower_is_better_stats", []))

    lines.append(f"# {data['league_name']} — Week {data['week']} Recap Data")
    lines.append(f"(Generated: {datetime.now().strftime('%A, %B %d, %Y')})\n")

    # --- Week context ---
    playoff_games = [m for m in data["matchups"] if m.get("is_playoffs") and not m.get("is_consolation")]
    is_championship_week = any(m.get("is_championship") for m in data["matchups"])
    is_playoff_week = bool(playoff_games)

    if is_championship_week:
        lines.append("## *** CHAMPIONSHIP WEEK ***")
        lines.append("The [CHAMPIONSHIP] matchup is the TITLE GAME — crown the champion, maximum drama.")
        lines.append("The [3RD PLACE] matchup is for 3rd/4th place — meaningful but NOT the championship.")
        lines.append("Do NOT confuse these two. Only the [CHAMPIONSHIP] game winner is the league champion.\n")
    elif is_playoff_week:
        lines.append("## *** PLAYOFF WEEK ***")
        lines.append("This is a PLAYOFF week. Non-consolation matchups determine who advances to the championship.")
        lines.append("Consolation bracket matchups are marked [CONSOLATION] — still pride on the line.\n")
    else:
        lines.append("## Regular Season Week\n")

    # --- Matchup Results with category breakdowns ---
    lines.append("## Matchup Results (with category-by-category breakdown)")
    lines.append(f"  Categories: {', '.join(sorted(set().union(*[t.get('category_stats', {}).keys() for m in data['matchups'] for t in m['teams']])))}")
    lines.append(f"  Lower-is-better categories: {', '.join(sorted(lower_is_better)) or 'ERA, WHIP'}\n")

    for m in data["matchups"]:
        teams = m["teams"]
        if len(teams) < 2:
            continue
        t1, t2 = teams[0], teams[1]

        # Build matchup label
        if m.get("is_championship"):
            label = "[CHAMPIONSHIP]"
        elif m.get("is_third_place"):
            label = "[3RD PLACE]"
        elif m.get("is_consolation"):
            label = "[CONSOLATION]"
        elif m.get("is_playoffs"):
            label = "[PLAYOFF]"
        else:
            label = ""

        if m["is_tied"]:
            result = f"TIE  {t1['name']} {t1['points']:.2f}  vs  {t2['name']} {t2['points']:.2f}"
        else:
            winner = t1 if t1["team_key"] == m.get("winner_key") else t2
            loser = t2 if winner is t1 else t1
            margin = abs(t1["points"] - t2["points"])
            result = (
                f"WIN  {winner['name']} {winner['points']:.2f}"
                f"  def.  {loser['name']} {loser['points']:.2f}"
                f"  (margin: {margin:.2f} cats)"
            )

        lines.append(f"  {label} {result}")
        lines.append(f"    {t1['name']} (mgr: {t1['manager']})  vs  {t2['name']} (mgr: {t2['manager']})")

        # Category breakdown
        cat_lines = _category_breakdown(t1, t2, lower_is_better)
        if cat_lines:
            lines.extend(cat_lines)
        lines.append("")

    # --- Team scores ranked ---
    all_teams = [t for m in data["matchups"] for t in m["teams"]]
    all_teams_sorted = sorted(all_teams, key=lambda x: x["points"], reverse=True)
    lines.append("## Category Points Scored This Week (ranked)")
    for rank, t in enumerate(all_teams_sorted, 1):
        lines.append(f"  {rank:2d}. {t['name']:30s}  {t['points']:.2f} pts")
    lines.append("")

    # --- Standings ---
    lines.append("## Current Standings")
    for s in data["standings"]:
        record = f"{s['wins']}-{s['losses']}"
        if s["ties"]:
            record += f"-{s['ties']}"
        lines.append(
            f"  {s['rank']:2d}. {s['name']:30s}  {record:8s}  "
            f"PF: {s['points_for']:.1f}  PA: {s['points_against']:.1f}"
        )
    lines.append("")

    # --- Top Player Performances ---
    if data.get("top_players"):
        lines.append(f"## Top Individual Player Performances (Week {data['week']})")
        for i, p in enumerate(data["top_players"][:10], 1):
            lines.append(
                f"  {i:2d}. {p['name']:25s}  {p['position']:4s}  "
                f"{p['mlb_team']:25s}  {p['points']:.2f} pts"
            )
        lines.append("")

    # --- Transactions ---
    if data.get("transactions"):
        lines.append("## Recent Transactions")
        seen = set()
        shown = 0
        for tx in data["transactions"]:
            if shown >= 15:
                break
            tx_type = tx["type"].upper()
            player_names = [p["name"] for p in tx["players"]]
            key = (tx_type, tuple(sorted(player_names)))
            if key in seen:
                continue
            seen.add(key)

            if tx_type in ("ADD", "DROP", "ADD/DROP"):
                for p in tx["players"]:
                    action = p["action"].upper()
                    lines.append(
                        f"  {action:8s}  {p['name']:25s} ({p['position']:4s})  "
                        f"→ {p['team']}"
                    )
            elif tx_type == "TRADE":
                lines.append(f"  TRADE: {' / '.join(player_names)}")
            shown += 1
        lines.append("")

    return "\n".join(lines)


def generate_recap(data: dict) -> str:
    """
    Call Claude Opus 4.6 with the formatted league data and stream back the recap.
    Returns the full recap text.
    """
    api_key = credentials.get_secret("ANTHROPIC_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "ANTHROPIC_API_KEY is not set.\n"
            "Run  python setup_keys.py  to store it in Keychain."
        )

    client = anthropic.Anthropic(api_key=api_key)
    data_prompt = _build_data_prompt(data)

    print("\n--- Claude is writing your recap (streaming) ---\n")

    recap_text = ""
    with client.messages.stream(
        model="claude-sonnet-4-5",
        max_tokens=2048,
        system=SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": (
                    f"Write this week's fantasy baseball recap column based on the data below.\n\n"
                    f"{data_prompt}"
                ),
            }
        ],
    ) as stream:
        for event in stream:
            if event.type == "content_block_delta":
                if event.delta.type == "text_delta":
                    print(event.delta.text, end="", flush=True)
                    recap_text += event.delta.text

        final = stream.get_final_message()

    print("\n\n--- Recap complete ---")
    print(
        f"(Tokens used — input: {final.usage.input_tokens}, "
        f"output: {final.usage.output_tokens})"
    )

    return recap_text
