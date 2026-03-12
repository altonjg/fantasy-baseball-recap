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
    DISCORD_WEBHOOK_URL   if you want Discord posting from CI too
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
from yahoo_client import fetch_weekly_data

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


def _call_claude(prompt: str, max_tokens: int = 1024) -> str:
    client = _anthropic_client()
    msg = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = msg.content[0].text.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    return raw


def _safe_json_parse(raw: str) -> dict:
    """
    Attempt to parse JSON from Claude's response.
    Falls back to extracting the first {...} block if direct parse fails —
    handles cases where Claude adds extra text before or after the JSON.
    """
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Try extracting just the first complete JSON object
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            return json.loads(match.group())
        raise


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

def generate_recap_article(week_data: dict, standings: list[dict]) -> dict | None:
    is_champ   = any(m.get("is_championship") for m in week_data.get("matchups", []))
    is_playoff = any(m.get("is_playoffs") and not m.get("is_consolation")
                     for m in week_data.get("matchups", []))

    if is_champ:
        writer_key = _PLAYOFF_WRITER
    elif is_playoff:
        writer_key = random.choice([_PLAYOFF_WRITER] + _RECAP_WRITERS)
    else:
        writer_key = random.choice(_RECAP_WRITERS)

    writer   = WRITER_STYLES[writer_key]
    week_num = week_data.get("week", "?")
    league   = week_data.get("league_name", "MillerLite® BeerLeagueBaseball")

    matchup_lines = []
    for m in week_data.get("matchups", []):
        teams = m.get("teams", [])
        if len(teams) < 2:
            continue
        t1, t2 = teams[0], teams[1]
        label = (
            "[CHAMPIONSHIP] " if m.get("is_championship") else
            "[PLAYOFF] "      if m.get("is_playoffs") and not m.get("is_consolation") else
            "[CONSOLATION] "  if m.get("is_consolation") else ""
        )
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
        f"  {s['rank']}. {s['name']}: {s['wins']}-{s['losses']} ({s.get('points_for',0):.0f} PF)"
        for s in standings[:10]
    ) if standings else "  (unavailable)"

    top_players = week_data.get("top_players", [])
    top_ctx = "\n".join(
        f"  {p['name']} ({p.get('position','?')}, {p.get('mlb_team','?')}): {p.get('points',0):.1f} pts"
        for p in top_players[:5]
    )

    week_type = "CHAMPIONSHIP" if is_champ else "PLAYOFF" if is_playoff else "REGULAR SEASON"

    prompt = f"""You are {writer['name']} of {writer['outlet']}, writing a weekly column for "{league}."

{writer['voice']}

WEEK {week_num} ({week_type}) RESULTS:
{chr(10).join(matchup_lines)}

CURRENT STANDINGS (top 10):
{standings_ctx}

{"TOP PERFORMERS:" + chr(10) + top_ctx if top_ctx else ""}

Write a weekly recap column (350–500 words) in {writer['name']}'s authentic voice:
1. Open with the most compelling storyline
2. Cover 2–3 matchups in depth
3. Mention standout individual performances
4. Brief standings note on the playoff/title race
5. Tease what's next

Use **bold** for team names. Markdown OK. Write as if published on {writer['outlet']}.

Respond ONLY with valid JSON — no markdown fences:
{{
  "headline": "...",
  "subheadline": "...(one-sentence deck)...",
  "body": "...(full column)..."
}}"""

    try:
        raw     = _call_claude(prompt, max_tokens=1500)
        article = _safe_json_parse(raw)
        article["generated_at"]    = datetime.now().isoformat()
        article["week"]            = week_num
        article["writer_key"]      = writer_key
        article["writer_name"]     = writer["name"]
        article["writer_outlet"]   = writer["outlet"]
        article["is_playoff"]      = is_playoff
        article["is_championship"] = is_champ
        return article
    except Exception as e:
        print(f"[ci_runner] Recap article generation failed: {e}", file=sys.stderr)
        return None


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
    if not draft_file.exists():
        print(f"[ci_runner] No draft_order.json found for {season}.", file=sys.stderr)
        return None

    with open(draft_file, encoding="utf-8") as f:
        draft_data = json.load(f)

    draft_order = draft_data.get("draft_order", [])
    draft_date  = draft_data.get("draft_date", f"{season}-03-22")
    draft_notes = draft_data.get("notes", "Snake draft, live online")

    # Last season's final standings
    prev_season  = season - 1
    prev_dir     = DATA_ROOT / str(prev_season)
    prev_standings: list[dict] = []
    prev_champion = "Unknown"

    if prev_dir.exists():
        prev_files = sorted(prev_dir.glob("week_*.json"))
        if prev_files:
            try:
                with open(prev_files[-1], encoding="utf-8") as f:
                    prev_wd = json.load(f)
                prev_standings = prev_wd.get("standings", [])
                for m in prev_wd.get("matchups", []):
                    if m.get("is_championship") and not m.get("is_tied"):
                        teams = m.get("teams", [])
                        winner = next(
                            (t for t in teams if t.get("team_key") == m.get("winner_key")), None
                        )
                        if winner:
                            prev_champion = winner.get("name", "Unknown")  # team name only
            except Exception:
                pass

    # Build manager-name → team-name mapping from prev season standings
    # so we can resolve draft_order.json entries (which store manager names)
    mgr_to_team: dict[str, str] = {}
    for s in prev_standings:
        mgr_name  = s.get("manager", "")
        team_name = s.get("name", "")
        if mgr_name and team_name:
            mgr_to_team[mgr_name] = team_name

    # Recent records (last 2 seasons only — keeps context tight and relevant)
    alltime = _build_historical_context(season, lookback=2)

    # --- Build prompt context ---
    writer     = WRITER_STYLES["gammons"]

    # Draft order context — map manager names to team names where possible
    draft_lines = "\n".join(
        f"  Pick {p['pick']:2d}: {mgr_to_team.get(p['manager'], p['manager'])}"
        for p in draft_order
    )

    # Previous season standings — team names only
    prev_lines = "\n".join(
        f"  {s['rank']:2d}. {s.get('name')}: "
        f"{s['wins']}-{s['losses']} ({s.get('points_for', 0):.0f} PF)"
        for s in prev_standings
    ) if prev_standings else "  (not available)"

    # All-time records context
    alltime_lines = []
    for mgr, rec in sorted(alltime.items(), key=lambda x: -x[1]["wins"]):
        champ_str = f", {rec['championships']}x champ" if rec["championships"] else ""
        alltime_lines.append(
            f"  {mgr}: {rec['wins']}-{rec['losses']} all-time "
            f"({rec['seasons']} seasons{champ_str}, best finish: #{rec['best_rank']})"
        )
    alltime_ctx = "\n".join(alltime_lines) if alltime_lines else "  (no history available)"

    prompt = f"""You are {writer['name']} of {writer['outlet']}.

{writer['voice']}

You are writing the definitive {season} season preview for a 14-team fantasy baseball league called "MillerLite® BeerLeagueBaseball." This is a close-knit group of friends who have played together for years. You have real historical data — use it. Reference team names, records, and history. A touch of irreverent trash talk is not just permitted, it's expected.

IMPORTANT: Refer to all participants exclusively by their TEAM NAME — never use real names.

LEAGUE STRUCTURE:
- 14 teams, head-to-head category scoring (12 categories: H/AB, R, HR, RBI, SB, OBP, IP, K, ERA, WHIP, QS, NSVH)
- ERA and WHIP: lower is better
- Snake draft format: {draft_notes}
- Draft date: {draft_date}

{season} DRAFT ORDER (pick position = competitive advantage):
{draft_lines}

{prev_season} FINAL STANDINGS (defending champion: {prev_champion}):
{prev_lines}

RECENT RECORDS (last 2 seasons, {season - 2}–{season - 1}):
{alltime_ctx}

Write a full season preview (900–1100 words) structured as follows:
1. **Opening** — dramatic, poetic scene-setter for the {season} season. Reference the defending champion team. Set the stakes.
2. **Draft Order Breakdown** — who has the edge at the top vs. the bottom? What does draft position mean in this league's history?
3. **The Field** — go through all 14 teams. For each: 2–3 sentences covering their historical pedigree, what to expect in {season}, and a projected finish. Be specific. Use their all-time records. Roast the ones who deserve it. Hype the contenders.
4. **Bold Predictions** — exactly 5 specific, confident predictions for the {season} season
5. **The Pick** — one champion prediction with conviction

Use **bold** for team names. Markdown OK.

Respond ONLY with valid JSON — no markdown fences:
{{
  "headline": "...(punchy season preview headline)...",
  "subheadline": "...(one-sentence deck that makes you want to read it)...",
  "body": "...(full article)..."
}}"""

    try:
        raw     = _call_claude(prompt, max_tokens=2500)
        article = _safe_json_parse(raw)
        article["generated_at"]  = datetime.now().isoformat()
        article["season"]        = season
        article["writer_key"]    = "gammons"
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

def run_trades(week_data: dict, season: int) -> int:
    """Detect and write articles for new trades. Returns count of new articles."""
    trades_dir  = DATA_ROOT / str(season) / "trades"
    covered_ts  = _load_existing_article_timestamps(trades_dir)
    unprocessed = _find_unprocessed_trades(week_data, covered_ts)

    if not unprocessed:
        print("[ci_runner] No new trades detected.")
        return 0

    standings = week_data.get("standings", [])
    written   = 0
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
            written += 1
        else:
            print("[ci_runner]   ✗ Article generation failed", file=sys.stderr)

    return written


def run_recap(week_data: dict, season: int) -> bool:
    """Generate weekly recap article. Returns True on success."""
    week_num     = week_data.get("week", 0)
    articles_dir = DATA_ROOT / str(season) / "articles"
    out_path     = articles_dir / f"week_{int(week_num):02d}_recap.json"

    if out_path.exists():
        print(f"[ci_runner] Recap article for week {week_num} already exists — skipping.")
        return True

    standings = week_data.get("standings", [])
    print(f"[ci_runner] Generating recap article for week {week_num}…")
    article = generate_recap_article(week_data, standings)
    if not article:
        return False

    articles_dir.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(article, f, indent=2)
    print(f"[ci_runner]   ✓ Saved {out_path.name} (by {article['writer_name']})")
    return True


def run_save_data(week_data: dict, season: int, week: int) -> None:
    """Save week data JSON to data/{season}/week_NN.json."""
    season_dir = DATA_ROOT / str(season)
    season_dir.mkdir(parents=True, exist_ok=True)
    out_path = season_dir / f"week_{int(week):02d}.json"
    with open(out_path, "w") as f:
        json.dump({**week_data, "saved_at": datetime.now().isoformat()}, f, indent=2, default=str)
    print(f"[ci_runner] Data saved to {out_path.name}")


def main() -> None:
    parser = argparse.ArgumentParser(description="BeerLeagueBaseball CI runner")
    parser.add_argument("--mode",   choices=["trades", "recap", "full", "preview"], default="full")
    parser.add_argument("--week",   type=int, default=None, help="Override week number")
    parser.add_argument("--season", type=int, default=None, help="Override season year (used with --mode preview)")
    parser.add_argument("--force",  action="store_true", help="Regenerate even if article already exists")
    parser.add_argument("--dry-run", action="store_true", help="Don't write any files")
    args = parser.parse_args()

    # ── Season preview mode (no Yahoo fetch needed) ──────────────────────────
    if args.mode == "preview":
        season = args.season or datetime.now().year
        print(f"[ci_runner] Generating {season} season preview…")
        ok = run_preview(season, force=args.force)
        if not ok:
            print("[ci_runner] Season preview generation failed.", file=sys.stderr)
            sys.exit(1)
        print("[ci_runner] Done ✓")
        return

    league_key = os.environ.get("YAHOO_LEAGUE_KEY", "")
    if not league_key:
        print("Error: YAHOO_LEAGUE_KEY not set.", file=sys.stderr)
        sys.exit(1)

    # Set up Yahoo OAuth (CI mode — no browser)
    print("[ci_runner] Setting up Yahoo OAuth…")
    oauth = setup_ci_oauth()

    # Fetch league data
    print(f"[ci_runner] Fetching Yahoo data (week={args.week or 'latest'})…")
    week_data = fetch_weekly_data(oauth, league_key, week=args.week)
    season    = week_data.get("season", datetime.now().year)
    week_num  = week_data.get("week", 0)
    print(f"[ci_runner] Got data for {season} Week {week_num}")

    if args.dry_run:
        print("[ci_runner] --dry-run: no files will be written.")
        print(json.dumps(week_data, indent=2, default=str)[:2000])
        return

    # Always save data snapshot
    run_save_data(week_data, season, week_num)

    # Trade articles
    if args.mode in ("trades", "full"):
        n = run_trades(week_data, season)
        print(f"[ci_runner] Trade articles written: {n}")

    # Weekly recap
    if args.mode in ("recap", "full"):
        ok = run_recap(week_data, season)
        if not ok:
            print("[ci_runner] Recap article generation failed.", file=sys.stderr)
            sys.exit(1)

    print("[ci_runner] Done ✓")


if __name__ == "__main__":
    main()
