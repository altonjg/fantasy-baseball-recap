"""
MillerLite® BeerLeagueBaseball — Weekly Recap Dashboard

Run locally:  streamlit run app.py
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="BeerLeagueBaseball Recap",
    page_icon="⚾",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
.hero-banner {
    background: linear-gradient(135deg, #1f3a5f 0%, #1a9850 100%);
    padding: 24px 32px;
    border-radius: 12px;
    color: white;
    margin-bottom: 16px;
}
.hero-title { font-size: 2em; font-weight: 800; margin: 0; }
.hero-sub   { font-size: 1em; opacity: 0.85; margin: 4px 0 0 0; }
.section-header {
    font-size: 1.05em; font-weight: 700; color: #1f3a5f;
    border-bottom: 2px solid #1a9850;
    padding-bottom: 4px; margin-bottom: 10px;
}
.award-row {
    display: flex; align-items: center;
    padding: 5px 0; border-bottom: 1px solid #f0f0f0; font-size: 0.9em;
}
.award-icon  { width: 26px; }
.award-label { color: #666; width: 170px; font-size: 0.85em; }
.award-winner { font-weight: 600; flex: 1; }
.award-value { color: #888; font-size: 0.82em; margin-left: 6px; }
.badge {
    display: inline-block; padding: 3px 10px; border-radius: 12px;
    font-size: 0.82em; font-weight: 600; margin: 3px 3px 3px 0;
}
.badge-gold  { background: #fff3cd; color: #856404; }
.badge-green { background: #d4edda; color: #155724; }
.badge-red   { background: #f8d7da; color: #721c24; }
.badge-blue  { background: #d1ecf1; color: #0c5460; }
.score-row {
    display: flex; justify-content: space-between; align-items: center;
    padding: 5px 10px; border-radius: 6px; margin: 3px 0;
    background: #f8f9fa; font-size: 0.9em;
}
.score-winner { font-weight: 700; color: #1a9850; }
.trophy-section {
    background: linear-gradient(135deg, #fff9e6, #fffbf0);
    border: 1px solid #f0c040; border-radius: 10px; padding: 16px; margin: 8px 0;
}
.panel-box {
    background: white; border: 1px solid #e8e8e8;
    border-radius: 10px; padding: 14px; height: 100%;
}
</style>
""", unsafe_allow_html=True)

# ── Constants ─────────────────────────────────────────────────────────────────
DATA_ROOT = Path(__file__).parent / "data"
LOWER_IS_BETTER_DEFAULT = {"ERA", "WHIP"}

AWARD_DEFS = [
    ("🥇", "Champion",           "champion"),
    ("🥈", "Runner-Up",          "runner_up"),
    ("💀", "Wooden Spoon",       "wooden_spoon"),
    ("🔥", "Most Points For",    "most_pf"),
    ("🛡️", "Best Defense",       "best_defense"),
    ("📈", "Longest Win Streak", "longest_win_streak"),
    ("📉", "Longest Lose Streak","longest_lose_streak"),
    ("🍀", "Luckiest Team",      "luckiest"),
    ("😤", "Most Unlucky",       "most_unlucky"),
    ("👑", "Best Regular Season","best_reg_season"),
    ("🎢", "Biggest Collapse",   "biggest_collapse"),
    ("⚡", "Hottest Finish",     "hottest_finish"),
    ("🧊", "Coldest Finish",     "coldest_finish"),
]


# ══════════════════════════════════════════════════════════════════════════════
# DATA LOADING
# ══════════════════════════════════════════════════════════════════════════════

def get_available_seasons() -> list[int]:
    if not DATA_ROOT.exists():
        return []
    seasons = [
        int(d.name) for d in DATA_ROOT.iterdir()
        if d.is_dir() and d.name.isdigit() and list(d.glob("week_*.json"))
    ]
    return sorted(seasons, reverse=True)


@st.cache_data(ttl=60)
def load_all_weeks(season: int) -> dict[int, dict]:
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
    return {s: load_all_weeks(s) for s in get_available_seasons()}


# ══════════════════════════════════════════════════════════════════════════════
# STANDINGS RECONSTRUCTION
# ══════════════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=60)
def compute_standings(weeks_data_frozen: tuple, up_to_week: int) -> list[dict]:
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
        cur_len  = sum(1 for _ in (r for r in reversed(res) if r == cur_type)
                       for _ in [None] if True) # count from end
        # recalculate cleanly
        cur_len = 0
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
    all_weeks     = sorted(weeks_data.keys())
    last_week     = max(all_weeks)
    weeks_frozen  = tuple(sorted(weeks_data.items()))
    final_st      = compute_standings(weeks_frozen, last_week)
    if not final_st:
        return {}

    awards: dict[str, dict] = {}

    # Champion / Runner-Up / Wooden Spoon
    awards["champion"]     = {"name": final_st[0]["name"]}
    if len(final_st) > 1:
        awards["runner_up"] = {"name": final_st[1]["name"]}
    awards["wooden_spoon"] = {
        "name": final_st[-1]["name"],
        "value": f"{final_st[-1]['wins']}-{final_st[-1]['losses']}",
    }

    # Most PF / Best Defense
    most_pf  = max(final_st, key=lambda x: x["points_for"])
    best_def = min(final_st, key=lambda x: x["points_against"])
    awards["most_pf"]      = {"name": most_pf["name"],  "value": f"{most_pf['points_for']:.1f} PF"}
    awards["best_defense"] = {"name": best_def["name"], "value": f"{best_def['points_against']:.1f} PA"}

    # Streaks
    streaks = compute_streaks(weeks_frozen)
    if streaks:
        mw = max(streaks.values(), key=lambda x: x["max_win_streak"])
        ml = max(streaks.values(), key=lambda x: x["max_lose_streak"])
        awards["longest_win_streak"]  = {"name": mw["name"], "value": f"{mw['max_win_streak']} in a row"}
        awards["longest_lose_streak"] = {"name": ml["name"], "value": f"{ml['max_lose_streak']} in a row"}

    # Luck ratings
    expected = compute_luck_ratings(weeks_data)
    actual_wins = {s["name"]: s["wins"] for s in final_st}
    luck_delta  = {name: round(actual_wins.get(name, 0) - exp, 2) for name, exp in expected.items()}
    if luck_delta:
        luckiest   = max(luck_delta, key=luck_delta.get)
        unluckiest = min(luck_delta, key=luck_delta.get)
        awards["luckiest"]     = {"name": luckiest,   "value": f"+{luck_delta[luckiest]:.1f} luck"}
        awards["most_unlucky"] = {"name": unluckiest, "value": f"{luck_delta[unluckiest]:.1f} luck"}

    # Best Regular Season (record before playoffs)
    rs_end = last_week
    for wk in all_weeks:
        if any(m.get("is_playoffs") for m in weeks_data[wk].get("matchups", [])):
            rs_end = wk - 1
            break
    rs_st = compute_standings(weeks_frozen, rs_end)
    if rs_st:
        awards["best_reg_season"] = {
            "name": rs_st[0]["name"],
            "value": f"{rs_st[0]['wins']}-{rs_st[0]['losses']} reg season",
        }

    # Hottest / Coldest Finish (last 4 weeks)
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
        awards["hottest_finish"] = {"name": hottest, "value": f"{hot_records[hottest]['wins']}-{hot_records[hottest]['losses']} last 4 wks"}
        awards["coldest_finish"] = {"name": coldest, "value": f"{hot_records[coldest]['wins']}-{hot_records[coldest]['losses']} last 4 wks"}

    # Biggest Collapse (top-half midseason rank → most rank drop)
    mid_wk   = all_weeks[len(all_weeks) // 2]
    mid_st   = compute_standings(weeks_frozen, mid_wk)
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
                    "name": worst[0],
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

    # 🔥 Hot Hand — most category wins
    if all_teams:
        hot = max(all_teams, key=lambda t: t["points"])
        awards.append({"badge": "🔥 Hot Hand", "color": "badge-gold",
                       "winner": hot["name"], "detail": f"{hot['points']:.0f} cats won"})

    # 🍀 Lucky Win — winner scored below week average
    for m in matchups:
        if len(m["teams"]) < 2 or not m.get("winner_key") or m.get("is_tied"):
            continue
        winner = next((t for t in m["teams"] if t["team_key"] == m["winner_key"]), None)
        if winner and winner["points"] < week_avg:
            awards.append({"badge": "🍀 Lucky Win", "color": "badge-green",
                           "winner": winner["name"],
                           "detail": f"{winner['points']:.0f} cats (avg {week_avg:.0f})"})
            break

    # 💀 Trap Game — lost despite higher season-avg PF
    prior_avgs: dict[str, float] = {}
    prior_counts: dict[str, int] = {}
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

    # 📉 Choker — top-half standing team loses to bottom-half team
    weeks_frozen = tuple(sorted(weeks_data.items()))
    standings    = compute_standings(weeks_frozen, cur_week - 1) if cur_week > 1 else []
    if standings:
        rank_map  = {s["name"]: s["rank"] for s in standings}
        mid_rank  = len(standings) // 2
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
                                   "winner": loser["name"], "detail": "Top-half team upset by bottom-half"})
                    break
    return awards


# ══════════════════════════════════════════════════════════════════════════════
# ALL-TIME STATS
# ══════════════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=300)
def compute_alltime_stats(all_seasons_frozen: tuple) -> dict:
    all_seasons = dict(all_seasons_frozen)
    team_stats:   dict[str, dict] = {}
    season_awards_map: dict[int, dict] = {}

    for season, weeks_data in sorted(all_seasons.items()):
        if not weeks_data:
            continue
        last_wk  = max(weeks_data.keys())
        wf       = tuple(sorted(weeks_data.items()))
        final_st = compute_standings(wf, last_wk)

        # Season awards
        sa = compute_season_awards(weeks_data)
        season_awards_map[season] = sa

        # Accumulate per-team all-time stats
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
            ts["seasons"]       += 1
            ts["wins"]          += s["wins"]
            ts["losses"]        += s["losses"]
            ts["ties"]          += s.get("ties", 0)
            ts["points_for"]    += s["points_for"]
            ts["points_against"]+= s["points_against"]
            ts["best_finish"]    = min(ts["best_finish"], s["rank"])
            ts["season_finishes"][season] = s["rank"]
            if s["rank"] == 1:  ts["championships"] += 1
            if s["rank"] <= 2:  ts["finals"]        += 1
            if s["rank"] == len(final_st): ts["wooden_spoons"] += 1

    # Compute win %
    for ts in team_stats.values():
        total = ts["wins"] + ts["losses"]
        ts["win_pct"] = round(ts["wins"] / total, 3) if total else 0.0

    return {"teams": team_stats, "season_awards": season_awards_map}


# ══════════════════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
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


def build_category_df(t1: dict, t2: dict, lower_is_better: set[str]) -> pd.DataFrame:
    cats1, cats2 = t1.get("category_stats", {}), t2.get("category_stats", {})
    rows = []
    for cat in sorted(set(cats1) | set(cats2)):
        v1, v2 = cats1.get(cat, "–"), cats2.get(cat, "–")
        rows.append({"Category": cat, t1["name"]: v1, "Winner": category_winner(v1, v2, cat, lower_is_better), t2["name"]: v2})
    return pd.DataFrame(rows)


def week_label(w: int, data: dict) -> str:
    is_champ    = any(m.get("is_championship") for m in data.get("matchups", []))
    is_playoff  = any(m.get("is_playoffs") and not m.get("is_consolation") for m in data.get("matchups", []))
    suffix = " 🏆" if is_champ else (" 🥊" if is_playoff else "")
    return f"Week {w}{suffix}"


def render_award_card(awards: dict, season: int) -> None:
    """Render a season awards card."""
    champion = awards.get("champion", {}).get("name", "—")
    st.markdown(f"""
    <div class="trophy-section">
        <div style="font-size:1.2em; font-weight:800; color:#1f3a5f; margin-bottom:10px;">
            🏆 {season} Season Awards
        </div>
    """, unsafe_allow_html=True)
    for icon, label, key in AWARD_DEFS:
        a = awards.get(key)
        if not a:
            continue
        value_str = a.get("value", "")
        st.markdown(f"""
        <div class="award-row">
            <span class="award-icon">{icon}</span>
            <span class="award-label">{label}</span>
            <span class="award-winner">{a['name']}</span>
            <span class="award-value">{value_str}</span>
        </div>
        """, unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)


def render_weekly_award_badges(awards: list[dict]) -> None:
    if not awards:
        st.caption("No awards data for this week.")
        return
    html = ""
    for a in awards:
        html += f'<span class="badge {a["color"]}">{a["badge"]} {a["winner"]}</span> '
        html += f'<span style="font-size:0.8em;color:#888;">{a["detail"]}</span><br>'
    st.markdown(html, unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# LOAD DATA
# ══════════════════════════════════════════════════════════════════════════════

available_seasons = get_available_seasons()

if not available_seasons:
    st.title("⚾ BeerLeagueBaseball Recap")
    st.info("No weekly data found yet.\n\nRun `python3 backfill.py --year 2025` to pull data from Yahoo.")
    st.stop()


# ══════════════════════════════════════════════════════════════════════════════
# SIDEBAR
# ══════════════════════════════════════════════════════════════════════════════

with st.sidebar:
    st.title("⚾ Beer League Baseball")
    st.divider()

    selected_season = st.selectbox(
        "Season",
        options=available_seasons,
        format_func=lambda y: f"{y} Season",
    )
    st.divider()

    weeks_data = load_all_weeks(selected_season)

    if not weeks_data:
        st.warning(f"No data found for {selected_season}.")
        st.stop()

    available_weeks = sorted(weeks_data.keys(), reverse=True)
    league_name     = weeks_data[available_weeks[0]].get("league_name", "Fantasy Baseball League")
    st.caption(league_name)

    selected_week = st.selectbox(
        "Select Week",
        options=available_weeks,
        format_func=lambda w: week_label(w, weeks_data[w]),
    )
    st.divider()

    # Sidebar standings
    _wf_sidebar  = tuple(sorted(weeks_data.items()))
    all_standings = compute_standings(_wf_sidebar, available_weeks[0])

    if all_standings:
        st.subheader("Standings")
        team_search = st.text_input("🔍 Search team", placeholder="Team name...", label_visibility="collapsed")
        filtered_st = [s for s in all_standings if not team_search or team_search.lower() in s["name"].lower()]
        with st.expander("View All Teams", expanded=False):
            for s in filtered_st:
                record = f"{s['wins']}-{s['losses']}" + (f"-{s['ties']}" if s.get("ties") else "")
                st.caption(f"{s['rank']}. **{s['name']}** — {record}")

    st.divider()
    st.caption(f"📊 {len(available_weeks)} weeks · {len(available_seasons)} seasons")


# ══════════════════════════════════════════════════════════════════════════════
# SELECTED WEEK DATA
# ══════════════════════════════════════════════════════════════════════════════

data           = weeks_data[selected_week]
matchups       = data.get("matchups", [])
_weeks_frozen  = tuple(sorted(weeks_data.items()))
standings      = compute_standings(_weeks_frozen, selected_week)
transactions   = data.get("transactions", [])
lower_is_better: set[str] = set(data.get("lower_is_better_stats", [])) or LOWER_IS_BETTER_DEFAULT

playoff_games    = [m for m in matchups if m.get("is_playoffs") and not m.get("is_consolation")]
is_championship  = any(m.get("is_championship") for m in matchups)
is_playoff_week  = bool(playoff_games)
season_complete  = is_season_complete(weeks_data)

# Pre-compute awards
season_awards  = compute_season_awards(weeks_data) if season_complete else {}
weekly_awards  = compute_weekly_awards(data, weeks_data)
all_seasons    = load_all_seasons_data()
_alltime_frozen = tuple(sorted({s: tuple(sorted(wd.items())) for s, wd in all_seasons.items()}.items()))


# ══════════════════════════════════════════════════════════════════════════════
# PAGE HEADER
# ══════════════════════════════════════════════════════════════════════════════

if is_championship:
    page_label = f"Week {selected_week} — Championship 🏆"
elif is_playoff_week:
    page_label = f"Week {selected_week} — Playoffs 🥊"
else:
    page_label = f"Week {selected_week} Recap"

champion_str = ""
if season_complete and season_awards.get("champion"):
    champion_str = f" · 🏆 {season_awards['champion']['name']}"

st.markdown(f"""
<div class="hero-banner">
    <div class="hero-title">⚾ {league_name}</div>
    <div class="hero-sub">{selected_season} Season · {page_label}{champion_str}</div>
</div>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# TABS
# ══════════════════════════════════════════════════════════════════════════════

tab_home, tab_week, tab_season, tab_alltime, tab_news = st.tabs([
    "🏠 Home",
    "⚔️ This Week",
    "🏆 Season",
    "📖 All-Time",
    "📰 News",
])


# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — HOME
# ══════════════════════════════════════════════════════════════════════════════

with tab_home:

    # ── Three-panel summary row ───────────────────────────────────────────────
    col_stand, col_pr, col_news = st.columns(3)

    with col_stand:
        st.markdown('<div class="panel-box">', unsafe_allow_html=True)
        st.markdown('<div class="section-header">🏆 Standings</div>', unsafe_allow_html=True)
        for s in standings[:7]:
            record = f"{s['wins']}-{s['losses']}"
            medal  = "🥇" if s["rank"] == 1 else ("🥈" if s["rank"] == 2 else ("🥉" if s["rank"] == 3 else f"{s['rank']}.")  )
            st.markdown(f"**{medal}** {s['name']} <span style='color:#888;font-size:0.85em'>{record}</span>", unsafe_allow_html=True)
        if len(standings) > 7:
            st.caption(f"_+{len(standings)-7} more teams_")
        st.markdown('</div>', unsafe_allow_html=True)

    with col_pr:
        st.markdown('<div class="panel-box">', unsafe_allow_html=True)
        st.markdown('<div class="section-header">⚡ Power Rankings</div>', unsafe_allow_html=True)
        # Simple power ranking: wins * 3 + PF weighting (full algo in Phase 4)
        if standings:
            max_pf = max(s["points_for"] for s in standings) or 1
            pr_scores = sorted(standings, key=lambda s: s["wins"] * 3 + (s["points_for"] / max_pf) * 5, reverse=True)
            for i, s in enumerate(pr_scores[:7], 1):
                # Compare to standings rank for movement
                rank_diff = s["rank"] - i
                arrow = f"<span style='color:#1a9850'>↑{rank_diff}</span>" if rank_diff > 0 else (
                        f"<span style='color:#d73027'>↓{abs(rank_diff)}</span>" if rank_diff < 0 else
                        "<span style='color:#888'>—</span>")
                st.markdown(f"**{i}.** {s['name']} {arrow}", unsafe_allow_html=True)
        st.caption("_Full algorithm coming in Phase 4_")
        st.markdown('</div>', unsafe_allow_html=True)

    with col_news:
        st.markdown('<div class="panel-box">', unsafe_allow_html=True)
        st.markdown('<div class="section-header">📰 Latest</div>', unsafe_allow_html=True)
        # Show last 3 weeks with recaps
        news_count = 0
        for wk in available_weeks:
            recap = weeks_data[wk].get("recap_text", "")
            if recap and news_count < 3:
                label = week_label(wk, weeks_data[wk])
                first_line = recap.split("\n")[0][:60] + "..."
                st.markdown(f"**{label}** · _{first_line}_")
                news_count += 1
        if news_count == 0:
            st.caption("No recaps generated yet.")
        st.markdown('</div>', unsafe_allow_html=True)

    st.divider()

    # ── This week's scores ────────────────────────────────────────────────────
    st.markdown('<div class="section-header">⚔️ This Week\'s Scores</div>', unsafe_allow_html=True)
    score_cols = st.columns(2)
    for i, m in enumerate(matchups):
        if len(m["teams"]) < 2:
            continue
        t1, t2     = m["teams"][0], m["teams"][1]
        winner_key = m.get("winner_key")
        t1_bold = "score-winner" if winner_key == t1["team_key"] else ""
        t2_bold = "score-winner" if winner_key == t2["team_key"] else ""
        icon = "🏆" if m.get("is_championship") else ("🥉" if m.get("is_third_place") else ("🥊" if m.get("is_playoffs") else "⚾"))
        with score_cols[i % 2]:
            st.markdown(f"""
            <div class="score-row">
                <span class="{t1_bold}">{t1['name']}</span>
                <span style="color:#888;font-size:0.85em">{icon} {t1['points']:.0f} – {t2['points']:.0f}</span>
                <span class="{t2_bold}">{t2['name']}</span>
            </div>
            """, unsafe_allow_html=True)

    st.divider()

    # ── Weekly Awards ─────────────────────────────────────────────────────────
    st.markdown('<div class="section-header">🏅 Weekly Awards</div>', unsafe_allow_html=True)
    render_weekly_award_badges(weekly_awards)

    # ── Season Awards (completed seasons only) ────────────────────────────────
    if season_complete and season_awards:
        st.divider()
        render_award_card(season_awards, selected_season)
    elif not season_complete and standings:
        st.divider()
        st.markdown('<div class="section-header">📊 Season Leaders (Live)</div>', unsafe_allow_html=True)
        lc1, lc2, lc3 = st.columns(3)
        lc1.metric("🏆 1st Place",   standings[0]["name"], f"{standings[0]['wins']}W-{standings[0]['losses']}L")
        most_pf_live = max(standings, key=lambda s: s["points_for"])
        lc2.metric("🔥 Most PF",    most_pf_live["name"],  f"{most_pf_live['points_for']:.1f}")
        best_def_live = min(standings, key=lambda s: s["points_against"])
        lc3.metric("🛡️ Best Defense", best_def_live["name"], f"{best_def_live['points_against']:.1f} PA")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — THIS WEEK
# ══════════════════════════════════════════════════════════════════════════════

with tab_week:
    inner_recap, inner_matchups, inner_tx = st.tabs(["📝 Recap", "⚔️ Matchups", "🔄 Transactions"])

    # ── Recap ─────────────────────────────────────────────────────────────────
    with inner_recap:
        recap_text = data.get("recap_text", "")
        if recap_text:
            col_main, col_side = st.columns([3, 1])
            with col_main:
                st.markdown(recap_text)
            with col_side:
                st.subheader("Quick Stats")
                all_teams_pts = sorted([t for m in matchups for t in m["teams"]], key=lambda t: t["points"], reverse=True)
                if all_teams_pts:
                    st.metric("🔥 High Score", all_teams_pts[0]["name"],  f"{all_teams_pts[0]['points']:.0f} cats")
                    st.metric("❄️ Low Score",  all_teams_pts[-1]["name"], f"{all_teams_pts[-1]['points']:.0f} cats", delta_color="off")
                    st.divider()
                    st.caption("**All Teams This Week** _(category wins)_")
                    for t in all_teams_pts:
                        st.caption(f"{t['name']} — **{t['points']:.0f}** cats won")
                st.divider()
                st.markdown("**🏅 Weekly Awards**")
                render_weekly_award_badges(weekly_awards)
        else:
            st.info("No recap generated for this week yet. Run `python3 main.py --dry-run` to generate one.")

    # ── Matchups ──────────────────────────────────────────────────────────────
    with inner_matchups:
        if not matchups:
            st.info("No matchup data available.")
        else:
            # Matchup type filter
            matchup_types = ["All"]
            if any(m.get("is_championship") for m in matchups):              matchup_types.append("Championship")
            if any(m.get("is_third_place")  for m in matchups):              matchup_types.append("3rd Place")
            if any(m.get("is_playoffs") and not m.get("is_consolation") and not m.get("is_championship") and not m.get("is_third_place") for m in matchups): matchup_types.append("Playoffs")
            if any(m.get("is_consolation")  for m in matchups):              matchup_types.append("Consolation")
            if any(not m.get("is_playoffs") and not m.get("is_consolation") for m in matchups): matchup_types.append("Regular Season")

            selected_type = st.radio("Filter matchups", matchup_types, horizontal=True) if len(matchup_types) > 2 else "All"

            def matchup_type_filter(m: dict) -> bool:
                if selected_type == "All":            return True
                if selected_type == "Championship":  return bool(m.get("is_championship"))
                if selected_type == "3rd Place":     return bool(m.get("is_third_place"))
                if selected_type == "Playoffs":      return m.get("is_playoffs") and not m.get("is_consolation") and not m.get("is_championship") and not m.get("is_third_place")
                if selected_type == "Consolation":   return bool(m.get("is_consolation"))
                if selected_type == "Regular Season":return not m.get("is_playoffs") and not m.get("is_consolation")
                return True

            filtered_matchups = [m for m in matchups if matchup_type_filter(m)]

            # Bar chart
            all_teams = [t for m in filtered_matchups for t in m["teams"]]
            df_pts    = pd.DataFrame(all_teams).sort_values("points", ascending=True)
            colors    = ["#f0c040" if r == max(df_pts["points"]) else "#4a90d9" for r in df_pts["points"]]
            fig_pts   = go.Figure(go.Bar(
                x=df_pts["points"], y=df_pts["name"], orientation="h",
                marker_color=colors, text=df_pts["points"].apply(lambda x: f"{x:.0f}"), textposition="outside",
            ))
            fig_pts.update_layout(title=f"Week {selected_week} — Category Wins by Team",
                                  xaxis_title="Category Wins", yaxis_title="",
                                  height=max(300, len(all_teams) * 40), margin=dict(l=10, r=60, t=40, b=30))
            st.plotly_chart(fig_pts, use_container_width=True)

            # Heatmap
            st.subheader("Category Win Heatmap")
            heatmap_rows = []
            for m in filtered_matchups:
                if len(m["teams"]) < 2: continue
                t1, t2 = m["teams"][0], m["teams"][1]
                label  = f"{t1['name']} vs {t2['name']}"
                for cat in sorted(set(t1.get("category_stats", {})) | set(t2.get("category_stats", {}))):
                    v1, v2 = t1.get("category_stats", {}).get(cat), t2.get("category_stats", {}).get(cat)
                    winner = category_winner(v1, v2, cat, lower_is_better)
                    heatmap_rows.append({"Matchup": label, "Category": cat, "Score": 1 if winner == "←" else (-1 if winner == "→" else 0)})
            if heatmap_rows:
                df_heat = pd.DataFrame(heatmap_rows).pivot(index="Matchup", columns="Category", values="Score")
                fig_heat = px.imshow(df_heat, color_continuous_scale=["#d73027", "#f7f7f7", "#1a9850"],
                                     color_continuous_midpoint=0, title="Category Heatmap (green = left team wins)", aspect="auto")
                fig_heat.update_layout(height=max(200, len(df_heat) * 60))
                st.plotly_chart(fig_heat, use_container_width=True)

            st.divider()
            st.subheader("Matchup Details")

            for m in filtered_matchups:
                if len(m["teams"]) < 2: continue
                t1, t2   = m["teams"][0], m["teams"][1]
                winner   = get_winner(m)
                icon     = "🏆" if m.get("is_championship") else ("🥉" if m.get("is_third_place") else ("😅" if m.get("is_consolation") else ("🥊" if m.get("is_playoffs") else "⚾")))
                score_str = f"{t1['points']:.0f} – {t2['points']:.0f}"
                expanded  = m.get("is_playoffs", False)

                with st.expander(f"{icon}  {t1['name']}  {score_str}  {t2['name']}", expanded=expanded):
                    ca, cv, cb = st.columns([5, 1, 5])
                    with ca:
                        medal = "🏅 " if (winner and winner["team_key"] == t1["team_key"]) else ""
                        st.markdown(f"### {medal}{t1['name']}")
                        st.caption(f"Manager: {t1['manager']}")
                        st.metric("Category Wins", int(t1["points"]))
                    with cv:
                        st.markdown("<p style='text-align:center;font-size:1.5em;padding-top:25px'>VS</p>", unsafe_allow_html=True)
                    with cb:
                        medal = "🏅 " if (winner and winner["team_key"] == t2["team_key"]) else ""
                        st.markdown(f"### {medal}{t2['name']}")
                        st.caption(f"Manager: {t2['manager']}")
                        st.metric("Category Wins", int(t2["points"]))

                    df_cats = build_category_df(t1, t2, lower_is_better)
                    if not df_cats.empty:
                        def highlight_winner(row):
                            if row["Winner"] == "←": return ["", "background-color: #1a9850; color: white", "", ""]
                            if row["Winner"] == "→": return ["", "", "", "background-color: #1a9850; color: white"]
                            return [""] * 4
                        st.dataframe(df_cats.style.apply(highlight_winner, axis=1), use_container_width=True, hide_index=True)
                        wins_t1 = (df_cats["Winner"] == "←").sum()
                        wins_t2 = (df_cats["Winner"] == "→").sum()
                        ties    = (df_cats["Winner"] == "tie").sum()
                        c1, c2, c3 = st.columns(3)
                        c1.metric(t1["name"], f"{wins_t1} cats won")
                        c2.metric("Tied",     f"{ties} cats")
                        c3.metric(t2["name"], f"{wins_t2} cats won")

    # ── Transactions ──────────────────────────────────────────────────────────
    with inner_tx:
        if not transactions:
            st.info("No transactions recorded for this week.")
        else:
            tx_teams   = sorted({p.get("team", "") for tx in transactions for p in tx.get("players", []) if p.get("team")})
            tx_actions = sorted({p.get("action", "").lower() for tx in transactions for p in tx.get("players", []) if p.get("action")})
            tf1, tf2   = st.columns([2, 1])
            with tf1:
                sel_tx_teams  = st.multiselect("Filter by team",   options=tx_teams,   default=tx_teams,   key="tx_teams")
            with tf2:
                sel_tx_action = st.selectbox("Filter by action", options=["All"] + [a.title() for a in tx_actions], key="tx_action")

            filtered_tx = [
                tx for tx in transactions
                if any(p.get("team") in sel_tx_teams and (sel_tx_action == "All" or p.get("action", "").lower() == sel_tx_action.lower())
                       for p in tx.get("players", []))
            ]

            team_counts: dict[str, dict] = {}
            for tx in filtered_tx:
                for p in tx.get("players", []):
                    team = p.get("team", "Free Agent")
                    team_counts.setdefault(team, {"add": 0, "drop": 0})
                    team_counts[team][p.get("action", "unknown").lower()] = team_counts[team].get(p.get("action", "unknown").lower(), 0) + 1

            if team_counts:
                df_tx = pd.DataFrame([{"Team": t, "Adds": c.get("add", 0), "Drops": c.get("drop", 0)}
                                       for t, c in sorted(team_counts.items(), key=lambda x: sum(x[1].values()), reverse=True)])
                fig_tx = px.bar(df_tx, x="Team", y=["Adds", "Drops"], barmode="group",
                                title="Transaction Activity", color_discrete_map={"Adds": "#1a9850", "Drops": "#d73027"})
                fig_tx.update_layout(height=350, xaxis_tickangle=-30)
                st.plotly_chart(fig_tx, use_container_width=True)

            st.subheader("All Transactions")
            icons = {"add": "➕", "drop": "➖", "trade": "🔄"}
            for tx in filtered_tx:
                for p in tx.get("players", []):
                    action = p.get("action", "").lower()
                    st.markdown(f"{icons.get(action, '📋')} **{action.upper()}** &nbsp; {p.get('name', '')} "
                                f"{'(' + p.get('position','') + ')' if p.get('position') else ''} &nbsp;→&nbsp; _{p.get('team', '')}_")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — SEASON
# ══════════════════════════════════════════════════════════════════════════════

with tab_season:
    inner_stand, inner_trends, inner_streaks = st.tabs(["🏆 Standings", "📈 Trends", "🔥 Streaks"])

    # ── Standings ─────────────────────────────────────────────────────────────
    with inner_stand:
        if not standings:
            st.info("No standings data available.")
        else:
            df_stand = pd.DataFrame(standings)
            c1, c2, c3 = st.columns(3)
            leader     = df_stand.iloc[0]
            most_pf    = df_stand.loc[df_stand["points_for"].idxmax()]
            least_pa   = df_stand.loc[df_stand["points_against"].idxmin()]
            c1.metric("🥇 First Place",    leader["name"],   f"{leader['wins']}W – {leader['losses']}L")
            c2.metric("🔥 Most Points For", most_pf["name"],  f"{most_pf['points_for']:.1f} PF")
            c3.metric("🛡️ Best Defense",   least_pa["name"], f"{least_pa['points_against']:.1f} PA")
            st.divider()

            col_l, col_r = st.columns(2)
            with col_l:
                df_sorted = df_stand.sort_values("wins", ascending=True)
                fig_wins = px.bar(df_sorted, x="wins", y="name", orientation="h", color="wins",
                                  color_continuous_scale="Greens", title="Season Wins", labels={"wins": "Wins", "name": ""}, text="wins")
                fig_wins.update_traces(textposition="outside")
                fig_wins.update_layout(showlegend=False, coloraxis_showscale=False,
                                       height=max(300, len(df_stand) * 35), margin=dict(l=10, r=40, t=40, b=20))
                st.plotly_chart(fig_wins, use_container_width=True)

            with col_r:
                fig_scatter = px.scatter(df_stand, x="points_against", y="points_for", text="name",
                                         color="wins", color_continuous_scale="RdYlGn", size=[15] * len(df_stand),
                                         title="Points For vs Points Against",
                                         labels={"points_for": "PF", "points_against": "PA", "wins": "Wins"})
                fig_scatter.update_traces(textposition="top center", textfont_size=10)
                fig_scatter.update_layout(height=420)
                st.plotly_chart(fig_scatter, use_container_width=True)

            st.subheader("Full Standings Table")
            df_display = df_stand[["rank", "name", "wins", "losses", "ties", "points_for", "points_against"]].copy()
            df_display.columns = ["Rank", "Team", "W", "L", "T", "PF", "PA"]
            total_games         = df_display["W"] + df_display["L"]
            df_display["Win%"]  = (df_display["W"] / total_games.replace(0, 1)).round(3)
            df_display["GB"]    = (df_display.iloc[0]["W"] - df_display["W"]) / 2
            st.dataframe(df_display.style.bar(subset=["Win%"], color=["#d73027", "#1a9850"], vmin=0, vmax=1),
                         use_container_width=True, hide_index=True)

            # Season awards mid-season leaders
            if not season_complete:
                st.divider()
                st.subheader("📊 Award Leaders (Live)")
                exp_wins  = compute_luck_ratings(weeks_data)
                act_wins  = {s["name"]: s["wins"] for s in standings}
                luck_now  = {n: round(act_wins.get(n, 0) - e, 2) for n, e in exp_wins.items()}
                if luck_now:
                    luckiest_now   = max(luck_now, key=luck_now.get)
                    unluckiest_now = min(luck_now, key=luck_now.get)
                    lc1, lc2 = st.columns(2)
                    lc1.metric("🍀 Luckiest So Far",    luckiest_now,   f"+{luck_now[luckiest_now]:.1f} luck rating")
                    lc2.metric("😤 Most Unlucky So Far", unluckiest_now, f"{luck_now[unluckiest_now]:.1f} luck rating")

    # ── Trends ────────────────────────────────────────────────────────────────
    with inner_trends:
        if len(weeks_data) < 2:
            st.info("Season trend charts appear once you have 2+ weeks of data.")
        else:
            all_team_names = sorted({t["name"] for wd in weeks_data.values() for m in wd.get("matchups", []) for t in m.get("teams", [])})
            all_week_nums  = sorted(weeks_data.keys())
            fc1, fc2 = st.columns([2, 1])
            with fc1:
                selected_teams = st.multiselect("Filter teams", options=all_team_names, default=all_team_names, key="trends_teams")
            with fc2:
                week_range = st.slider("Week range", min_value=min(all_week_nums), max_value=max(all_week_nums),
                                       value=(min(all_week_nums), max(all_week_nums)), key="trends_weeks")

            records_list: list[dict] = []
            for wk in sorted(weeks_data.keys()):
                if not (week_range[0] <= wk <= week_range[1]):
                    continue
                for s in compute_standings(_weeks_frozen, wk):
                    if s["name"] in selected_teams:
                        records_list.append({"Week": wk, "Team": s["name"], "Wins": s["wins"],
                                             "Losses": s["losses"], "PF": s["points_for"], "Rank": s["rank"]})
            df_history = pd.DataFrame(records_list) if records_list else pd.DataFrame()

            if df_history.empty:
                st.info("No data matches current filters.")
            else:
                fig_rank = px.line(df_history, x="Week", y="Rank", color="Team",
                                   title="Standings Rank Over Time (lower = better)", markers=True)
                fig_rank.update_yaxes(autorange="reversed")
                fig_rank.update_layout(height=450)
                st.plotly_chart(fig_rank, use_container_width=True)

                fig_wins_t = px.line(df_history, x="Week", y="Wins", color="Team",
                                     title="Cumulative Wins Over Time", markers=True)
                fig_wins_t.update_layout(height=400)
                st.plotly_chart(fig_wins_t, use_container_width=True)

                fig_pf = px.line(df_history, x="Week", y="PF", color="Team",
                                 title="Cumulative Points For Over Time", markers=True)
                fig_pf.update_layout(height=400)
                st.plotly_chart(fig_pf, use_container_width=True)

                weekly_pts = [{"Week": wk, "Team": t["name"], "Categories Won": t["points"]}
                              for wk, wd in sorted(weeks_data.items())
                              if week_range[0] <= wk <= week_range[1]
                              for m in wd.get("matchups", [])
                              for t in m.get("teams", []) if t["name"] in selected_teams]
                if weekly_pts:
                    fig_weekly = px.line(pd.DataFrame(weekly_pts), x="Week", y="Categories Won",
                                        color="Team", markers=True, title="Categories Won Per Team Per Week")
                    fig_weekly.update_layout(height=450)
                    st.plotly_chart(fig_weekly, use_container_width=True)

    # ── Streaks ───────────────────────────────────────────────────────────────
    with inner_streaks:
        streaks = compute_streaks(_weeks_frozen)
        if not streaks:
            st.info("No streak data available.")
        else:
            streak_rows = []
            for s in standings:
                sk = next((v for v in streaks.values() if v["name"] == s["name"]), None)
                if sk:
                    cur_str = f"{sk['current_streak']}{'W' if sk['current_type']=='W' else ('L' if sk['current_type']=='L' else 'T')}"
                    streak_rows.append({"Team": sk["name"], "Current Streak": cur_str,
                                        "Best Win Streak": sk["max_win_streak"], "Worst Lose Streak": sk["max_lose_streak"]})
            if streak_rows:
                df_streaks = pd.DataFrame(streak_rows)
                st.dataframe(df_streaks, use_container_width=True, hide_index=True)

                col_ws, col_ls = st.columns(2)
                with col_ws:
                    df_ws = df_streaks.sort_values("Best Win Streak", ascending=True)
                    fig_ws = px.bar(df_ws, x="Best Win Streak", y="Team", orientation="h",
                                    color="Best Win Streak", color_continuous_scale="Greens",
                                    title="Season-Best Win Streak per Team")
                    fig_ws.update_layout(coloraxis_showscale=False, height=max(300, len(df_ws)*35))
                    st.plotly_chart(fig_ws, use_container_width=True)
                with col_ls:
                    df_ls = df_streaks.sort_values("Worst Lose Streak", ascending=True)
                    fig_ls = px.bar(df_ls, x="Worst Lose Streak", y="Team", orientation="h",
                                    color="Worst Lose Streak", color_continuous_scale="Reds",
                                    title="Season-Worst Lose Streak per Team")
                    fig_ls.update_layout(coloraxis_showscale=False, height=max(300, len(df_ls)*35))
                    st.plotly_chart(fig_ls, use_container_width=True)


# ══════════════════════════════════════════════════════════════════════════════
# TAB 4 — ALL-TIME
# ══════════════════════════════════════════════════════════════════════════════

with tab_alltime:
    alltime = compute_alltime_stats(tuple(sorted(
        {s: tuple(sorted(wd.items())) for s, wd in all_seasons.items()}.items()
    )))
    team_stats_all    = alltime.get("teams", {})
    season_awards_all = alltime.get("season_awards", {})

    inner_history, inner_h2h, inner_trophy, inner_awards_arch = st.tabs([
        "📅 History", "⚔️ Head-to-Head", "🏆 Trophy Case", "🎖️ Awards Archive"
    ])

    # ── History Table ─────────────────────────────────────────────────────────
    with inner_history:
        if not team_stats_all:
            st.info("Not enough data for all-time stats yet.")
        else:
            all_seasons_list = sorted(all_seasons.keys())
            history_rows = []
            for name, ts in team_stats_all.items():
                row = {"Team": name, "Seasons": ts["seasons"],
                       "All-Time W": ts["wins"], "All-Time L": ts["losses"],
                       "Win%": ts["win_pct"], "🏆": ts["championships"],
                       "Finals": ts["finals"], "💀": ts["wooden_spoons"],
                       "Total PF": round(ts["points_for"], 1)}
                for yr in all_seasons_list:
                    finish = ts["season_finishes"].get(yr)
                    row[str(yr)] = f"#{finish}" if finish else "—"
                history_rows.append(row)

            df_hist = pd.DataFrame(history_rows).sort_values("Win%", ascending=False)
            st.dataframe(df_hist, use_container_width=True, hide_index=True)

    # ── Head-to-Head ──────────────────────────────────────────────────────────
    with inner_h2h:
        all_team_names_ever = sorted(team_stats_all.keys())
        if len(all_team_names_ever) < 2:
            st.info("Need at least 2 teams for head-to-head.")
        else:
            hc1, hc2 = st.columns(2)
            with hc1:
                h2h_team_a = st.selectbox("Team A", options=all_team_names_ever, key="h2h_a")
            with hc2:
                opts_b = [t for t in all_team_names_ever if t != h2h_team_a]
                h2h_team_b = st.selectbox("Team B", options=opts_b, key="h2h_b")

            if h2h_team_a and h2h_team_b:
                h2h_records: dict[str, int] = {h2h_team_a: 0, h2h_team_b: 0, "ties": 0}
                h2h_matchups = []
                for season_yr, wd in sorted(all_seasons.items()):
                    for wk in sorted(wd.keys()):
                        for m in wd[wk].get("matchups", []):
                            if len(m["teams"]) < 2:
                                continue
                            names = {t["name"] for t in m["teams"]}
                            if h2h_team_a in names and h2h_team_b in names:
                                t_a = next(t for t in m["teams"] if t["name"] == h2h_team_a)
                                t_b = next(t for t in m["teams"] if t["name"] == h2h_team_b)
                                if m.get("is_tied"):
                                    h2h_records["ties"] += 1
                                    result_str = "Tie"
                                elif m.get("winner_key") == t_a["team_key"]:
                                    h2h_records[h2h_team_a] += 1
                                    result_str = f"✅ {h2h_team_a}"
                                else:
                                    h2h_records[h2h_team_b] += 1
                                    result_str = f"✅ {h2h_team_b}"
                                h2h_matchups.append({"Season": season_yr, "Week": wk,
                                                     f"{h2h_team_a} Pts": t_a["points"],
                                                     f"{h2h_team_b} Pts": t_b["points"],
                                                     "Winner": result_str})

                wa, wb = h2h_records[h2h_team_a], h2h_records[h2h_team_b]
                series_leader = h2h_team_a if wa > wb else (h2h_team_b if wb > wa else "Tied")
                ha, hb = st.columns(2)
                ha.metric(h2h_team_a, f"{wa}W", f"{'Series Leader 👑' if series_leader == h2h_team_a else ''}")
                hb.metric(h2h_team_b, f"{wb}W", f"{'Series Leader 👑' if series_leader == h2h_team_b else ''}")
                if h2h_records["ties"]:
                    st.caption(f"Ties: {h2h_records['ties']}")

                if h2h_matchups:
                    st.divider()
                    st.subheader("All Matchups")
                    st.dataframe(pd.DataFrame(h2h_matchups), use_container_width=True, hide_index=True)

    # ── Trophy Case ───────────────────────────────────────────────────────────
    with inner_trophy:
        if not team_stats_all:
            st.info("Not enough data yet.")
        else:
            st.subheader("🏆 Championships")
            champs = sorted([(ts["name"], ts["championships"], ts["season_finishes"])
                             for ts in team_stats_all.values() if ts["championships"] > 0],
                            key=lambda x: x[1], reverse=True)
            for name, count, finishes in champs:
                champ_years = [str(yr) for yr, r in sorted(finishes.items()) if r == 1]
                st.markdown(f"{'🥇' * count} **{name}** — {', '.join(champ_years)}")

            st.divider()
            st.subheader("📊 All-Time Win Leaders")
            df_wins = pd.DataFrame([
                {"Team": ts["name"], "Wins": ts["wins"], "Losses": ts["losses"],
                 "Win%": ts["win_pct"], "🏆": ts["championships"]}
                for ts in team_stats_all.values()
            ]).sort_values("Win%", ascending=False)
            st.dataframe(df_wins, use_container_width=True, hide_index=True)

            st.divider()
            st.subheader("📈 Single Season Records")
            records_data = []
            for season_yr, wd in all_seasons.items():
                if not wd:
                    continue
                last = max(wd.keys())
                wf   = tuple(sorted(wd.items()))
                st_list = compute_standings(wf, last)
                if st_list:
                    best = st_list[0]
                    worst = st_list[-1]
                    records_data.append({
                        "Season": season_yr,
                        "Best Record Team": best["name"],
                        "Best W-L": f"{best['wins']}-{best['losses']}",
                        "Worst Record Team": worst["name"],
                        "Worst W-L": f"{worst['wins']}-{worst['losses']}",
                        "Most PF Team": max(st_list, key=lambda s: s["points_for"])["name"],
                        "Most PF": round(max(st_list, key=lambda s: s["points_for"])["points_for"], 1),
                    })
            if records_data:
                st.dataframe(pd.DataFrame(records_data), use_container_width=True, hide_index=True)

    # ── Awards Archive ────────────────────────────────────────────────────────
    with inner_awards_arch:
        completed = [(yr, sa) for yr, sa in sorted(season_awards_all.items(), reverse=True) if sa]
        if not completed:
            st.info("No completed seasons with award data yet.")
        else:
            for yr, sa in completed:
                render_award_card(sa, yr)
                st.write("")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 5 — NEWS
# ══════════════════════════════════════════════════════════════════════════════

with tab_news:
    inner_tradewire, inner_archive = st.tabs(["📰 Trade Wire", "📚 Recap Archive"])

    # ── Trade Wire ────────────────────────────────────────────────────────────
    with inner_tradewire:
        trades_dir = DATA_ROOT / str(selected_season) / "trades"
        trade_files = sorted(trades_dir.glob("*.json"), reverse=True) if trades_dir.exists() else []
        trade_articles = []
        for f in trade_files:
            try:
                with open(f) as fp:
                    trade_articles.append(json.load(fp))
            except Exception:
                pass

        if not trade_articles:
            st.markdown("""
            <div style="text-align:center; padding: 40px; color: #888;">
                <div style="font-size: 3em;">📰</div>
                <div style="font-size: 1.2em; font-weight: 600; margin: 10px 0;">Trade Wire Coming in Phase 6</div>
                <div style="font-size: 0.9em;">When a trade is processed in Yahoo, BeerLeague Insider will automatically publish<br>
                a breaking news article written in the style of ESPN's Jeff Passan.</div>
            </div>
            """, unsafe_allow_html=True)

            # Show trades from transactions as a preview
            all_trades = [tx for wk_data in weeks_data.values()
                          for tx in wk_data.get("transactions", []) if tx.get("type") == "trade"]
            if all_trades:
                st.divider()
                st.subheader(f"📋 {len(all_trades)} Trade(s) This Season — Articles Coming Soon")
                for tx in all_trades[:5]:
                    players = tx.get("players", [])
                    if players:
                        names = ", ".join(p.get("name", "") for p in players[:3])
                        st.caption(f"🔄 Trade involving: {names}{'...' if len(players) > 3 else ''}")
        else:
            for article in trade_articles:
                with st.expander(article.get("headline", "Trade"), expanded=True):
                    st.markdown(article.get("body", ""))
                    c1, c2 = st.columns(2)
                    c1.metric("Grade", article.get("grade_team_a", "—"))
                    c2.metric("Grade", article.get("grade_team_b", "—"))

    # ── Recap Archive ─────────────────────────────────────────────────────────
    with inner_archive:
        recaps = [(wk, weeks_data[wk]) for wk in sorted(weeks_data.keys(), reverse=True)
                  if weeks_data[wk].get("recap_text")]
        if not recaps:
            st.info("No recaps generated yet for this season.")
        else:
            st.caption(f"{len(recaps)} recap(s) available for {selected_season}")
            for wk, wd in recaps:
                label = week_label(wk, wd)
                with st.expander(f"📝 {label}", expanded=(wk == recaps[0][0])):
                    st.markdown(wd["recap_text"])
                    if wd.get("generated_at"):
                        st.caption(f"Generated {wd['generated_at'][:10]}")
                    # Weekly awards for archived weeks
                    week_badges = compute_weekly_awards(wd, weeks_data)
                    if week_badges:
                        st.divider()
                        render_weekly_award_badges(week_badges)
