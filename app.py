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

DATA_ROOT = Path(__file__).parent / "data"

LOWER_IS_BETTER_DEFAULT = {"ERA", "WHIP"}


# ── Season detection ──────────────────────────────────────────────────────────
def get_available_seasons() -> list[int]:
    """Return sorted list of seasons that have data in data/{year}/ subfolders."""
    if not DATA_ROOT.exists():
        return []
    seasons = []
    for d in DATA_ROOT.iterdir():
        if d.is_dir() and d.name.isdigit() and list(d.glob("week_*.json")):
            seasons.append(int(d.name))
    return sorted(seasons, reverse=True)


# ── Data loading ──────────────────────────────────────────────────────────────
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


# ── Standings reconstruction ──────────────────────────────────────────────────
@st.cache_data(ttl=60)
def compute_standings(weeks_data_frozen: tuple, up_to_week: int) -> list[dict]:
    """
    Reconstruct standings from matchup data up to (and including) up_to_week.
    Yahoo's standings API returns zeros for completed historical leagues,
    so we derive wins/losses/PF/PA directly from matchup results.
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
                r1["ties"] += 1
                r2["ties"] += 1
            elif m.get("winner_key") == t1["team_key"]:
                r1["wins"] += 1
                r2["losses"] += 1
            elif m.get("winner_key") == t2["team_key"]:
                r2["wins"] += 1
                r1["losses"] += 1

    result = list(records.values())
    result.sort(key=lambda x: (-x["wins"], -x["points_for"]))
    for i, s in enumerate(result):
        s["rank"] = i + 1
    return result


# ── Helpers ───────────────────────────────────────────────────────────────────
def get_winner(matchup: dict) -> dict | None:
    if matchup.get("is_tied") or not matchup.get("winner_key"):
        return None
    teams = matchup["teams"]
    return next((t for t in teams if t["team_key"] == matchup["winner_key"]), None)


def category_winner(v1, v2, cat: str, lower_is_better: set[str]) -> str:
    """Return '←', '→', or 'tie' relative to team 1 vs team 2."""
    try:
        f1, f2 = float(v1), float(v2)
        if f1 == f2:
            return "tie"
        if cat in lower_is_better:
            return "←" if f1 < f2 else "→"
        return "←" if f1 > f2 else "→"
    except (TypeError, ValueError):
        return ""


def build_category_df(t1: dict, t2: dict, lower_is_better: set[str]) -> pd.DataFrame:
    cats1 = t1.get("category_stats", {})
    cats2 = t2.get("category_stats", {})
    all_cats = sorted(set(cats1) | set(cats2))
    rows = []
    for cat in all_cats:
        v1 = cats1.get(cat, "–")
        v2 = cats2.get(cat, "–")
        winner = category_winner(v1, v2, cat, lower_is_better)
        rows.append({
            "Category": cat,
            t1["name"]: v1,
            "Winner": winner,
            t2["name"]: v2,
        })
    return pd.DataFrame(rows)


def week_label(w: int, data: dict) -> str:
    is_champ = any(m.get("is_championship") for m in data.get("matchups", []))
    is_playoff = any(m.get("is_playoffs") and not m.get("is_consolation") for m in data.get("matchups", []))
    suffix = " 🏆" if is_champ else (" 🥊" if is_playoff else "")
    return f"Week {w}{suffix}"


# ── Load data ─────────────────────────────────────────────────────────────────
available_seasons = get_available_seasons()

if not available_seasons:
    st.title("⚾ BeerLeagueBaseball Recap")
    st.info(
        "No weekly data found yet.\n\n"
        "Run `python3 backfill.py --year 2025` to pull data from Yahoo."
    )
    st.stop()

# ── Sidebar ───────────────────────────────────────────────────────────────────
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
    league_name = weeks_data[available_weeks[0]].get("league_name", "Fantasy Baseball League")
    st.caption(league_name)

    selected_week = st.selectbox(
        "Select Week",
        options=available_weeks,
        format_func=lambda w: week_label(w, weeks_data[w]),
    )
    st.divider()

    # Season summary in sidebar (use reconstructed standings from all available weeks)
    all_standings = compute_standings(tuple(sorted(weeks_data.items())), available_weeks[0])
    if all_standings:
        st.subheader("Current Standings")
        with st.expander("View All Teams", expanded=False):
            for s in all_standings:
                record = f"{s['wins']}-{s['losses']}"
                if s.get("ties"):
                    record += f"-{s['ties']}"
                st.caption(f"{s['rank']}. **{s['name']}** — {record}")

    st.divider()
    st.caption(f"📊 {len(available_weeks)} week(s) of data available")

# ── Selected week data ────────────────────────────────────────────────────────
data = weeks_data[selected_week]
matchups = data.get("matchups", [])
# Reconstruct standings from matchup history (Yahoo API returns zeros for historical leagues)
_weeks_frozen = tuple(sorted(weeks_data.items()))
standings = compute_standings(_weeks_frozen, selected_week)
transactions = data.get("transactions", [])
top_players = data.get("top_players", [])
lower_is_better: set[str] = set(data.get("lower_is_better_stats", [])) or LOWER_IS_BETTER_DEFAULT

playoff_games = [m for m in matchups if m.get("is_playoffs") and not m.get("is_consolation")]
is_championship = any(m.get("is_championship") for m in matchups)
is_playoff_week = bool(playoff_games)

# ── Page header ───────────────────────────────────────────────────────────────
if is_championship:
    st.markdown(f"# 🏆 {selected_season} — Week {selected_week} Championship")
elif is_playoff_week:
    st.markdown(f"# 🥊 {selected_season} — Week {selected_week} Playoffs")
else:
    st.markdown(f"# ⚾ {selected_season} — Week {selected_week} Recap")

if data.get("generated_at"):
    st.caption(f"Generated {data['generated_at'][:10]}")

st.divider()

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab_recap, tab_matchups, tab_standings, tab_season, tab_transactions = st.tabs([
    "📝 Recap",
    "⚔️ Matchups",
    "🏆 Standings",
    "📈 Season Trends",
    "🔄 Transactions",
])

# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — RECAP
# ══════════════════════════════════════════════════════════════════════════════
with tab_recap:
    recap_text = data.get("recap_text", "")
    if recap_text:
        # Two-column layout: recap on left, quick stats on right
        col_main, col_side = st.columns([3, 1])
        with col_main:
            st.markdown(recap_text)
        with col_side:
            st.subheader("Quick Stats")
            all_teams_pts = sorted(
                [t for m in matchups for t in m["teams"]],
                key=lambda t: t["points"],
                reverse=True,
            )
            if all_teams_pts:
                top = all_teams_pts[0]
                bot = all_teams_pts[-1]
                st.metric("🔥 High Score", f"{top['name']}", f"{top['points']:.0f} cats")
                st.metric("❄️ Low Score", f"{bot['name']}", f"{bot['points']:.0f} cats", delta_color="off")
                st.divider()
                st.caption("**All Teams This Week** _(category wins)_")
                for t in all_teams_pts:
                    st.caption(f"{t['name']} — **{t['points']:.0f}** cats won")
    else:
        st.info("No recap generated for this week yet. Run `python3 main.py --dry-run` to generate one.")

# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — MATCHUPS
# ══════════════════════════════════════════════════════════════════════════════
with tab_matchups:
    if not matchups:
        st.info("No matchup data available.")
    else:
        # Matchup type filter
        matchup_types = ["All"]
        if any(m.get("is_championship") for m in matchups):
            matchup_types.append("Championship")
        if any(m.get("is_third_place") for m in matchups):
            matchup_types.append("3rd Place")
        if any(m.get("is_playoffs") and not m.get("is_consolation") and not m.get("is_championship") and not m.get("is_third_place") for m in matchups):
            matchup_types.append("Playoffs")
        if any(m.get("is_consolation") for m in matchups):
            matchup_types.append("Consolation")
        if any(not m.get("is_playoffs") and not m.get("is_consolation") for m in matchups):
            matchup_types.append("Regular Season")

        if len(matchup_types) > 2:
            selected_type = st.radio("Filter matchups", matchup_types, horizontal=True)
        else:
            selected_type = "All"

        def matchup_type_filter(m: dict) -> bool:
            if selected_type == "All":             return True
            if selected_type == "Championship":    return bool(m.get("is_championship"))
            if selected_type == "3rd Place":       return bool(m.get("is_third_place"))
            if selected_type == "Playoffs":        return m.get("is_playoffs") and not m.get("is_consolation") and not m.get("is_championship") and not m.get("is_third_place")
            if selected_type == "Consolation":     return bool(m.get("is_consolation"))
            if selected_type == "Regular Season":  return not m.get("is_playoffs") and not m.get("is_consolation")
            return True

        filtered_matchups = [m for m in matchups if matchup_type_filter(m)]

        # Weekly points bar chart
        all_teams = [t for m in filtered_matchups for t in m["teams"]]
        df_pts = pd.DataFrame(all_teams).sort_values("points", ascending=True)
        colors = ["#f0c040" if r == max(df_pts["points"]) else "#4a90d9" for r in df_pts["points"]]
        fig_pts = go.Figure(go.Bar(
            x=df_pts["points"],
            y=df_pts["name"],
            orientation="h",
            marker_color=colors,
            text=df_pts["points"].apply(lambda x: f"{x:.0f}"),
            textposition="outside",
        ))
        fig_pts.update_layout(
            title=f"Week {selected_week} — Category Wins by Team",
            xaxis_title="Category Wins",
            yaxis_title="",
            height=max(300, len(all_teams) * 40),
            margin=dict(l=10, r=60, t=40, b=30),
        )
        st.plotly_chart(fig_pts, width="stretch")

        # Category win heatmap across all matchups
        st.subheader("Category Win Heatmap")
        heatmap_rows = []
        for m in filtered_matchups:
            if len(m["teams"]) < 2:
                continue
            t1, t2 = m["teams"][0], m["teams"][1]
            cats1 = t1.get("category_stats", {})
            cats2 = t2.get("category_stats", {})
            label = f"{t1['name']} vs {t2['name']}"
            for cat in sorted(set(cats1) | set(cats2)):
                v1 = cats1.get(cat, None)
                v2 = cats2.get(cat, None)
                winner = category_winner(v1, v2, cat, lower_is_better)
                score = 1 if winner == "←" else (-1 if winner == "→" else 0)
                heatmap_rows.append({"Matchup": label, "Category": cat, "Score": score})

        if heatmap_rows:
            df_heat = pd.DataFrame(heatmap_rows).pivot(index="Matchup", columns="Category", values="Score")
            fig_heat = px.imshow(
                df_heat,
                color_continuous_scale=["#d73027", "#f7f7f7", "#1a9850"],
                color_continuous_midpoint=0,
                title="Category Heatmap (green = left team wins, red = right team wins)",
                aspect="auto",
            )
            fig_heat.update_layout(height=max(200, len(df_heat) * 60))
            st.plotly_chart(fig_heat, width="stretch")

        st.divider()

        # Individual matchup detail cards
        st.subheader("Matchup Details")
        for m in filtered_matchups:
            if len(m["teams"]) < 2:
                continue
            t1, t2 = m["teams"][0], m["teams"][1]
            winner = get_winner(m)

            if m.get("is_championship"):
                header_icon = "🏆"
            elif m.get("is_third_place"):
                header_icon = "🥉"
            elif m.get("is_consolation"):
                header_icon = "😅"
            elif m.get("is_playoffs"):
                header_icon = "🥊"
            else:
                header_icon = "⚾"

            score_str = f"{t1['points']:.0f} – {t2['points']:.0f}"
            expanded = m.get("is_playoffs", False) or m.get("is_championship", False)

            with st.expander(
                f"{header_icon}  {t1['name']}  {score_str}  {t2['name']}",
                expanded=expanded,
            ):
                col_a, col_vs, col_b = st.columns([5, 1, 5])
                with col_a:
                    medal = "🏅 " if (winner and winner["team_key"] == t1["team_key"]) else ""
                    st.markdown(f"### {medal}{t1['name']}")
                    st.caption(f"Manager: {t1['manager']}")
                    st.metric("Category Wins", int(t1["points"]))
                with col_vs:
                    st.markdown("<p style='text-align:center;font-size:1.5em;padding-top:25px'>VS</p>",
                                unsafe_allow_html=True)
                with col_b:
                    medal = "🏅 " if (winner and winner["team_key"] == t2["team_key"]) else ""
                    st.markdown(f"### {medal}{t2['name']}")
                    st.caption(f"Manager: {t2['manager']}")
                    st.metric("Category Wins", int(t2["points"]))

                # Category breakdown table
                df_cats = build_category_df(t1, t2, lower_is_better)
                if not df_cats.empty:
                    # Color-code the winning team's stat column
                    # Columns: [Category, t1_name, Winner, t2_name]
                    def highlight_winner(row):
                        if row["Winner"] == "←":
                            return ["", "background-color: #1a9850; color: white", "", ""]
                        elif row["Winner"] == "→":
                            return ["", "", "", "background-color: #1a9850; color: white"]
                        return [""] * 4

                    st.dataframe(
                        df_cats.style.apply(highlight_winner, axis=1),
                        width="stretch",
                        hide_index=True,
                    )

                    # Category win counts
                    wins_t1 = (df_cats["Winner"] == "←").sum()
                    wins_t2 = (df_cats["Winner"] == "→").sum()
                    ties = (df_cats["Winner"] == "tie").sum()
                    c1, c2, c3 = st.columns(3)
                    c1.metric(t1["name"], f"{wins_t1} cats won")
                    c2.metric("Tied", f"{ties} cats")
                    c3.metric(t2["name"], f"{wins_t2} cats won")

# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — STANDINGS
# ══════════════════════════════════════════════════════════════════════════════
with tab_standings:
    if not standings:
        st.info("No standings data available.")
    else:
        df_stand = pd.DataFrame(standings)

        # Top-row metrics
        c1, c2, c3 = st.columns(3)
        leader = df_stand.iloc[0]
        most_pf = df_stand.loc[df_stand["points_for"].idxmax()]
        least_pa = df_stand.loc[df_stand["points_against"].idxmin()]
        c1.metric("🥇 First Place", leader["name"], f"{leader['wins']}W – {leader['losses']}L")
        c2.metric("🔥 Most Points For", most_pf["name"], f"{most_pf['points_for']:.1f} PF")
        c3.metric("🛡️ Best Defense", least_pa["name"], f"{least_pa['points_against']:.1f} PA")

        st.divider()

        col_left, col_right = st.columns(2)

        with col_left:
            # Wins bar chart
            df_sorted = df_stand.sort_values("wins", ascending=True)
            fig_wins = px.bar(
                df_sorted,
                x="wins",
                y="name",
                orientation="h",
                color="wins",
                color_continuous_scale="Greens",
                title="Season Wins",
                labels={"wins": "Wins", "name": ""},
                text="wins",
            )
            fig_wins.update_traces(textposition="outside")
            fig_wins.update_layout(
                showlegend=False,
                coloraxis_showscale=False,
                height=max(300, len(df_stand) * 35),
                margin=dict(l=10, r=40, t=40, b=20),
            )
            st.plotly_chart(fig_wins, width="stretch")

        with col_right:
            # Points For vs Against scatter
            fig_scatter = px.scatter(
                df_stand,
                x="points_against",
                y="points_for",
                text="name",
                color="wins",
                color_continuous_scale="RdYlGn",
                size=[15] * len(df_stand),
                title="Points For vs Points Against",
                labels={
                    "points_for": "Points For (PF)",
                    "points_against": "Points Against (PA)",
                    "wins": "Wins",
                },
            )
            fig_scatter.update_traces(textposition="top center", textfont_size=10)
            fig_scatter.update_layout(height=420)
            st.plotly_chart(fig_scatter, width="stretch")

        # Full standings table
        st.subheader("Full Standings Table")
        df_display = df_stand[["rank", "name", "wins", "losses", "ties", "points_for", "points_against"]].copy()
        df_display.columns = ["Rank", "Team", "W", "L", "T", "PF", "PA"]
        total_games = df_display["W"] + df_display["L"]
        df_display["Win%"] = (df_display["W"] / total_games.replace(0, 1)).round(3)
        df_display["GB"] = (df_display.iloc[0]["W"] - df_display["W"]) / 2
        st.dataframe(
            df_display.style.bar(subset=["Win%"], color=["#d73027", "#1a9850"], vmin=0, vmax=1),
            width="stretch",
            hide_index=True,
        )

        # Win % bar chart
        df_display_sorted = df_display.sort_values("Win%", ascending=True)
        fig_winpct = px.bar(
            df_display_sorted,
            x="Win%",
            y="Team",
            orientation="h",
            color="Win%",
            color_continuous_scale="RdYlGn",
            title="Win Percentage",
            text=df_display_sorted["Win%"].apply(lambda x: f"{x:.3f}"),
        )
        fig_winpct.update_traces(textposition="outside")
        fig_winpct.update_layout(
            coloraxis_showscale=False,
            height=max(300, len(df_display) * 35),
            margin=dict(l=10, r=60, t=40, b=20),
        )
        st.plotly_chart(fig_winpct, width="stretch")

# ══════════════════════════════════════════════════════════════════════════════
# TAB 4 — SEASON TRENDS
# ══════════════════════════════════════════════════════════════════════════════
with tab_season:
    if len(weeks_data) < 2:
        st.info("Season trend charts appear once you have 2+ weeks of data.")
    else:
        # Filters
        all_team_names = sorted({
            t["name"]
            for wd in weeks_data.values()
            for m in wd.get("matchups", [])
            for t in m.get("teams", [])
        })
        all_week_nums = sorted(weeks_data.keys())
        fcol1, fcol2 = st.columns([2, 1])
        with fcol1:
            selected_teams = st.multiselect(
                "Filter teams",
                options=all_team_names,
                default=all_team_names,
                key="trends_teams",
            )
        with fcol2:
            week_range = st.slider(
                "Week range",
                min_value=min(all_week_nums),
                max_value=max(all_week_nums),
                value=(min(all_week_nums), max(all_week_nums)),
                key="trends_weeks",
            )

        # Build multi-week standings history from reconstructed standings
        records: list[dict] = []
        for wk in sorted(weeks_data.keys()):
            if not (week_range[0] <= wk <= week_range[1]):
                continue
            for s in compute_standings(_weeks_frozen, wk):
                if s["name"] in selected_teams:
                    records.append({
                        "Week": wk,
                        "Team": s["name"],
                        "Wins": s["wins"],
                        "Losses": s["losses"],
                        "PF": s["points_for"],
                        "PA": s["points_against"],
                        "Rank": s["rank"],
                    })
        df_history = pd.DataFrame(records) if records else pd.DataFrame()

        if df_history.empty:
            st.info("No data matches the current filters.")
        else:
            # Rank over time (lower = better)
            fig_rank = px.line(
                df_history,
                x="Week",
                y="Rank",
                color="Team",
                title="Standings Rank Over Time (lower = better)",
                markers=True,
            )
            fig_rank.update_yaxes(autorange="reversed")
            fig_rank.update_layout(height=450)
            st.plotly_chart(fig_rank, width="stretch")

            # Cumulative wins over time
            fig_wins_time = px.line(
                df_history,
                x="Week",
                y="Wins",
                color="Team",
                title="Cumulative Wins Over Time",
                markers=True,
            )
            fig_wins_time.update_layout(height=400)
            st.plotly_chart(fig_wins_time, width="stretch")

            # Points For over time
            fig_pf = px.line(
                df_history,
                x="Week",
                y="PF",
                color="Team",
                title="Cumulative Points For Over Time",
                markers=True,
            )
            fig_pf.update_layout(height=400)
            st.plotly_chart(fig_pf, width="stretch")

            # Weekly category wins per team (filtered)
            weekly_pts: list[dict] = []
            for wk, wd in sorted(weeks_data.items()):
                if not (week_range[0] <= wk <= week_range[1]):
                    continue
                for m in wd.get("matchups", []):
                    for t in m.get("teams", []):
                        if t["name"] in selected_teams:
                            weekly_pts.append({"Week": wk, "Team": t["name"], "Categories Won": t["points"]})
            if weekly_pts:
                df_weekly = pd.DataFrame(weekly_pts)
                fig_weekly = px.line(
                    df_weekly,
                    x="Week",
                    y="Categories Won",
                    color="Team",
                    markers=True,
                    title="Categories Won Per Team Per Week",
                )
                fig_weekly.update_layout(height=450)
                st.plotly_chart(fig_weekly, width="stretch")

# ══════════════════════════════════════════════════════════════════════════════
# TAB 5 — TRANSACTIONS
# ══════════════════════════════════════════════════════════════════════════════
with tab_transactions:
    if not transactions:
        st.info("No transactions recorded for this week.")
    else:
        # Filters
        tx_teams = sorted({p.get("team", "") for tx in transactions for p in tx.get("players", []) if p.get("team")})
        tx_actions = sorted({p.get("action", "").lower() for tx in transactions for p in tx.get("players", []) if p.get("action")})
        tf1, tf2 = st.columns([2, 1])
        with tf1:
            sel_tx_teams = st.multiselect("Filter by team", options=tx_teams, default=tx_teams, key="tx_teams")
        with tf2:
            sel_tx_action = st.selectbox("Filter by action", options=["All"] + [a.title() for a in tx_actions], key="tx_action")

        filtered_transactions = [
            tx for tx in transactions
            if any(
                p.get("team") in sel_tx_teams
                and (sel_tx_action == "All" or p.get("action", "").lower() == sel_tx_action.lower())
                for p in tx.get("players", [])
            )
        ]

        # Count moves per team
        team_counts: dict[str, dict] = {}
        for tx in filtered_transactions:
            for p in tx.get("players", []):
                team = p.get("team", "Free Agent")
                action = p.get("action", "unknown").lower()
                if team not in team_counts:
                    team_counts[team] = {"add": 0, "drop": 0}
                team_counts[team][action] = team_counts[team].get(action, 0) + 1

        if team_counts:
            df_tx = pd.DataFrame([
                {"Team": team, "Adds": counts.get("add", 0), "Drops": counts.get("drop", 0)}
                for team, counts in sorted(team_counts.items(), key=lambda x: sum(x[1].values()), reverse=True)
            ])
            fig_tx = px.bar(
                df_tx,
                x="Team",
                y=["Adds", "Drops"],
                barmode="group",
                title="Transaction Activity This Week",
                color_discrete_map={"Adds": "#1a9850", "Drops": "#d73027"},
            )
            fig_tx.update_layout(height=350, xaxis_tickangle=-30)
            st.plotly_chart(fig_tx, width="stretch")
        elif filtered_transactions:
            st.info("No chart data for the selected filters.")

        # Transaction list
        st.subheader("All Transactions")
        icons = {"add": "➕", "drop": "➖", "trade": "🔄"}
        for tx in filtered_transactions:
            for p in tx.get("players", []):
                action = p.get("action", "").lower()
                icon = icons.get(action, "📋")
                pos = p.get("position", "")
                team = p.get("team", "")
                st.markdown(
                    f"{icon} **{action.upper()}** &nbsp; {p.get('name', '')} "
                    f"{'(' + pos + ')' if pos else ''} &nbsp;→&nbsp; _{team}_"
                )
