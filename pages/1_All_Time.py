"""
pages/1_All_Time.py — All-Time Records & History

Standalone Streamlit page for the BeerLeagueBaseball dashboard.
Accessible via the sidebar navigation when running as a multi-page app.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure the project root is importable (handles both local dev and Streamlit Cloud)
_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import pandas as pd
import plotly.express as px
import streamlit as st

from helpers import (
    DATA_ROOT,
    AWARD_DEFS,
    compute_alltime_stats,
    compute_standings,
    compute_rivalry_stats,
    load_all_seasons_data,
    load_team_logos,
    render_award_card,
    _badge_html,
)

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="All-Time Records — BeerLeagueBaseball",
    page_icon="📖",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Shared CSS (trophy + award styles used on this page) ──────────────────────
st.markdown("""
<style>
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
.award-value  { color: #888; font-size: 0.82em; margin-left: 6px; }
.badge {
    display: inline-block; padding: 3px 10px; border-radius: 12px;
    font-size: 0.82em; font-weight: 600; margin: 3px 3px 3px 0;
}
.badge-gold  { background: #fff3cd; color: #856404; }
.badge-green { background: #d4edda; color: #155724; }
.badge-red   { background: #f8d7da; color: #721c24; }
.badge-blue  { background: #d1ecf1; color: #0c5460; }
.trophy-section {
    background: linear-gradient(135deg, #fff9e6, #fffbf0);
    border: 1px solid #f0c040; border-radius: 10px; padding: 16px; margin: 8px 0;
}
.team-badge {
    display: inline-flex; align-items: center; justify-content: center;
    border-radius: 50%; font-size: 0.6em; font-weight: 800; color: white;
    flex-shrink: 0; vertical-align: middle; line-height: 1;
}
footer { visibility: hidden; }
</style>
""", unsafe_allow_html=True)

# ── Load data ─────────────────────────────────────────────────────────────────
all_seasons  = load_all_seasons_data()
_logo_lookup = load_team_logos()

if not all_seasons:
    st.title("📖 All-Time Records")
    st.info("No season data found yet. Run the backfill script to load data.")
    st.stop()

_alltime_frozen = tuple(sorted(
    {s: tuple(sorted(wd.items())) for s, wd in all_seasons.items()}.items()
))

alltime           = compute_alltime_stats(_alltime_frozen)
team_stats_all    = alltime.get("teams", {})
season_awards_all = alltime.get("season_awards", {})

# ── Page header ───────────────────────────────────────────────────────────────
st.markdown("""
<div style="background:linear-gradient(135deg,#1f3a5f 0%,#1a9850 100%);
            padding:24px 32px;border-radius:12px;color:white;margin-bottom:16px;">
  <div style="font-size:2em;font-weight:800;margin:0">📖 All-Time Records</div>
  <div style="font-size:1em;opacity:0.85;margin:4px 0 0 0">
    MillerLite® BeerLeagueBaseball — Complete Historical Database
  </div>
</div>
""", unsafe_allow_html=True)

# ── Inner tabs ────────────────────────────────────────────────────────────────
inner_history, inner_h2h, inner_trophy, inner_awards_arch = st.tabs([
    "📅 History", "⚔️ Head-to-Head", "🏆 Trophy Case", "🎖️ Awards Archive"
])


# ══════════════════════════════════════════════════════════════════════════════
# HISTORY TABLE
# ══════════════════════════════════════════════════════════════════════════════

with inner_history:
    if not team_stats_all:
        st.info("Not enough data for all-time stats yet.")
    else:
        all_seasons_list = sorted(all_seasons.keys())
        history_rows = []
        for name, ts in team_stats_all.items():
            row = {
                "Team":       name,
                "Seasons":    ts["seasons"],
                "All-Time W": ts["wins"],
                "All-Time L": ts["losses"],
                "Win%":       ts["win_pct"],
                "🏆":          ts["championships"],
                "Finals":     ts["finals"],
                "💀":          ts["wooden_spoons"],
                "Total PF":   round(ts["points_for"], 1),
            }
            for yr in all_seasons_list:
                finish     = ts["season_finishes"].get(yr)
                row[str(yr)] = f"#{finish}" if finish else "—"
            history_rows.append(row)

        df_hist = pd.DataFrame(history_rows).sort_values("Win%", ascending=False)
        st.dataframe(df_hist, use_container_width=True, hide_index=True)


# ══════════════════════════════════════════════════════════════════════════════
# HEAD-TO-HEAD
# ══════════════════════════════════════════════════════════════════════════════

with inner_h2h:
    all_team_names_ever = sorted(team_stats_all.keys())
    if len(all_team_names_ever) < 2:
        st.info("Need at least 2 teams for head-to-head.")
    else:
        hc1, hc2 = st.columns(2)
        with hc1:
            h2h_team_a = st.selectbox("Team A", options=all_team_names_ever, key="h2h_a")
        with hc2:
            opts_b     = [t for t in all_team_names_ever if t != h2h_team_a]
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
                            h2h_matchups.append({
                                "Season": season_yr, "Week": wk,
                                f"{h2h_team_a} Pts": t_a["points"],
                                f"{h2h_team_b} Pts": t_b["points"],
                                "Winner": result_str,
                            })

            wa, wb        = h2h_records[h2h_team_a], h2h_records[h2h_team_b]
            series_leader = h2h_team_a if wa > wb else (h2h_team_b if wb > wa else "Tied")
            ha, hb        = st.columns(2)
            ha.metric(h2h_team_a, f"{wa}W",
                      f"{'Series Leader 👑' if series_leader == h2h_team_a else ''}")
            hb.metric(h2h_team_b, f"{wb}W",
                      f"{'Series Leader 👑' if series_leader == h2h_team_b else ''}")
            if h2h_records["ties"]:
                st.caption(f"Ties: {h2h_records['ties']}")

            if h2h_matchups:
                st.divider()
                st.subheader("All Matchups")
                st.dataframe(pd.DataFrame(h2h_matchups), use_container_width=True, hide_index=True)


# ══════════════════════════════════════════════════════════════════════════════
# TROPHY CASE
# ══════════════════════════════════════════════════════════════════════════════

with inner_trophy:
    if not team_stats_all:
        st.info("Not enough data yet.")
    else:
        # ── Championship Banner ────────────────────────────────────────────────
        st.subheader("🏆 Championship Rings")
        champs = sorted(
            [(ts["name"], ts["championships"], ts["season_finishes"])
             for ts in team_stats_all.values() if ts["championships"] > 0],
            key=lambda x: x[1], reverse=True,
        )
        if champs:
            max_rings = champs[0][1]
            for name, count, finishes in champs:
                champ_years = [str(yr) for yr, r in sorted(finishes.items()) if r == 1]
                badge_html  = _badge_html(name, _logo_lookup.get(name, ""), 22)
                st.markdown(
                    f"{'🏆' * count}&nbsp;{badge_html}&nbsp;<strong>{name}</strong>"
                    f"<span style='color:#888;font-size:0.85em'> ({', '.join(champ_years)})</span>",
                    unsafe_allow_html=True,
                )
        else:
            st.info("No championship data yet.")

        df_rings = pd.DataFrame([
            {"Team": ts["name"], "Championships": ts["championships"],
             "Finals": ts["finals"], "Wooden Spoons": ts["wooden_spoons"]}
            for ts in team_stats_all.values()
        ]).sort_values("Championships", ascending=False)

        if not df_rings.empty:
            fig_rings = px.bar(
                df_rings.sort_values("Championships", ascending=True),
                x="Championships", y="Team", orientation="h",
                color="Championships",
                color_continuous_scale=[[0, "#f0c040"], [1, "#c8960c"]],
                text="Championships", title="All-Time Championships",
            )
            fig_rings.update_traces(textposition="outside")
            fig_rings.update_layout(coloraxis_showscale=False,
                                    height=max(300, len(df_rings) * 35))
            st.plotly_chart(fig_rings, use_container_width=True)

        st.divider()

        # ── All-Time Win Leaders ───────────────────────────────────────────────
        st.subheader("📊 All-Time Win Leaders")
        df_wins = pd.DataFrame([
            {
                "Team":       ts["name"],
                "Seasons":    ts["seasons"],
                "Wins":       ts["wins"],
                "Losses":     ts["losses"],
                "Win%":       ts["win_pct"],
                "Avg Finish": round(
                    sum(ts["season_finishes"].values()) / len(ts["season_finishes"]), 1
                ) if ts["season_finishes"] else "—",
                "🏆": ts["championships"],
                "💀": ts["wooden_spoons"],
            }
            for ts in team_stats_all.values()
        ]).sort_values("Win%", ascending=False)
        st.dataframe(
            df_wins.style.bar(subset=["Win%"], color=["#f8d7da", "#d4edda"], vmin=0, vmax=1),
            use_container_width=True, hide_index=True,
        )

        st.divider()

        # ── Single Season Records ──────────────────────────────────────────────
        st.subheader("📈 Single Season Records")

        all_season_highs: list[dict] = []
        weekly_highs:     list[dict] = []

        for season_yr, wd in sorted(all_seasons.items()):
            if not wd:
                continue
            wf      = tuple(sorted(wd.items()))
            last_wk = max(wd.keys())
            st_list = compute_standings(wf, last_wk)
            if not st_list:
                continue

            best          = st_list[0]
            worst         = st_list[-1]
            most_pf_team  = max(st_list, key=lambda s: s["points_for"])
            least_pf_team = min(st_list, key=lambda s: s["points_for"])

            all_season_highs.append({
                "Season":          season_yr,
                "🥇 Best Record":  f"{best['name']} ({best['wins']}-{best['losses']})",
                "💀 Worst Record": f"{worst['name']} ({worst['wins']}-{worst['losses']})",
                "🔥 Most PF":      f"{most_pf_team['name']} ({most_pf_team['points_for']:.0f})",
                "🧊 Fewest PF":    f"{least_pf_team['name']} ({least_pf_team['points_for']:.0f})",
            })

            for wk, wkd in wd.items():
                for m in wkd.get("matchups", []):
                    for t in m.get("teams", []):
                        if t.get("points", 0) > 0:
                            weekly_highs.append({
                                "season": season_yr, "week": wk,
                                "team": t["name"], "score": t["points"],
                            })

        if all_season_highs:
            st.dataframe(pd.DataFrame(all_season_highs),
                         use_container_width=True, hide_index=True)

        if weekly_highs:
            st.divider()
            wh_df  = pd.DataFrame(weekly_highs)
            tc1, tc2 = st.columns(2)
            with tc1:
                st.markdown("**🔥 Highest Single-Week Scores (All-Time)**")
                top_scores = (wh_df.sort_values("score", ascending=False).head(10)
                              .rename(columns={"season": "Season", "week": "Week",
                                               "team": "Team", "score": "Cat Wins"}))
                st.dataframe(top_scores, use_container_width=True, hide_index=True)
            with tc2:
                st.markdown("**🧊 Lowest Single-Week Scores (All-Time)**")
                bot_scores = (wh_df.sort_values("score").head(10)
                              .rename(columns={"season": "Season", "week": "Week",
                                               "team": "Team", "score": "Cat Wins"}))
                st.dataframe(bot_scores, use_container_width=True, hide_index=True)

        st.divider()

        # ── Rivalry Board ──────────────────────────────────────────────────────
        st.subheader("⚔️ Rivalry Board")
        st.caption("Most-played matchups across all seasons")
        rivalries = compute_rivalry_stats(all_seasons)
        if rivalries:
            rivalry_rows = []
            for rv in rivalries[:15]:
                a_wins, b_wins = rv["a_wins"], rv["b_wins"]
                leader = rv["team_a"] if a_wins > b_wins else (
                    rv["team_b"] if b_wins > a_wins else "Even"
                )
                rivalry_rows.append({
                    "Team A":         rv["team_a"],
                    "Record":         f"{a_wins}–{b_wins}" + (f"–{rv['ties']}" if rv["ties"] else ""),
                    "Team B":         rv["team_b"],
                    "Games":          rv["games"],
                    "Series Leader":  f"{'👑 ' if leader != 'Even' else ''}{leader}",
                })
            st.dataframe(pd.DataFrame(rivalry_rows),
                         use_container_width=True, hide_index=True)

            df_rv_plot = pd.DataFrame([{
                "Matchup": f"{rv['team_a']} vs\n{rv['team_b']}",
                "A Wins":  rv["a_wins"],
                "B Wins":  rv["b_wins"],
            } for rv in rivalries[:10]])
            fig_rv = px.bar(
                df_rv_plot, x="Matchup", y=["A Wins", "B Wins"],
                barmode="stack", title="Top 10 Rivalries — All-Time Record",
                color_discrete_map={"A Wins": "#1a9850", "B Wins": "#d73027"},
            )
            fig_rv.update_layout(height=380, xaxis_tickangle=-20)
            st.plotly_chart(fig_rv, use_container_width=True)


# ══════════════════════════════════════════════════════════════════════════════
# AWARDS ARCHIVE
# ══════════════════════════════════════════════════════════════════════════════

with inner_awards_arch:
    completed = [(yr, sa) for yr, sa in sorted(season_awards_all.items(), reverse=True) if sa]
    if not completed:
        st.info("No completed seasons with award data yet.")
    else:
        for yr, sa in completed:
            render_award_card(sa, yr)
            st.write("")

# ── Footer ────────────────────────────────────────────────────────────────────
st.markdown(
    '<div style="text-align:center;color:#aaa;font-size:0.78em;'
    'padding:18px 0 6px 0;border-top:1px solid #f0f0f0;margin-top:24px;">'
    '⚾ MillerLite® BeerLeagueBaseball &nbsp;·&nbsp; All-Time Records &nbsp;·&nbsp; '
    'Built with Streamlit &amp; Claude'
    '</div>',
    unsafe_allow_html=True,
)
