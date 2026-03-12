"""
MillerLite® BeerLeagueBaseball — Weekly Recap Dashboard

Run locally:  streamlit run app.py
"""

from __future__ import annotations

import json
from datetime import datetime
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
/* ── Hero banner ── */
.hero-banner {
    background: linear-gradient(135deg, #0d2d6e 0%, #0a1628 100%);
    border-left: 5px solid #f0c040;
    padding: 24px 32px; border-radius: 12px; color: #e8edf5; margin-bottom: 16px;
}
.hero-title { font-size: 2em; font-weight: 800; margin: 0; letter-spacing: -0.01em; }
.hero-sub   { font-size: 1em; opacity: 0.75; margin: 4px 0 0 0; }
/* ── Section headers — uppercase gold editorial ── */
.section-header {
    font-size: 0.72em; font-weight: 800; color: #f0c040;
    text-transform: uppercase; letter-spacing: 0.12em;
    border-bottom: 1px solid #1a2d4a;
    padding-bottom: 5px; margin-bottom: 10px;
}
/* ── Award rows ── */
.award-row {
    display: flex; align-items: center;
    padding: 5px 0; border-bottom: 1px solid #1a2d4a; font-size: 0.9em;
}
.award-icon  { width: 26px; }
.award-label { color: #8a9bb5; width: 170px; font-size: 0.85em; }
.award-winner { font-weight: 600; flex: 1; color: #e8edf5; }
.award-value { color: #8a9bb5; font-size: 0.82em; margin-left: 6px; }
/* ── Badges ── */
.badge {
    display: inline-block; padding: 3px 10px; border-radius: 12px;
    font-size: 0.82em; font-weight: 600; margin: 3px 3px 3px 0;
}
.badge-gold  { background: rgba(240,192,64,0.15); color: #f0c040; border: 1px solid rgba(240,192,64,0.3); }
.badge-green { background: rgba(34,197,94,0.12); color: #22c55e; border: 1px solid rgba(34,197,94,0.25); }
.badge-red   { background: rgba(239,68,68,0.12); color: #ef4444; border: 1px solid rgba(239,68,68,0.25); }
.badge-blue  { background: rgba(96,165,250,0.12); color: #60a5fa; border: 1px solid rgba(96,165,250,0.25); }
/* ── Score rows ── */
.score-row {
    display: flex; justify-content: space-between; align-items: center;
    padding: 5px 10px; border-radius: 6px; margin: 3px 0;
    background: #111e35; font-size: 0.9em; border: 1px solid #1a2d4a;
}
.score-winner { font-weight: 700; color: #22c55e; }
.score-row:hover { background: #162840; transition: background 0.15s; }
/* ── Trophy / season awards section ── */
.trophy-section {
    background: linear-gradient(135deg, #0e1e38, #111e35);
    border: 1px solid rgba(240,192,64,0.35); border-radius: 10px;
    padding: 16px; margin: 8px 0;
}
/* ── Panel boxes ── */
.panel-box {
    background: #111e35; border: 1px solid #1a2d4a;
    border-radius: 10px; padding: 14px; height: 100%;
    transition: box-shadow 0.2s;
}
.panel-box:hover { box-shadow: 0 4px 18px rgba(0,0,0,0.4); }
/* ── Stat chip ── */
.stat-chip {
    display: inline-block; background: #0d1f38; border-radius: 6px;
    padding: 3px 9px; font-size: 0.8em; color: #8a9bb5; margin: 2px 2px 2px 0;
    font-weight: 500; border: 1px solid #1a2d4a;
}
/* ── Pre-season banner ── */
.preseason-banner {
    background: linear-gradient(135deg, #0d2d6e 0%, #0a1628 100%);
    color: #e8edf5; border-radius: 14px; padding: 32px 36px; text-align: center;
    margin-bottom: 20px; border: 1px solid #1a2d4a;
}
.preseason-title { font-size: 1.8em; font-weight: 800; margin-bottom: 6px; }
.preseason-sub   { font-size: 1em; opacity: 0.65; }
/* ── Draft order rows ── */
.draft-pick-row {
    display: flex; align-items: center; padding: 6px 10px;
    border-radius: 7px; margin: 3px 0; background: #111e35;
    font-size: 0.92em; border: 1px solid #1a2d4a;
}
.draft-pick-num  { font-weight: 800; color: #f0c040; width: 36px; }
.draft-pick-name { flex: 1; font-weight: 600; color: #e8edf5; }
.draft-pick-note { font-size: 0.8em; color: #8a9bb5; }
/* ── Footer ── */
.footer-bar {
    text-align: center; color: #8a9bb5; font-size: 0.78em;
    padding: 18px 0 6px 0; border-top: 1px solid #1a2d4a; margin-top: 24px;
}
/* ── Season preview masthead ── */
.preview-masthead {
    background: linear-gradient(135deg, #0a1628 0%, #0d2d6e 100%);
    color: #e8edf5; border-radius: 14px; padding: 22px 28px; margin-bottom: 0px;
    border-left: 5px solid #f0c040;
}
.preview-label  { font-size: 0.72em; font-weight: 800; letter-spacing: 3px;
                  color: #f0c040; text-transform: uppercase; margin-bottom: 4px; }
.preview-title  { font-size: 1.45em; font-weight: 800; line-height: 1.25; margin-bottom: 6px; }
.preview-deck   { font-size: 0.9em; opacity: 0.78; margin-bottom: 10px; }
.preview-byline { font-size: 0.78em; opacity: 0.55; }
/* Hide default Streamlit footer */
footer { visibility: hidden; }
/* ── League leaders bar ── */
.leaders-bar { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 14px; }
.leader-cell {
    flex: 1; min-width: 130px; background: #111e35; border-radius: 8px;
    padding: 8px 11px; border: 1px solid #1a2d4a;
}
.leader-label { font-size: 0.65em; text-transform: uppercase; letter-spacing: 0.1em; color: #8a9bb5; }
.leader-team  { font-size: 0.85em; font-weight: 700; color: #e8edf5; margin: 3px 0 1px; display:flex; align-items:center; gap:5px; }
.leader-stat  { font-size: 0.75em; color: #8a9bb5; }
/* ── Team badge ── */
.team-badge {
    display: inline-flex; align-items: center; justify-content: center;
    border-radius: 50%; font-size: 0.6em; font-weight: 800; color: white;
    flex-shrink: 0; vertical-align: middle; line-height: 1;
}
/* ── Standings rows ── */
.div-label {
    font-size: 0.65em; text-transform: uppercase; letter-spacing: 0.1em;
    color: #8a9bb5; margin: 8px 0 4px; padding-bottom: 3px; border-bottom: 1px solid #1a2d4a;
}
.stand-row {
    display: flex; align-items: center; padding: 4px 0; gap: 5px;
    border-bottom: 1px solid #1a2d4a; font-size: 0.85em;
}
.stand-medal { width: 22px; flex-shrink: 0; }
.stand-name  { flex: 1; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; color: #e8edf5; }
.stand-record { color: #8a9bb5; font-size: 0.82em; white-space: nowrap; }
.div-leader-tag {
    font-size: 0.6em; color: #f0c040; font-weight: 700;
    background: rgba(240,192,64,0.15); border-radius: 3px; padding: 1px 4px; margin-left: 3px;
}
/* ── Power rankings rows ── */
.pr-row {
    display: flex; align-items: center; padding: 3px 0; gap: 4px;
    border-bottom: 1px solid #1a2d4a; font-size: 0.84em;
}
.pr-rank  { width: 20px; font-weight: 700; color: #f0c040; flex-shrink: 0; }
.pr-name  { flex: 1; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; color: #e8edf5; }
.pr-arrow { width: 26px; text-align: center; font-size: 0.72em; }
.pr-form  { font-size: 0.72em; white-space: nowrap; }
/* ── News ── */
.news-item    { padding: 6px 0; border-bottom: 1px solid #1a2d4a; }
.news-item:last-child { border-bottom: none; }
.news-week    { font-size: 0.65em; font-weight: 800; text-transform: uppercase; letter-spacing: 0.1em; color: #f0c040; }
.news-headline { font-size: 0.83em; color: #c8d4e8; margin-top: 2px; line-height: 1.35; }
/* ── Playoff picture ── */
.playoff-tier { display: flex; align-items: flex-start; gap: 8px; margin: 5px 0; flex-wrap: wrap; }
.playoff-tier-label { font-size: 0.65em; font-weight: 800; text-transform: uppercase; width: 52px; padding-top: 5px; flex-shrink: 0; }
.playoff-chip {
    display: inline-flex; align-items: center; gap: 4px;
    padding: 3px 9px; border-radius: 16px; font-size: 0.78em; font-weight: 600; margin: 2px;
}
.chip-in     { background: rgba(34,197,94,0.15); color: #22c55e; border: 1px solid rgba(34,197,94,0.3); }
.chip-bubble { background: rgba(240,192,64,0.15); color: #f0c040; border: 1px solid rgba(240,192,64,0.3); }
.chip-out    { background: rgba(239,68,68,0.12); color: #ef4444; border: 1px solid rgba(239,68,68,0.25); }
/* ── Season preview compact card ── */
.preview-card {
    background: linear-gradient(90deg, #0a1628 0%, #0d2d6e 100%);
    color: #e8edf5; border-radius: 10px; padding: 10px 16px;
    margin-bottom: 14px; border-left: 4px solid #f0c040;
    display: flex; align-items: center; gap: 12px; flex-wrap: wrap;
}
.preview-card-label { font-size: 0.7em; font-weight: 800; letter-spacing: 0.1em; text-transform: uppercase; color: #f0c040; white-space: nowrap; }
.preview-card-hed   { font-size: 0.88em; font-weight: 700; flex: 1; }
.preview-card-by    { font-size: 0.72em; opacity: 0.55; white-space: nowrap; }
</style>
""", unsafe_allow_html=True)


# ── Import shared helpers ─────────────────────────────────────────────────────
from helpers import (
    DATA_ROOT,
    AWARD_DEFS,
    LOWER_IS_BETTER_DEFAULT,
    WRITER_STYLES,
    get_available_seasons,
    load_all_weeks,
    load_all_seasons_data,
    load_divisions,
    load_team_logos,
    compute_standings,
    compute_streaks,
    compute_luck_ratings,
    compute_power_rankings,
    compute_rivalry_stats,
    compute_season_awards,
    compute_weekly_awards,
    compute_alltime_stats,
    is_season_complete,
    get_winner,
    category_winner,
    build_category_df,
    week_label,
    render_award_card,
    render_weekly_award_badges,
    render_player_card,
    _team_color,
    _team_initials,
    _badge_html,
    generate_trade_article,
    generate_weekly_recap_article,
    save_recap_article,
    save_trade_article,
    _get_anthropic_key,
)


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

selected_week: int | str | None = None   # set inside sidebar else-branch

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
        # ── Pre-season dashboard ───────────────────────────────────────────────
        draft_file = DATA_ROOT / str(selected_season) / "draft_order.json"
        if draft_file.exists():
            try:
                with open(draft_file) as f:
                    draft_data = json.load(f)
            except Exception:
                draft_data = {}

            draft_date_str = draft_data.get("draft_date", "")
            try:
                draft_dt   = datetime.strptime(draft_date_str, "%Y-%m-%d")
                days_until  = (draft_dt.date() - datetime.today().date()).days
                if days_until > 0:
                    countdown = f"Draft in {days_until} day{'s' if days_until != 1 else ''} · {draft_date_str}"
                elif days_until == 0:
                    countdown = "🚨 Draft Day!"
                else:
                    countdown = f"Drafted {abs(days_until)} day{'s' if abs(days_until) != 1 else ''} ago · Season starting soon"
            except Exception:
                countdown = draft_date_str or "Draft date TBD"

            st.markdown(f"""
            <div class="preseason-banner">
                <div class="preseason-title">⚾ {selected_season} Season</div>
                <div class="preseason-sub">Pre-Season · {countdown}</div>
            </div>
            """, unsafe_allow_html=True)

            draft_order = draft_data.get("draft_order", [])
            if draft_order:
                st.markdown("### 📋 Draft Order")
                st.caption(f"{draft_data.get('draft_format', 'Snake draft').replace('_',' ').title()} — {draft_data.get('notes','')}")
                n = len(draft_order)
                cols = st.columns(2)
                for pick_info in draft_order:
                    pick    = pick_info["pick"]
                    manager = pick_info["manager"]
                    with cols[(pick - 1) % 2]:
                        medal = "🥇" if pick == 1 else ("🥈" if pick == 2 else ("🥉" if pick == 3 else ""))
                        st.markdown(
                            f'<div class="draft-pick-row">'
                            f'<span class="draft-pick-num">#{pick}</span>'
                            f'<span class="draft-pick-name">{manager}</span>'
                            f'<span class="draft-pick-note">{medal}</span>'
                            f'</div>',
                            unsafe_allow_html=True,
                        )
        else:
            st.warning(f"No data found for {selected_season}.")
        # (no st.stop here — main content handled after sidebar)

    else:  # has week data — show week picker + sidebar standings
        available_weeks = sorted(weeks_data.keys(), reverse=True)
        league_name     = weeks_data[available_weeks[0]].get("league_name", "Fantasy Baseball League")
        st.caption(league_name)

        _preview_path_chk = DATA_ROOT / str(selected_season) / "articles" / "season_preview.json"
        _week_opts = (["preview"] if _preview_path_chk.exists() else []) + available_weeks
        selected_week = st.selectbox(
            "Select Week",
            options=_week_opts,
            format_func=lambda w: "📋 Season Preview" if w == "preview" else week_label(w, weeks_data[w]),
        )
        st.divider()

        # Sidebar standings
        _wf_sidebar   = tuple(sorted(weeks_data.items()))
        all_standings = compute_standings(_wf_sidebar, available_weeks[0])

        if all_standings:
            st.subheader("Standings")
            team_search  = st.text_input("🔍 Search team", placeholder="Team name...", label_visibility="collapsed")
            filtered_st  = [s for s in all_standings if not team_search or team_search.lower() in s["name"].lower()]
            with st.expander("View All Teams", expanded=False):
                for s in filtered_st:
                    record = f"{s['wins']}-{s['losses']}" + (f"-{s['ties']}" if s.get("ties") else "")
                    st.caption(f"{s['rank']}. **{s['name']}** — {record}")

        st.divider()
        st.caption(f"📊 {len(available_weeks)} weeks · {len(available_seasons)} seasons")


# ══════════════════════════════════════════════════════════════════════════════
# PREVIEW ARTICLE RENDERER  (shared by pre-season gate and preview-week gate)
# ══════════════════════════════════════════════════════════════════════════════

def _render_preview_article(season: int) -> None:
    path = DATA_ROOT / str(season) / "articles" / "season_preview.json"
    if not path.exists():
        st.info(f"The {season} season preview hasn't been generated yet.")
        return
    try:
        with open(path) as _f:
            _pa = json.load(_f)
        _pw  = _pa.get("writer_name", "Staff")
        _po  = _pa.get("writer_outlet", "")
        _pd  = _pa.get("generated_at", "")[:10]
        _phl = _pa.get("headline", f"{season} Season Preview")
        _psd = _pa.get("subheadline", "")
        st.markdown(f"""
        <div class="preview-masthead">
          <div class="preview-label">Season Preview · {season}</div>
          <div class="preview-title">{_phl}</div>
          {'<div class="preview-deck">' + _psd + '</div>' if _psd else ''}
          <div class="preview-byline">By {_pw} &nbsp;·&nbsp; {_po}
          {'&nbsp;·&nbsp; ' + _pd if _pd else ''}</div>
        </div>
        """, unsafe_allow_html=True)
        st.write("")
        st.markdown(_pa.get("body", ""))
    except Exception as _e:
        st.error(f"Could not load preview article: {_e}")


# ── Pre-season gate (no week data yet) ───────────────────────────────────────
if not weeks_data:
    _render_preview_article(selected_season)
    st.stop()

# ── Preview week gate (in-season) ────────────────────────────────────────────
if selected_week == "preview":
    _render_preview_article(selected_season)
    st.stop()


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
season_awards = compute_season_awards(weeks_data) if season_complete else {}
weekly_awards = compute_weekly_awards(data, weeks_data)


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

tab_home, tab_week, tab_season, tab_news = st.tabs([
    "🏠 Home",
    "⚔️ This Week",
    "🏆 Season",
    "📰 News",
])


# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — HOME
# ══════════════════════════════════════════════════════════════════════════════

with tab_home:

    # ── Season Preview compact card ───────────────────────────────────────────
    _preview_path = DATA_ROOT / str(selected_season) / "articles" / "season_preview.json"
    if _preview_path.exists():
        try:
            with open(_preview_path) as _pf:
                _prev_art = json.load(_pf)
            _prev_hed    = _prev_art.get("headline", f"{selected_season} Season Preview")
            _prev_writer = _prev_art.get("writer_name", "Staff")
            _prev_date   = _prev_art.get("generated_at", "")[:10]
            st.markdown(f"""
            <div class="preview-card">
              <span class="preview-card-label">📋 {selected_season} Season Preview</span>
              <span class="preview-card-hed">{_prev_hed}</span>
              <span class="preview-card-by">by {_prev_writer} · {_prev_date}
                &nbsp;·&nbsp; <em>Select "📋 Season Preview" in the week picker to read</em></span>
            </div>""", unsafe_allow_html=True)
        except Exception:
            pass

    # ── Build logo lookup: file-based first, then overlay current week data ───
    _logo_lookup: dict[str, str] = dict(load_team_logos())
    for _m in matchups:
        for _t in _m.get("teams", []):
            if _t.get("logo_url"):
                _logo_lookup[_t["name"]] = _t["logo_url"]

    # ── League leaders bar ────────────────────────────────────────────────────
    if standings:
        _home_divs   = load_divisions(selected_season)
        _pr_list_ldr = compute_power_rankings(_weeks_frozen, tuple(standings))
        _most_pf     = max(standings, key=lambda s: s["points_for"])
        _best_def    = min(standings, key=lambda s: s["points_against"])
        _hot_team    = _pr_list_ldr[0] if _pr_list_ldr else standings[0]

        _leader_cells = [
            ("🏆", "Best Record",     standings[0]["name"], f"{standings[0]['wins']}-{standings[0]['losses']}"),
            ("⚡", "Most Points For", _most_pf["name"],     f"{_most_pf['points_for']:.0f} pts"),
            ("🛡️", "Fewest Against",  _best_def["name"],    f"{_best_def['points_against']:.0f} pts"),
            ("🔥", "Power #1",        _hot_team["name"],    f"PR rank {_hot_team['pr_rank']}" if _pr_list_ldr else "—"),
        ]
        for _dn, _dt in _home_divs.items():
            _div_st = sorted([s for s in standings if s["name"] in _dt], key=lambda s: s["rank"])
            if _div_st:
                _short = _dn.replace("League", "Lge")
                _leader_cells.append(("🏟️", f"{_short} Leader", _div_st[0]["name"], f"{_div_st[0]['wins']}-{_div_st[0]['losses']}"))

        _cells_html = ""
        for _icon, _lbl, _team, _val in _leader_cells:
            _b = _badge_html(_team, _logo_lookup.get(_team, ""), 18)
            _cells_html += (
                f'<div class="leader-cell">'
                f'<div class="leader-label">{_icon} {_lbl}</div>'
                f'<div class="leader-team">{_b}{_team}</div>'
                f'<div class="leader-stat">{_val}</div>'
                f'</div>'
            )
        st.markdown(f'<div class="leaders-bar">{_cells_html}</div>', unsafe_allow_html=True)

    # ── Main three-panel row ──────────────────────────────────────────────────
    _home_divs = load_divisions(selected_season)
    col_stand, col_pr, col_news = st.columns([5, 3, 4])

    # ─ Standings (built as single HTML string to avoid Streamlit div bug) ─────
    with col_stand:
        _sh = '<div class="panel-box"><div class="section-header">🏆 Standings</div>'
        if _home_divs and standings:
            _div_leader_names: set[str] = set()
            for _dn, _dt in _home_divs.items():
                _dss = sorted([s for s in standings if s["name"] in _dt], key=lambda s: s["rank"])
                if _dss:
                    _div_leader_names.add(_dss[0]["name"])

            _sh += '<div style="display:flex;gap:14px;">'
            for _div_name, _div_teams in _home_divs.items():
                _div_st = sorted([s for s in standings if s["name"] in _div_teams], key=lambda s: s["rank"])
                _sh += f'<div style="flex:1;min-width:0;"><div class="div-label">{_div_name}</div>'
                for s in _div_st:
                    rec   = f"{s['wins']}-{s['losses']}"
                    medal = "🥇" if s["rank"] == 1 else "🥈" if s["rank"] == 2 else "🥉" if s["rank"] == 3 else f"{s['rank']}."
                    badge = _badge_html(s["name"], _logo_lookup.get(s["name"], ""), 20)
                    dtag  = '<span class="div-leader-tag">DIV</span>' if s["name"] in _div_leader_names else ""
                    _sh += (
                        f'<div class="stand-row">'
                        f'<span class="stand-medal">{medal}</span>{badge}'
                        f'<span class="stand-name" style="font-size:0.82em">{s["name"]}{dtag}</span>'
                        f'<span class="stand-record">{rec}</span>'
                        f'</div>'
                    )
                _sh += '</div>'
            _sh += '</div>'
        elif standings:
            for s in standings:
                rec   = f"{s['wins']}-{s['losses']}"
                medal = "🥇" if s["rank"] == 1 else "🥈" if s["rank"] == 2 else "🥉" if s["rank"] == 3 else f"{s['rank']}."
                badge = _badge_html(s["name"], _logo_lookup.get(s["name"], ""), 20)
                _sh  += f'<div class="stand-row"><span class="stand-medal">{medal}</span>{badge}<span class="stand-name">{s["name"]}</span><span class="stand-record">{rec}</span></div>'
        else:
            _sh += '<p style="color:#8a9bb5;font-size:0.85em">No standings data yet.</p>'
        _sh += '</div>'
        st.markdown(_sh, unsafe_allow_html=True)

    # ─ Power Rankings ─────────────────────────────────────────────────────────
    with col_pr:
        _pr_list = compute_power_rankings(_weeks_frozen, tuple(standings))
        _prh = '<div class="panel-box"><div class="section-header">⚡ Power Rankings</div>'
        if _pr_list:
            for r in _pr_list:
                diff  = r["rank_diff"]
                arr   = (f'<span style="color:#22c55e">▲{diff}</span>'  if diff > 0 else
                         f'<span style="color:#ef4444">▼{abs(diff)}</span>' if diff < 0 else
                         '<span style="color:#8a9bb5">—</span>')
                form  = r["recent_form"]
                fc    = "#22c55e" if form.startswith(("3-", "2-")) else ("#ef4444" if form.endswith(("-3", "-2")) else "#8a9bb5")
                badge = _badge_html(r["name"], _logo_lookup.get(r["name"], ""), 18)
                _prh += (
                    f'<div class="pr-row">'
                    f'<span class="pr-rank">{r["pr_rank"]}.</span>{badge}'
                    f'<span class="pr-name">{r["name"]}</span>'
                    f'<span class="pr-arrow">{arr}</span>'
                    f'<span class="pr-form" style="color:{fc}">({form})</span>'
                    f'</div>'
                )
        else:
            _prh += '<p style="color:#8a9bb5;font-size:0.82em">Rankings available once games are played.</p>'
        _prh += '</div>'
        st.markdown(_prh, unsafe_allow_html=True)

    # ─ Latest News ────────────────────────────────────────────────────────────
    with col_news:
        _nh = '<div class="panel-box"><div class="section-header">📰 Latest</div>'
        _all_articles: list[tuple[str, str, str]] = []
        for _wk in available_weeks:
            _wd     = weeks_data[_wk]
            _recap  = _wd.get("recap_text", "")
            if _recap:
                _lbl = week_label(_wk, _wd)
                _hed = _recap.split("\n")[0].strip().lstrip("#").strip()
                _all_articles.append(("recap", _lbl, _hed))
            for _tx in _wd.get("transactions", []):
                _art = _tx.get("article", {})
                if _art.get("headline"):
                    _all_articles.append(("trade", f"Week {_wk} · Trade", _art["headline"]))

        for _atype, _albl, _ahed in _all_articles[:5]:
            _icon = "📰" if _atype == "recap" else "🔄"
            _nh += (
                f'<div class="news-item">'
                f'<div class="news-week">{_icon} {_albl}</div>'
                f'<div class="news-headline">{_ahed[:90]}{"…" if len(_ahed) > 90 else ""}</div>'
                f'</div>'
            )
        if not _all_articles:
            _nh += '<p style="color:#8a9bb5;font-size:0.82em">No recaps generated yet.</p>'
        _nh += '</div>'
        st.markdown(_nh, unsafe_allow_html=True)

    # ── Playoff Picture (regular season only) ─────────────────────────────────
    if standings and not season_complete and not is_playoff_week:
        _PLAYOFF_SPOTS = 6
        _pp_in     = [s for s in standings if s["rank"] <= _PLAYOFF_SPOTS]
        _pp_bubble = [s for s in standings if s["rank"] in (_PLAYOFF_SPOTS + 1, _PLAYOFF_SPOTS + 2)]
        _pp_out    = [s for s in standings if s["rank"] > _PLAYOFF_SPOTS + 2]

        def _pp_chip(s: dict, cls: str) -> str:
            b = _badge_html(s["name"], _logo_lookup.get(s["name"], ""), 16)
            return f'<span class="playoff-chip {cls}">{b}{s["name"]}</span>'

        _pph = (
            '<div class="panel-box" style="margin-top:14px">'
            '<div class="section-header">🏟️ Playoff Picture</div>'
            '<div class="playoff-tier">'
            '<span class="playoff-tier-label" style="color:#155724">IN</span>'
            '<div>' + ''.join(_pp_chip(s, "chip-in") for s in _pp_in) + '</div></div>'
        )
        if _pp_bubble:
            _pph += (
                '<div class="playoff-tier">'
                '<span class="playoff-tier-label" style="color:#856404">BUBBLE</span>'
                '<div>' + ''.join(_pp_chip(s, "chip-bubble") for s in _pp_bubble) + '</div></div>'
            )
        _pph += (
            '<div class="playoff-tier">'
            '<span class="playoff-tier-label" style="color:#721c24">OUT</span>'
            '<div>' + ''.join(_pp_chip(s, "chip-out") for s in _pp_out) + '</div></div>'
            '</div>'
        )
        st.markdown(_pph, unsafe_allow_html=True)

    st.divider()

    # ── This week's scores ────────────────────────────────────────────────────
    st.markdown('<div class="section-header">⚔️ This Week\'s Scores</div>', unsafe_allow_html=True)
    score_cols = st.columns(2)
    for i, m in enumerate(matchups):
        if len(m["teams"]) < 2:
            continue
        t1, t2     = m["teams"][0], m["teams"][1]
        winner_key = m.get("winner_key")
        t1_bold    = "score-winner" if winner_key == t1["team_key"] else ""
        t2_bold    = "score-winner" if winner_key == t2["team_key"] else ""
        icon       = "🏆" if m.get("is_championship") else ("🥉" if m.get("is_third_place") else ("🥊" if m.get("is_playoffs") else "⚾"))
        with score_cols[i % 2]:
            st.markdown(f"""
            <div class="score-row">
                <span class="{t1_bold}">{t1['name']}</span>
                <span style="color:#8a9bb5;font-size:0.85em">{icon} {t1['points']:.0f} – {t2['points']:.0f}</span>
                <span class="{t2_bold}">{t2['name']}</span>
            </div>
            """, unsafe_allow_html=True)

    st.divider()

    # ── Weekly Awards ─────────────────────────────────────────────────────────
    st.markdown('<div class="section-header">🏅 Weekly Awards</div>', unsafe_allow_html=True)
    render_weekly_award_badges(weekly_awards)

    # ── Top Performers ────────────────────────────────────────────────────────
    top_players = data.get("top_players", [])
    if top_players:
        st.divider()
        st.markdown('<div class="section-header">⭐ Top Performers This Week</div>', unsafe_allow_html=True)
        show_players = top_players[:5]
        tp_cols = st.columns(len(show_players))
        for col, player in zip(tp_cols, show_players):
            with col:
                st.markdown(render_player_card(player, selected_season), unsafe_allow_html=True)

    # ── Season Awards (completed seasons only) ────────────────────────────────
    if season_complete and season_awards:
        st.divider()
        render_award_card(season_awards, selected_season)
    elif not season_complete and standings:
        st.divider()
        st.markdown('<div class="section-header">📊 Season Leaders (Live)</div>', unsafe_allow_html=True)
        lc1, lc2, lc3 = st.columns(3)
        lc1.metric("🏆 1st Place",     standings[0]["name"], f"{standings[0]['wins']}W-{standings[0]['losses']}L")
        most_pf_live  = max(standings, key=lambda s: s["points_for"])
        lc2.metric("🔥 Most PF",       most_pf_live["name"],  f"{most_pf_live['points_for']:.1f}")
        best_def_live = min(standings, key=lambda s: s["points_against"])
        lc3.metric("🛡️ Best Defense",  best_def_live["name"], f"{best_def_live['points_against']:.1f} PA")


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

        # ── Weekly Stars (player cards) ────────────────────────────────────────
        tp = data.get("top_players", [])
        if tp:
            st.divider()
            st.markdown("#### ⭐ Weekly Stars")
            st.caption("Top fantasy performers — season stats via MLB Stats API")
            star_cols = st.columns(min(len(tp[:5]), 5))
            for col, player in zip(star_cols, tp[:5]):
                with col:
                    st.markdown(render_player_card(player, selected_season), unsafe_allow_html=True)
            if len(tp) > 5:
                with st.expander(f"Show all {len(tp)} top players"):
                    more_cols = st.columns(5)
                    for i, player in enumerate(tp[5:]):
                        with more_cols[i % 5]:
                            st.markdown(render_player_card(player, selected_season), unsafe_allow_html=True)

    # ── Matchups ──────────────────────────────────────────────────────────────
    with inner_matchups:
        if not matchups:
            st.info("No matchup data available.")
        else:
            matchup_types = ["All"]
            if any(m.get("is_championship") for m in matchups):              matchup_types.append("Championship")
            if any(m.get("is_third_place")  for m in matchups):              matchup_types.append("3rd Place")
            if any(m.get("is_playoffs") and not m.get("is_consolation") and not m.get("is_championship") and not m.get("is_third_place") for m in matchups): matchup_types.append("Playoffs")
            if any(m.get("is_consolation")  for m in matchups):              matchup_types.append("Consolation")
            if any(not m.get("is_playoffs") and not m.get("is_consolation") for m in matchups): matchup_types.append("Regular Season")

            selected_type = st.radio("Filter matchups", matchup_types, horizontal=True) if len(matchup_types) > 2 else "All"

            def matchup_type_filter(m: dict) -> bool:
                if selected_type == "All":             return True
                if selected_type == "Championship":    return bool(m.get("is_championship"))
                if selected_type == "3rd Place":       return bool(m.get("is_third_place"))
                if selected_type == "Playoffs":        return m.get("is_playoffs") and not m.get("is_consolation") and not m.get("is_championship") and not m.get("is_third_place")
                if selected_type == "Consolation":     return bool(m.get("is_consolation"))
                if selected_type == "Regular Season":  return not m.get("is_playoffs") and not m.get("is_consolation")
                return True

            filtered_matchups = [m for m in matchups if matchup_type_filter(m)]

            all_teams = [t for m in filtered_matchups for t in m["teams"]]
            df_pts    = pd.DataFrame(all_teams).sort_values("points", ascending=True)
            colors    = ["#f0c040" if r == max(df_pts["points"]) else "#4a90d9" for r in df_pts["points"]]
            fig_pts   = go.Figure(go.Bar(
                x=df_pts["points"], y=df_pts["name"], orientation="h",
                marker_color=colors, text=df_pts["points"].apply(lambda x: f"{x:.0f}"), textposition="outside",
            ))
            fig_pts.update_layout(title=f"Week {selected_week} — Category Wins by Team",
                                  xaxis_title="Category Wins", yaxis_title="",
                                  template="plotly_dark", paper_bgcolor="#0a1628", plot_bgcolor="#111e35",
                                  height=max(300, len(all_teams) * 40), margin=dict(l=10, r=60, t=40, b=30))
            st.plotly_chart(fig_pts, use_container_width=True)

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
                fig_heat = px.imshow(df_heat, color_continuous_scale=["#ef4444", "#1a2d4a", "#22c55e"],
                                     color_continuous_midpoint=0, title="Category Heatmap (green = left team wins)", aspect="auto")
                fig_heat.update_layout(height=max(200, len(df_heat) * 60),
                                       template="plotly_dark", paper_bgcolor="#0a1628", plot_bgcolor="#111e35")
                st.plotly_chart(fig_heat, use_container_width=True)

            st.divider()
            st.subheader("Matchup Details")

            for m in filtered_matchups:
                if len(m["teams"]) < 2: continue
                t1, t2    = m["teams"][0], m["teams"][1]
                winner    = get_winner(m)
                icon      = "🏆" if m.get("is_championship") else ("🥉" if m.get("is_third_place") else ("😅" if m.get("is_consolation") else ("🥊" if m.get("is_playoffs") else "⚾")))
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
                        st.markdown("<p style='text-align:center;font-size:1.5em;padding-top:25px;color:#8a9bb5'>VS</p>", unsafe_allow_html=True)
                    with cb:
                        medal = "🏅 " if (winner and winner["team_key"] == t2["team_key"]) else ""
                        st.markdown(f"### {medal}{t2['name']}")
                        st.caption(f"Manager: {t2['manager']}")
                        st.metric("Category Wins", int(t2["points"]))

                    df_cats = build_category_df(t1, t2, lower_is_better)
                    if not df_cats.empty:
                        def highlight_winner(row):
                            if row["Winner"] == "←": return ["", "background-color: #1a4a2e; color: #22c55e", "", ""]
                            if row["Winner"] == "→": return ["", "", "", "background-color: #1a4a2e; color: #22c55e"]
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
                df_tx  = pd.DataFrame([{"Team": t, "Adds": c.get("add", 0), "Drops": c.get("drop", 0)}
                                        for t, c in sorted(team_counts.items(), key=lambda x: sum(x[1].values()), reverse=True)])
                fig_tx = px.bar(df_tx, x="Team", y=["Adds", "Drops"], barmode="group",
                                title="Transaction Activity", color_discrete_map={"Adds": "#22c55e", "Drops": "#ef4444"})
                fig_tx.update_layout(height=350, xaxis_tickangle=-30,
                                     template="plotly_dark", paper_bgcolor="#0a1628", plot_bgcolor="#111e35")
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
            c1.metric("🥇 First Place",     leader["name"],   f"{leader['wins']}W – {leader['losses']}L")
            c2.metric("🔥 Most Points For",  most_pf["name"],  f"{most_pf['points_for']:.1f} PF")
            c3.metric("🛡️ Best Defense",    least_pa["name"], f"{least_pa['points_against']:.1f} PA")
            st.divider()

            col_l, col_r = st.columns(2)
            with col_l:
                df_sorted = df_stand.sort_values("wins", ascending=True)
                fig_wins  = px.bar(df_sorted, x="wins", y="name", orientation="h", color="wins",
                                   color_continuous_scale=[[0, "#0d2d6e"], [1, "#f0c040"]], title="Season Wins",
                                   labels={"wins": "Wins", "name": ""}, text="wins")
                fig_wins.update_traces(textposition="outside")
                fig_wins.update_layout(showlegend=False, coloraxis_showscale=False,
                                       template="plotly_dark", paper_bgcolor="#0a1628", plot_bgcolor="#111e35",
                                       height=max(300, len(df_stand) * 35), margin=dict(l=10, r=40, t=40, b=20))
                st.plotly_chart(fig_wins, use_container_width=True)

            with col_r:
                fig_scatter = px.scatter(df_stand, x="points_against", y="points_for", text="name",
                                         color="wins", color_continuous_scale=[[0, "#ef4444"], [0.5, "#f0c040"], [1, "#22c55e"]],
                                         size=[15] * len(df_stand),
                                         title="Points For vs Points Against",
                                         labels={"points_for": "PF", "points_against": "PA", "wins": "Wins"})
                fig_scatter.update_traces(textposition="top center", textfont_size=10)
                fig_scatter.update_layout(height=420, template="plotly_dark",
                                          paper_bgcolor="#0a1628", plot_bgcolor="#111e35")
                st.plotly_chart(fig_scatter, use_container_width=True)

            st.subheader("Full Standings Table")
            df_display           = df_stand[["rank", "name", "wins", "losses", "ties", "points_for", "points_against"]].copy()
            df_display.columns   = ["Rank", "Team", "W", "L", "T", "PF", "PA"]
            total_games          = df_display["W"] + df_display["L"]
            df_display["Win%"]   = (df_display["W"] / total_games.replace(0, 1)).round(3)
            df_display["GB"]     = (df_display.iloc[0]["W"] - df_display["W"]) / 2
            st.dataframe(df_display.style.bar(subset=["Win%"], color=["#ef4444", "#22c55e"], vmin=0, vmax=1),
                         use_container_width=True, hide_index=True)

            st.divider()
            st.subheader("⚡ Power Rankings")
            st.caption("Weighted: 40% recent form (L3) · 30% season win% · 20% points-for · 10% strength of schedule")
            pr_full = compute_power_rankings(_weeks_frozen, tuple(standings))
            if pr_full:
                pr_rows = []
                for r in pr_full:
                    diff = r["rank_diff"]
                    move = f"▲{diff}" if diff > 0 else (f"▼{abs(diff)}" if diff < 0 else "—")
                    pr_rows.append({
                        "PR": r["pr_rank"], "Team": r["name"], "Move": move,
                        "L3": r["recent_form"], "W": r["wins"], "L": r["losses"],
                        "Win%": round(r["wins"] / max(r["wins"] + r["losses"], 1), 3),
                        "PF": round(r["points_for"], 1), "SOS": r["sos"], "PR Score": r["pr_score"],
                    })
                df_pr = pd.DataFrame(pr_rows)
                st.dataframe(
                    df_pr.style.bar(subset=["PR Score"], color=["#0d2d6e", "#f0c040"], vmin=0, vmax=1),
                    use_container_width=True, hide_index=True,
                )
                fig_pr = px.scatter(
                    df_pr, x="W", y="PR Score", text="Team",
                    color="PR Score", color_continuous_scale=[[0, "#ef4444"], [0.5, "#f0c040"], [1, "#22c55e"]],
                    size=[14] * len(df_pr),
                    title="Power Score vs Wins (teams above the line are outperforming their record)",
                )
                fig_pr.update_traces(textposition="top center", textfont_size=9)
                fig_pr.update_layout(height=420, coloraxis_showscale=False,
                                     template="plotly_dark", paper_bgcolor="#0a1628", plot_bgcolor="#111e35")
                st.plotly_chart(fig_pr, use_container_width=True)
            else:
                st.info("Power rankings available once games are played.")

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
                _dark_layout = dict(template="plotly_dark", paper_bgcolor="#0a1628", plot_bgcolor="#111e35")
                fig_rank = px.line(df_history, x="Week", y="Rank", color="Team",
                                   title="Standings Rank Over Time (lower = better)", markers=True)
                fig_rank.update_yaxes(autorange="reversed")
                fig_rank.update_layout(height=450, **_dark_layout)
                st.plotly_chart(fig_rank, use_container_width=True)

                fig_wins_t = px.line(df_history, x="Week", y="Wins", color="Team",
                                     title="Cumulative Wins Over Time", markers=True)
                fig_wins_t.update_layout(height=400, **_dark_layout)
                st.plotly_chart(fig_wins_t, use_container_width=True)

                fig_pf = px.line(df_history, x="Week", y="PF", color="Team",
                                 title="Cumulative Points For Over Time", markers=True)
                fig_pf.update_layout(height=400, **_dark_layout)
                st.plotly_chart(fig_pf, use_container_width=True)

                weekly_pts = [{"Week": wk, "Team": t["name"], "Categories Won": t["points"]}
                              for wk, wd in sorted(weeks_data.items())
                              if week_range[0] <= wk <= week_range[1]
                              for m in wd.get("matchups", [])
                              for t in m.get("teams", []) if t["name"] in selected_teams]
                if weekly_pts:
                    fig_weekly = px.line(pd.DataFrame(weekly_pts), x="Week", y="Categories Won",
                                         color="Team", markers=True, title="Categories Won Per Team Per Week")
                    fig_weekly.update_layout(height=450, **_dark_layout)
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
                    df_ws  = df_streaks.sort_values("Best Win Streak", ascending=True)
                    fig_ws = px.bar(df_ws, x="Best Win Streak", y="Team", orientation="h",
                                    color="Best Win Streak", color_continuous_scale=[[0, "#0d2d6e"], [1, "#22c55e"]],
                                    title="Season-Best Win Streak per Team")
                    fig_ws.update_layout(coloraxis_showscale=False, height=max(300, len(df_ws)*35),
                                         template="plotly_dark", paper_bgcolor="#0a1628", plot_bgcolor="#111e35")
                    st.plotly_chart(fig_ws, use_container_width=True)
                with col_ls:
                    df_ls  = df_streaks.sort_values("Worst Lose Streak", ascending=True)
                    fig_ls = px.bar(df_ls, x="Worst Lose Streak", y="Team", orientation="h",
                                    color="Worst Lose Streak", color_continuous_scale=[[0, "#0d2d6e"], [1, "#ef4444"]],
                                    title="Season-Worst Lose Streak per Team")
                    fig_ls.update_layout(coloraxis_showscale=False, height=max(300, len(df_ls)*35),
                                         template="plotly_dark", paper_bgcolor="#0a1628", plot_bgcolor="#111e35")
                    st.plotly_chart(fig_ls, use_container_width=True)


# ══════════════════════════════════════════════════════════════════════════════
# TAB 4 — NEWS
# ══════════════════════════════════════════════════════════════════════════════

with tab_news:
    inner_tradewire, inner_recaps, inner_archive = st.tabs(
        ["📰 Trade Wire", "📝 Weekly Recaps", "📚 Recap Archive"]
    )

    # ── Trade Wire ────────────────────────────────────────────────────────────
    with inner_tradewire:
        trades_dir  = DATA_ROOT / str(selected_season) / "trades"
        trade_files = sorted(trades_dir.glob("*.json"), reverse=True) if trades_dir.exists() else []

        saved_articles:    list[dict] = []
        saved_timestamps:  set[int]   = set()
        for f in trade_files:
            try:
                with open(f) as fp:
                    a = json.load(fp)
                    saved_articles.append(a)
                    saved_timestamps.add(int(a.get("transaction_timestamp", 0)))
            except Exception:
                pass

        session_articles: list[dict] = st.session_state.get("generated_trade_articles", [])
        session_ts       = {int(a.get("transaction_timestamp", 0)) for a in session_articles}

        all_trades = [
            tx for wk_data in weeks_data.values()
            for tx in wk_data.get("transactions", [])
            if tx.get("type") == "trade"
        ]
        all_trades.sort(key=lambda t: t.get("timestamp", 0), reverse=True)
        unprocessed = [t for t in all_trades
                       if int(t.get("timestamp", 0)) not in saved_timestamps | session_ts]

        has_key = bool(_get_anthropic_key())

        st.markdown("""
        <div style="background:linear-gradient(135deg,#1f3a5f,#0a1628);color:white;
                    border-radius:10px;padding:16px 20px;margin-bottom:16px;">
          <div style="font-size:1.3em;font-weight:800;letter-spacing:0.5px">
            📰 BeerLeague Insider
          </div>
          <div style="font-size:0.85em;opacity:0.8;margin-top:2px">
            Breaking news · Trade analysis by Passan, Heyman &amp; more
          </div>
        </div>
        """, unsafe_allow_html=True)

        if unprocessed:
            if not has_key:
                st.warning(
                    f"**{len(unprocessed)} unprocessed trade(s) found.** "
                    "Add `ANTHROPIC_API_KEY` to your Streamlit secrets to auto-generate articles.",
                    icon="🔑",
                )
                for tx in unprocessed:
                    names = ", ".join(p.get("name", "") for p in tx.get("players", [])[:4])
                    st.caption(f"🔄 {names}{'…' if len(tx.get('players',[])) > 4 else ''}")
            else:
                st.info(f"**{len(unprocessed)} new trade(s)** detected without articles.", icon="🔄")
                league_pw  = st.text_input(
                    "🔑 League passphrase", type="password", key="tradewire_pw",
                    placeholder="Enter passphrase to unlock article generation",
                )
                correct_pw = st.secrets.get("LEAGUE_PASSWORD", "") if league_pw else ""
                pw_ok      = bool(league_pw and league_pw == correct_pw)
                if league_pw and not pw_ok:
                    st.error("Incorrect passphrase.", icon="🚫")
                if pw_ok and st.button("🤖 Generate BeerLeague Insider Articles", type="primary"):
                    new_articles = []
                    prog = st.progress(0, text="Generating articles…")
                    for i, tx in enumerate(unprocessed):
                        prog.progress((i + 1) / len(unprocessed),
                                      text=f"Writing article {i+1}/{len(unprocessed)}…")
                        article = generate_trade_article(tx, standings)
                        if article:
                            new_articles.append(article)
                            saved_path = save_trade_article(article, trades_dir)
                            if saved_path:
                                st.toast(f"Saved: {saved_path.name}", icon="💾")
                    prog.empty()
                    if new_articles:
                        existing = st.session_state.get("generated_trade_articles", [])
                        st.session_state["generated_trade_articles"] = existing + new_articles
                        st.success(f"Generated {len(new_articles)} article(s)! "
                                   "Commit the `data/{}/trades/` folder to persist them.".format(selected_season))
                        st.rerun()

        display_articles = saved_articles + session_articles
        display_articles.sort(key=lambda a: a.get("transaction_timestamp", 0), reverse=True)

        if not display_articles and not unprocessed:
            st.markdown("""
            <div style="text-align:center;padding:50px 20px;color:#aaa;">
              <div style="font-size:3em">📰</div>
              <div style="font-size:1.1em;font-weight:600;margin:12px 0">No trades yet this season</div>
              <div style="font-size:0.9em">When a trade is processed in Yahoo, the BeerLeague Insider<br>
              will automatically generate a breaking news article.</div>
            </div>""", unsafe_allow_html=True)

        for article in display_articles:
            team_a   = article.get("team_a", "Team A")
            team_b   = article.get("team_b", "Team B")
            grade_a  = article.get("grade_team_a", "—")
            grade_b  = article.get("grade_team_b", "—")
            headline = article.get("headline", "Trade")
            gen_date = article.get("generated_at", "")[:10]

            with st.expander(f"📰 {headline}", expanded=True):
                art_writer = article.get("writer_name", "Staff Reporter")
                art_outlet = article.get("writer_outlet", "BeerLeague Insider")
                outlet_colors = {
                    "ESPN":         ("#d00", "#fff"),
                    "MLB Network":  ("#002D72", "#fff"),
                    "The Athletic": ("#111", "#fff"),
                    "The Ringer":   ("#6600cc", "#fff"),
                }
                oc_bg, oc_fg = outlet_colors.get(art_outlet, ("#555", "#fff"))
                st.markdown(
                    f"<div style='margin-bottom:10px'>"
                    f"<span style='font-weight:700;font-size:0.95em'>{art_writer}</span>"
                    f"&nbsp;&nbsp;"
                    f"<span style='background:{oc_bg};color:{oc_fg};padding:2px 9px;"
                    f"border-radius:4px;font-size:0.75em;font-weight:700;"
                    f"letter-spacing:0.5px'>{art_outlet.upper()}</span>"
                    f"</div>",
                    unsafe_allow_html=True,
                )
                st.markdown(article.get("body", ""))
                st.divider()

                gc1, gc2, gc3 = st.columns([2, 2, 1])
                grade_color = lambda g: (
                    "#1a9850" if g and g[0] in "AB" else
                    ("#e07b00" if g and g[0] == "C" else "#d73027")
                )
                gc1.markdown(
                    f"<div style='text-align:center;background:#f8f9fa;border-radius:8px;padding:12px'>"
                    f"<div style='font-size:0.8em;color:#888'>GRADE · {team_a}</div>"
                    f"<div style='font-size:2em;font-weight:800;color:{grade_color(grade_a)}'>{grade_a}</div>"
                    f"</div>", unsafe_allow_html=True,
                )
                gc2.markdown(
                    f"<div style='text-align:center;background:#f8f9fa;border-radius:8px;padding:12px'>"
                    f"<div style='font-size:0.8em;color:#888'>GRADE · {team_b}</div>"
                    f"<div style='font-size:2em;font-weight:800;color:{grade_color(grade_b)}'>{grade_b}</div>"
                    f"</div>", unsafe_allow_html=True,
                )
                if gen_date:
                    gc3.caption(f"Generated\n{gen_date}")

    # ── Weekly Recaps ─────────────────────────────────────────────────────────
    with inner_recaps:
        articles_dir  = DATA_ROOT / str(selected_season) / "articles"
        recap_files   = sorted(articles_dir.glob("week_*_recap.json"), reverse=True) \
                        if articles_dir.exists() else []
        stored_recaps = st.session_state.get("recap_articles", [])

        disk_recaps: list[dict] = []
        for fp in recap_files:
            try:
                with open(fp) as f:
                    disk_recaps.append(json.load(f))
            except Exception:
                pass
        seen_weeks = {a["week"] for a in disk_recaps}
        all_recap_articles = disk_recaps + [
            a for a in stored_recaps if a.get("week") not in seen_weeks
        ]
        all_recap_articles.sort(key=lambda a: a.get("week", 0), reverse=True)

        st.markdown("""
        <div style="background:linear-gradient(135deg,#1a3a5c 0%,#2d6a3f 100%);
             color:white;border-radius:12px;padding:18px 22px;margin-bottom:16px;">
          <div style="font-size:1.3em;font-weight:800;letter-spacing:0.5px">
            📝 BeerLeague Weekly
          </div>
          <div style="font-size:0.85em;opacity:0.8;margin-top:2px">
            Weekly columns by Rosenthal, Olney, Simmons &amp; Gammons
          </div>
        </div>
        """, unsafe_allow_html=True)

        weeks_without_recap = [
            (wk, wd) for wk, wd in sorted(weeks_data.items(), reverse=True)
            if wd.get("matchups") and wk not in {a.get("week") for a in all_recap_articles}
        ]

        if weeks_without_recap and has_key:
            st.info(f"**{len(weeks_without_recap)} week(s)** have results but no column yet.", icon="📝")
            recap_pw = st.text_input(
                "🔑 League passphrase", type="password", key="recaps_pw",
                placeholder="Enter passphrase to unlock article generation",
            )
            correct_recap_pw = st.secrets.get("LEAGUE_PASSWORD", "") if recap_pw else ""
            recap_pw_ok      = bool(recap_pw and recap_pw == correct_recap_pw)
            if recap_pw and not recap_pw_ok:
                st.error("Incorrect passphrase.", icon="🚫")

            if recap_pw_ok:
                wk_options           = [f"Week {wk}" for wk, _ in weeks_without_recap]
                selected_gen_wk_label = st.selectbox("Generate column for:", wk_options, key="recap_gen_select")
                selected_gen_wk       = int(selected_gen_wk_label.split()[1])

                if st.button("✍️ Generate Weekly Column", type="primary", key="gen_recap_btn"):
                    wd_to_gen  = weeks_data[selected_gen_wk]
                    is_champ   = any(m.get("is_championship") for m in wd_to_gen.get("matchups", []))
                    is_playoff = any(m.get("is_playoffs") and not m.get("is_consolation")
                                     for m in wd_to_gen.get("matchups", []))
                    with st.spinner("Writing this week's column…"):
                        new_ra = generate_weekly_recap_article(
                            wd_to_gen,
                            standings,          # ← fixed: was standings_data (undefined)
                            is_playoff=is_playoff,
                            is_championship=is_champ,
                        )
                    if new_ra:
                        save_recap_article(new_ra, articles_dir)
                        existing = st.session_state.get("recap_articles", [])
                        st.session_state["recap_articles"] = existing + [new_ra]
                        all_recap_articles = [new_ra] + [
                            a for a in all_recap_articles if a.get("week") != new_ra.get("week")
                        ]
                        all_recap_articles.sort(key=lambda a: a.get("week", 0), reverse=True)
                        st.success(
                            f"Column written by **{new_ra['writer_name']}** ({new_ra['writer_outlet']})!",
                            icon="✍️",
                        )
                        st.rerun()

        elif weeks_without_recap and not has_key:
            st.warning(
                "Add `ANTHROPIC_API_KEY` to your Streamlit secrets to generate weekly columns.",
                icon="🔑",
            )

        if not all_recap_articles:
            st.markdown("""
            <div style="text-align:center;padding:40px 20px;color:#aaa">
              <div style="font-size:3em">📝</div>
              <div style="font-size:1.1em;font-weight:600;margin:12px 0">No columns yet this season</div>
              <div style="font-size:0.9em">Weekly columns will appear here once generated.<br>
              They can also be auto-created by the GitHub Actions runner.</div>
            </div>""", unsafe_allow_html=True)
        else:
            outlet_colors = {
                "ESPN":         ("#d00", "#fff"),
                "MLB Network":  ("#002D72", "#fff"),
                "The Athletic": ("#111", "#fff"),
                "The Ringer":   ("#6600cc", "#fff"),
            }
            st.caption(f"{len(all_recap_articles)} column(s) for {selected_season}")
            for ra in all_recap_articles:
                wk_num     = ra.get("week", "?")
                headline   = ra.get("headline", f"Week {wk_num} Recap")
                subdeck    = ra.get("subheadline", "")
                ra_writer  = ra.get("writer_name", "Staff")
                ra_outlet  = ra.get("writer_outlet", "BeerLeague Weekly")
                ra_date    = ra.get("generated_at", "")[:10]
                is_champ   = ra.get("is_championship", False)
                is_playoff = ra.get("is_playoff", False)
                week_badge = "🏆 Championship" if is_champ else ("🥊 Playoff" if is_playoff else f"Week {wk_num}")
                oc_bg, oc_fg = outlet_colors.get(ra_outlet, ("#555", "#fff"))

                with st.expander(f"📝 {week_badge}: {headline}", expanded=(ra is all_recap_articles[0])):
                    st.markdown(
                        f"<div style='margin-bottom:10px'>"
                        f"<span style='font-weight:700;font-size:0.95em'>{ra_writer}</span>"
                        f"&nbsp;&nbsp;"
                        f"<span style='background:{oc_bg};color:{oc_fg};padding:2px 9px;"
                        f"border-radius:4px;font-size:0.75em;font-weight:700;"
                        f"letter-spacing:0.5px'>{ra_outlet.upper()}</span>"
                        f"{'&nbsp;&nbsp;<span style=\"color:#888;font-size:0.82em\">' + ra_date + '</span>' if ra_date else ''}"
                        f"</div>",
                        unsafe_allow_html=True,
                    )
                    if subdeck:
                        st.markdown(f"*{subdeck}*")
                    st.divider()
                    st.markdown(ra.get("body", ""))

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
                    week_badges = compute_weekly_awards(wd, weeks_data)
                    if week_badges:
                        st.divider()
                        render_weekly_award_badges(week_badges)


# ── Footer ────────────────────────────────────────────────────────────────────
_last_updated = max(
    (weeks_data[w].get("generated_at", "") for w in weeks_data),
    default="",
)
_last_upd_str = _last_updated[:10] if _last_updated else "—"
st.markdown(
    f'<div class="footer-bar">'
    f'⚾ MillerLite® BeerLeagueBaseball &nbsp;·&nbsp; {selected_season} Season &nbsp;·&nbsp; '
    f'Data updated {_last_upd_str} &nbsp;·&nbsp; '
    f'Built with Streamlit &amp; Claude'
    f'</div>',
    unsafe_allow_html=True,
)
